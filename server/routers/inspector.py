"""비전 검사 노드 라우터 — aria.inspection(검증된 비병목 파이프라인) 재사용.

/api/inspector/{start,stop,set_latency,state}. 텔레메트리는 WS로 inspector_state/result 송출.
추론 재작성 없음 — mock/patchcore/combined 디텍터 주입.
"""
import time
import threading
from fastapi import APIRouter, Body

from server.config import BANKS_DIR, MODELS_DIR, DATA_ROOT, IMG_EXT
from aria.core.config import inference as _cfg, pdm as _pdm_cfg
from aria.planes.twin_state import get_twin as _get_twin
from aria.ipc.bus import get_bus as _get_bus

router = APIRouter(prefix="/api/inspector", tags=["inspector"])

# _run · _lanes 는 TwinState로 승격됨 — 직접 접근 금지.
# _infer_lock 은 검사 평면 내부 관심사(공유 백본 직렬화) — 승격 안 함.
_infer_lock = threading.Lock()

# P-producer 헬스용 — 마지막 trigger 시각(monotonic). inspection_node.py가 읽음.
_last_trigger_ts: float = 0.0


def get_last_trigger_ts() -> float:
    return _last_trigger_ts


def _feed_health(asset_proxy, snap: dict, lane: int, elapsed: float):
    """T1-C C0: 실 텔레메트리(p95·drop) + 결정론적 트윈 프록시(temp·vib, sim) → IPC.
    자산 = 해당 레인 검사 스테이션(robot_arm_{lane}). 예외를 밖으로 던지지 않음."""
    try:
        p95 = snap.get("infer_latency_p95_ms") or 0.0
        drop = snap.get("drop_count") or 0.0
        asset_id = f"robot_arm_{lane}"
        px = asset_proxy(asset_id, p95, drop, elapsed)
        _get_bus().publish("health", {
            "lane": lane, "asset_id": asset_id,
            "temp_c": px["temp_c"], "vib_rms_mm_s": px["vib_rms_mm_s"],
            "infer_p95_ms": p95, "drop_rate": drop, "current_a": None, "sim": px["sim"],
        })
    except Exception:
        pass


def _note_ng_if(msg, lane: int):
    """검사 결과가 NG면 IPC bus로 NG 이벤트 발행 (P-core가 pdm_fusion에 라우팅)."""
    try:
        if msg.get("type") != "result" or msg.get("verdict") != "NG":
            return
        cell = msg.get("defect_class") or msg.get("cell")
        if cell is None:
            xy = msg.get("defect_xy")
            if isinstance(xy, (list, tuple)) and len(xy) == 2:
                cell = f"{int(xy[0] * 4)},{int(xy[1] * 4)}"   # 조좌표 4x4 셀
        _get_bus().publish("ng", {"asset_id": f"robot_arm_{lane}", "cell": cell})
    except Exception:
        pass


def _build_detector(mode: str, category: str, tau: float):
    """mode별 디텍터 생성(patchcore/combined). 실패 시 예외."""
    from aria.inspection.detectors import PatchCoreDetector
    bank = BANKS_DIR / f"{category}.npy"
    if not bank.exists():
        raise FileNotFoundError(f"bank 없음: {category}")
    det = PatchCoreDetector(str(bank), tau=tau)
    if mode == "combined":
        from aria.inspection.detectors import YoloDetector, CombinedDetector
        w = MODELS_DIR / "yolo" / f"{category}.pt"
        if w.exists():
            det = CombinedDetector(det, YoloDetector(str(w), conf=_cfg.yolo_conf), tau=tau)
    return det


def _trained_rotation(classes=None):
    """학습된(뱅크 보유) + test 이미지 있는 클래스 순환 목록."""
    out = []
    for f in sorted(BANKS_DIR.glob("*.npy")):
        c = f.stem
        if (DATA_ROOT / c / "test").is_dir():
            out.append(c)
    if classes:
        sel = [c for c in classes if c in out]
        if sel:
            out = sel
    return out


def _collect_images(category: str, limit: int = 80):
    cat = DATA_ROOT / category
    good, defect = [], []
    test = cat / "test"
    if test.is_dir():
        for sub in sorted(test.iterdir()):
            if not sub.is_dir():
                continue
            files = [str(p) for p in sorted(sub.glob("*")) if p.suffix.lower() in IMG_EXT]
            (good if sub.name.lower() == "good" else defect).extend(files)
    out = []
    for i in range(max(len(good), len(defect))):
        if i < len(good):
            out.append(good[i])
        if i < len(defect):
            out.append(defect[i])
    return out[:limit] if limit else out


@router.post("/start")
async def start(payload: dict = Body(default={})):
    from aria.inspection.async_pipeline import AsyncPipeline, MockDriver, mock_infer_factory
    from aria.inspection.twin_bridge import TwinBridge, WsFloorSink

    twin = _get_twin()
    if twin.is_running():
        return {"ok": False, "error": "이미 가동 중 — 먼저 stop"}

    mode = payload.get("mode", "mock")
    category = payload.get("category", "bottle")
    tau = float(payload.get("tau", _cfg.tau(category)))
    q = int(payload.get("queue", _cfg.queue_depth))
    workers = int(payload.get("workers", _cfg.n_workers))
    line_hz = float(payload.get("line_hz", _cfg.single_hz))
    holder = {"infer_ms": float(payload.get("infer_ms", 40.0)),
              "extra_ms": float(payload.get("inflate_ms", 0.0))}

    if mode in ("patchcore", "combined"):
        from aria.inspection.detectors import PatchCoreDetector
        bank = BANKS_DIR / f"{category}.npy"
        if not bank.exists():
            return {"ok": False, "error": f"뱅크 없음: banks/{category}.npy"}
        detector = PatchCoreDetector(str(bank), tau=tau)
        if mode == "combined":
            from aria.inspection.detectors import YoloDetector, CombinedDetector
            w = MODELS_DIR / "yolo" / f"{category}.pt"
            if not w.exists():
                return {"ok": False, "error": f"YOLO weights 없음: models/yolo/{category}.pt"}
            detector = CombinedDetector(detector, YoloDetector(str(w), conf=_cfg.yolo_conf), tau=tau)
        images = _collect_images(category, limit=80)
        if not images:
            return {"ok": False, "error": f"이미지 없음: data/{category}/test"}
        detector.infer(images[0])   # 웜업

        def infer_fn(image):
            out = detector.infer(image)
            if holder["extra_ms"] > 0:
                time.sleep(holder["extra_ms"] / 1000.0)
            return out
        driver = MockDriver(grab_ms=2.0, image_paths=images)
    else:
        infer_fn = mock_infer_factory(lambda: holder["infer_ms"])
        driver = MockDriver(grab_ms=2.0, seed=7)

    def _ws(msg):
        t = msg.get("type")
        _get_bus().publish("ws", {**msg, "type": f"inspector_{t}"})
        _note_ng_if(msg, lane=0)

    bridge = TwinBridge([WsFloorSink(_ws)])
    pipe = AsyncPipeline(driver, infer_fn, tau=tau, queue_capacity=q,
                         n_workers=workers, telemetry_cb=bridge.telemetry_cb())
    pipe.start()
    bridge.start_state_pump(pipe.snapshot, hz=_cfg.state_pump_hz)

    twin.start_run(pipe, bridge, mode, category, holder)

    # 유한 패스: 데이터셋 1바퀴(테스트 이미지 수)만큼 검사 후 자동 완료. payload.max_parts로 override.
    if mode in ("patchcore", "combined"):
        default_total = len(images)
    else:
        default_total = 150
    max_parts = int(payload.get("max_parts") or default_total)
    twin.update_run(max_parts=max_parts)

    def _trigger_loop():
        global _last_trigger_ts
        from aria.inspection.asset_proxy import proxy as _asset_proxy
        interval = 1.0 / max(0.1, line_hz)
        n = 0
        last_rec = 0.0
        t_start = time.time()
        while _get_twin().is_running() and n < max_parts:
            pipe.trigger(); _last_trigger_ts = time.monotonic(); n += 1
            now = time.time()
            if now - last_rec >= _cfg.snapshot_interval_s:
                last_rec = now
                try:
                    snap = pipe.snapshot()
                    _get_bus().publish("record", {"snap": snap, "lane": 0, "category": category})
                    _feed_health(_asset_proxy, snap, lane=0, elapsed=now - t_start)
                except Exception:
                    pass
            time.sleep(interval)
        # 자연 완료(중간 stop이 아니면) → 드레인 대기 후 정지 + 완료 방송
        if _get_twin().is_running():
            time.sleep(1.8)                       # 큐 잔여분 추론 완료 대기
            try:
                snap = pipe.snapshot()
            except Exception:
                snap = {}
            _p, _b = _get_twin().stop_run()
            try:
                if _p: _p.stop()
                if _b: _b.stop()
            except Exception:
                pass
            _get_bus().publish("ws", {
                "type": "inspector_done", "category": category, "mode": mode,
                "n_trigger": snap.get("n_trigger"), "n_ok": snap.get("n_ok"),
                "n_ng": snap.get("n_ng"), "yield_rate": snap.get("yield_rate"),
                "ts": time.time(),
            })

    th = threading.Thread(target=_trigger_loop, name="inspector-trigger", daemon=True)
    th.start()
    twin.update_run(trigger_thread=th)
    return {"ok": True, "mode": mode, "category": category, "line_hz": line_hz, "max_parts": max_parts}


@router.post("/stop")
async def stop():
    twin = _get_twin()
    if not twin.is_running():
        return {"ok": True, "note": "이미 정지"}
    run = twin.get_run()
    th = run.get("trigger_thread")
    pipe, bridge = twin.stop_run()
    if th:
        th.join(timeout=1.0)
    try:
        if pipe: pipe.stop()
        if bridge: bridge.stop()
    except Exception as e:
        return {"ok": True, "warn": str(e)}
    return {"ok": True}


# ── 멀티레인: 동시 N레인, 각 레인이 클래스를 차례로 검사하고 끝나면 다음 클래스로 ──
@router.post("/start_lanes")
async def start_lanes(payload: dict = Body(default={})):
    from aria.inspection.async_pipeline import AsyncPipeline, MockDriver
    from aria.inspection.twin_bridge import TwinBridge, WsFloorSink
    twin = _get_twin()
    if twin.lanes_running():
        return {"ok": False, "error": "이미 멀티레인 가동 중 — 먼저 stop_lanes"}
    mode = payload.get("mode", "combined")
    line_hz = float(payload.get("line_hz", _cfg.lane_hz))
    tau = float(payload.get("tau", _cfg.tau()))
    lane_count = int(payload.get("lane_count", 3))
    rotation = _trained_rotation(payload.get("classes"))
    if not rotation:
        return {"ok": False, "error": "학습된 클래스 없음 — 먼저 학습"}
    twin.start_lanes(lane_count, rotation, mode)
    epoch = twin.lanes_epoch()   # 이 가동 세대 — 구 워커 부활 방지

    def _alive() -> bool:
        t = _get_twin()
        return t.lanes_running() and t.lanes_epoch() == epoch

    def lane_worker(lane: int):
        cls_idx = lane % len(rotation)
        while _alive():
            category = rotation[cls_idx]
            try:
                detector = _build_detector(mode, category, tau)
                images = _collect_images(category, limit=60)
                if not images:
                    raise RuntimeError("no images")
                detector.infer(images[0])   # 웜업(공유 백본 1회 로드)
            except Exception:
                cls_idx = (cls_idx + lane_count) % len(rotation); time.sleep(0.5); continue

            def infer_fn(image, _d=detector):
                with _infer_lock:           # 공유 백본 직렬화
                    return _d.infer(image)

            def _ws(msg, _lane=lane, _cat=category):
                t = msg.get("type")
                _get_bus().publish("ws", {**msg, "type": f"inspector_{t}", "lane": _lane, "category": _cat})
                _note_ng_if(msg, lane=_lane)

            driver = MockDriver(grab_ms=2.0, image_paths=images)
            bridge = TwinBridge([WsFloorSink(_ws)])
            pipe = AsyncPipeline(driver, infer_fn, tau=tau, queue_capacity=_cfg.queue_depth, n_workers=_cfg.n_workers,
                                 telemetry_cb=bridge.telemetry_cb())
            pipe.start()
            bridge.start_state_pump(pipe.snapshot, hz=_cfg.lane_pump_hz)

            n, total = 0, len(images)
            interval = 1.0 / max(0.1, line_hz)
            last_rec = 0.0
            t_start = time.time()
            while _alive() and n < total:
                pipe.trigger(); n += 1
                now = time.time()
                if now - last_rec >= _cfg.snapshot_interval_s:      # 시계열 척추: 레인별 샘플
                    last_rec = now
                    try:
                        from aria.inspection.asset_proxy import proxy as _asset_proxy
                        snap = pipe.snapshot()
                        _get_bus().publish("record", {"snap": snap, "lane": lane, "category": category})
                        _feed_health(_asset_proxy, snap, lane=lane, elapsed=now - t_start)
                    except Exception:
                        pass
                time.sleep(interval)
            time.sleep(1.2)
            try:
                snap = pipe.snapshot()
            except Exception:
                snap = {}
            try:
                pipe.stop(); bridge.stop()
            except Exception:
                pass
            _get_bus().publish("ws", {
                "type": "inspector_done", "lane": lane, "category": category,
                "n_ok": snap.get("n_ok"), "n_ng": snap.get("n_ng"),
                "yield_rate": snap.get("yield_rate"), "ts": time.time(),
            })
            cls_idx = (cls_idx + lane_count) % len(rotation)   # 다음 클래스

    for lane in range(lane_count):
        th = threading.Thread(target=lane_worker, args=(lane,), name=f"lane-{lane}", daemon=True)
        th.start(); _get_twin().append_lane_thread(th)
    return {"ok": True, "lanes": lane_count, "rotation": rotation, "mode": mode}


@router.post("/stop_lanes")
async def stop_lanes():
    _get_twin().stop_lanes()
    return {"ok": True}


@router.post("/set_latency")
async def set_latency(payload: dict = Body(...)):
    run = _get_twin().get_run()
    if not run.get("running"):
        return {"ok": False, "error": "가동 중 아님"}
    h = run.get("holder", {})
    if "infer_ms" in payload:
        h["infer_ms"] = float(payload["infer_ms"])
    if "inflate_ms" in payload:
        h["extra_ms"] = float(payload["inflate_ms"])
    return {"ok": True, "infer_ms": h.get("infer_ms"), "inflate_ms": h.get("extra_ms")}


@router.get("/state")
async def state():
    run = _get_twin().get_run()
    if not run.get("running"):
        return {"ok": True, "running": False}
    pipe = run.get("pipe")
    snap = pipe.snapshot()
    recent = [
        {"part_id": r.part_id, "verdict": r.verdict, "score": round(r.score, 4),
         "latency_ms": r.latency_ms, "defect_class": r.defect_class}
        for r in list(pipe.results())[-12:]
    ]
    return {"ok": True, "running": True, "mode": run.get("mode"),
            "category": run.get("category"), "snapshot": snap, "recent": recent}


@router.get("/history")
async def history(minutes: int = 60, max_points: int = 200):
    """시계열 척추 조회 — 재시작 후에도 저장분에서 추세 복원(리플레이·드리프트 토대)."""
    from aria.inspection.timeseries import recent as ts_recent
    series = ts_recent(minutes=minutes, max_points=max_points)
    return {"ok": True, "series": series, "count": len(series)}


@router.get("/health_history")
async def health_history(asset_id: str = None, minutes: int = 60, max_points: int = 300):
    """T1-C: 자산 건전성 선행지표 시계열(온도·진동·p95·drop). 재시작 후 복원."""
    from aria.inspection.timeseries import recent_health, health_assets
    series = recent_health(asset_id=asset_id, minutes=minutes, max_points=max_points)
    return {"ok": True, "series": series, "count": len(series), "assets": health_assets(minutes)}
