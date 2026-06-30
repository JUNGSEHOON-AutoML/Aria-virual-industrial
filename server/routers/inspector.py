"""비전 검사 노드 라우터 — aria.inspection(검증된 비병목 파이프라인) 재사용.

/api/inspector/{start,stop,set_latency,state}. 텔레메트리는 WS로 inspector_state/result 송출.
추론 재작성 없음 — mock/patchcore/combined 디텍터 주입.
"""
import asyncio
import time
import threading
from fastapi import APIRouter, Body

from server.config import BANKS_DIR, MODELS_DIR, DATA_ROOT, IMG_EXT
from server.ws import manager, broadcast_threadsafe

router = APIRouter(prefix="/api/inspector", tags=["inspector"])

_run: dict = {}        # 런타임 상태(단일 노드)
_lanes: dict = {}      # 멀티레인(동시 N레인) 상태
_infer_lock = threading.Lock()   # 공유 DINO 백본 보호(레인 동시 추론 직렬화)


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
            det = CombinedDetector(det, YoloDetector(str(w), conf=0.25), tau=tau)
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

    if _run.get("running"):
        return {"ok": False, "error": "이미 가동 중 — 먼저 stop"}

    mode = payload.get("mode", "mock")
    category = payload.get("category", "bottle")
    tau = float(payload.get("tau", 0.5))
    q = int(payload.get("queue", 4))
    workers = int(payload.get("workers", 2))
    line_hz = float(payload.get("line_hz", 20.0))
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
            detector = CombinedDetector(detector, YoloDetector(str(w), conf=0.25), tau=tau)
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

    loop = asyncio.get_running_loop()

    def _ws(msg):
        t = msg.get("type")
        broadcast_threadsafe(loop, {**msg, "type": f"inspector_{t}"})

    bridge = TwinBridge([WsFloorSink(_ws)])
    pipe = AsyncPipeline(driver, infer_fn, tau=tau, queue_capacity=q,
                         n_workers=workers, telemetry_cb=bridge.telemetry_cb())
    pipe.start()
    bridge.start_state_pump(pipe.snapshot, hz=5.0)

    _run.update({"running": True, "pipe": pipe, "bridge": bridge,
                 "holder": holder, "mode": mode, "category": category})

    # 유한 패스: 데이터셋 1바퀴(테스트 이미지 수)만큼 검사 후 자동 완료. payload.max_parts로 override.
    if mode in ("patchcore", "combined"):
        default_total = len(images)
    else:
        default_total = 150
    max_parts = int(payload.get("max_parts") or default_total)
    _run["max_parts"] = max_parts

    def _trigger_loop():
        interval = 1.0 / max(0.1, line_hz)
        n = 0
        while _run.get("running") and n < max_parts:
            pipe.trigger(); n += 1
            time.sleep(interval)
        # 자연 완료(중간 stop이 아니면) → 드레인 대기 후 정지 + 완료 방송
        if _run.get("running"):
            time.sleep(1.8)                       # 큐 잔여분 추론 완료 대기
            try:
                snap = pipe.snapshot()
            except Exception:
                snap = {}
            _run["running"] = False
            try:
                pipe.stop(); bridge.stop()
            except Exception:
                pass
            broadcast_threadsafe(loop, {
                "type": "inspector_done", "category": category, "mode": mode,
                "n_trigger": snap.get("n_trigger"), "n_ok": snap.get("n_ok"),
                "n_ng": snap.get("n_ng"), "yield_rate": snap.get("yield_rate"),
                "ts": time.time(),
            })

    th = threading.Thread(target=_trigger_loop, name="inspector-trigger", daemon=True)
    th.start()
    _run["trigger_thread"] = th
    return {"ok": True, "mode": mode, "category": category, "line_hz": line_hz, "max_parts": max_parts}


@router.post("/stop")
async def stop():
    if not _run.get("running"):
        return {"ok": True, "note": "이미 정지"}
    _run["running"] = False
    th = _run.get("trigger_thread")
    if th:
        th.join(timeout=1.0)
    try:
        _run["pipe"].stop()
        _run["bridge"].stop()
    except Exception as e:
        return {"ok": True, "warn": str(e)}
    return {"ok": True}


# ── 멀티레인: 동시 N레인, 각 레인이 클래스를 차례로 검사하고 끝나면 다음 클래스로 ──
@router.post("/start_lanes")
async def start_lanes(payload: dict = Body(default={})):
    from aria.inspection.async_pipeline import AsyncPipeline, MockDriver
    from aria.inspection.twin_bridge import TwinBridge, WsFloorSink
    if _lanes.get("running"):
        return {"ok": False, "error": "이미 멀티레인 가동 중 — 먼저 stop_lanes"}
    mode = payload.get("mode", "combined")
    line_hz = float(payload.get("line_hz", 6.0))
    tau = float(payload.get("tau", 0.5))
    lane_count = int(payload.get("lane_count", 3))
    rotation = _trained_rotation(payload.get("classes"))
    if not rotation:
        return {"ok": False, "error": "학습된 클래스 없음 — 먼저 학습"}
    loop = asyncio.get_running_loop()
    _lanes.clear()
    _lanes.update({"running": True, "threads": [], "rotation": rotation, "lane_count": lane_count})

    def lane_worker(lane: int):
        cls_idx = lane % len(rotation)
        while _lanes.get("running"):
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
                broadcast_threadsafe(loop, {**msg, "type": f"inspector_{t}", "lane": _lane, "category": _cat})

            driver = MockDriver(grab_ms=2.0, image_paths=images)
            bridge = TwinBridge([WsFloorSink(_ws)])
            pipe = AsyncPipeline(driver, infer_fn, tau=tau, queue_capacity=4, n_workers=1,
                                 telemetry_cb=bridge.telemetry_cb())
            pipe.start()
            bridge.start_state_pump(pipe.snapshot, hz=4.0)

            n, total = 0, len(images)
            interval = 1.0 / max(0.1, line_hz)
            while _lanes.get("running") and n < total:
                pipe.trigger(); n += 1; time.sleep(interval)
            time.sleep(1.2)
            try:
                snap = pipe.snapshot()
            except Exception:
                snap = {}
            try:
                pipe.stop(); bridge.stop()
            except Exception:
                pass
            broadcast_threadsafe(loop, {
                "type": "inspector_done", "lane": lane, "category": category,
                "n_ok": snap.get("n_ok"), "n_ng": snap.get("n_ng"),
                "yield_rate": snap.get("yield_rate"), "ts": time.time(),
            })
            cls_idx = (cls_idx + lane_count) % len(rotation)   # 다음 클래스

    for lane in range(lane_count):
        th = threading.Thread(target=lane_worker, args=(lane,), name=f"lane-{lane}", daemon=True)
        th.start(); _lanes["threads"].append(th)
    return {"ok": True, "lanes": lane_count, "rotation": rotation, "mode": mode}


@router.post("/stop_lanes")
async def stop_lanes():
    _lanes["running"] = False
    return {"ok": True}


@router.post("/set_latency")
async def set_latency(payload: dict = Body(...)):
    if not _run.get("running"):
        return {"ok": False, "error": "가동 중 아님"}
    h = _run["holder"]
    if "infer_ms" in payload:
        h["infer_ms"] = float(payload["infer_ms"])
    if "inflate_ms" in payload:
        h["extra_ms"] = float(payload["inflate_ms"])
    return {"ok": True, "infer_ms": h["infer_ms"], "inflate_ms": h["extra_ms"]}


@router.get("/state")
async def state():
    if not _run.get("running"):
        return {"ok": True, "running": False}
    pipe = _run["pipe"]
    snap = pipe.snapshot()
    recent = [
        {"part_id": r.part_id, "verdict": r.verdict, "score": round(r.score, 4),
         "latency_ms": r.latency_ms, "defect_class": r.defect_class}
        for r in list(pipe.results())[-12:]
    ]
    return {"ok": True, "running": True, "mode": _run["mode"],
            "category": _run["category"], "snapshot": snap, "recent": recent}
