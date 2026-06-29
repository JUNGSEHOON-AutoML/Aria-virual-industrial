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

_run: dict = {}   # 런타임 상태(단일 노드)


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

    def _trigger_loop():
        interval = 1.0 / max(0.1, line_hz)
        while _run.get("running"):
            pipe.trigger()
            time.sleep(interval)

    th = threading.Thread(target=_trigger_loop, name="inspector-trigger", daemon=True)
    th.start()
    _run["trigger_thread"] = th
    return {"ok": True, "mode": mode, "category": category, "line_hz": line_hz}


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
