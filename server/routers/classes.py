"""클래스(MVTec) 라우터 — per-class 학습/판정 + 스캔/샘플 + 파일 서빙. feature_bank 재사용.
/api/class/{train,validate}, /api/mvtec/scan, /api/class/samples, /api/image, /api/result.
"""
import asyncio
import threading
import urllib.parse
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse

from server.config import BANKS_DIR, IMG_EXT, ROOT, DATA_ROOT, UPLOAD_DIR, OUTPUT_DIR
from server.ws import manager, broadcast_threadsafe

router = APIRouter(prefix="/api", tags=["class"])


@router.post("/class/train")
async def class_train(payload: dict = Body(...)):
    from aria.perception.scorer.feature_bank import build_bank
    cid = payload.get("classId")
    root = Path(payload.get("mvtec_path", ""))
    good_dir = root / "train" / "good"
    if not good_dir.exists():
        return {"ok": False, "error": f"good 디렉토리 없음: {good_dir}"}
    goods = sorted(str(p) for p in good_dir.glob("*") if p.suffix.lower() in IMG_EXT)
    if not cid or not goods:
        return {"ok": False, "error": f"good 이미지 없음: {good_dir}"}
    loop = asyncio.get_running_loop()

    def emit(state, detail):
        broadcast_threadsafe(loop, {"type": "agent_status", "agent": cid.upper(), "state": state, "detail": detail})

    def worker():
        try:
            emit("running", f"{len(goods)} good 학습")
            bank = build_bank(goods, run_id=cid)
            np.save(str(BANKS_DIR / f"{cid}.npy"), bank)
            emit("done", f"bank {bank.shape[0]} 패치")
        except Exception as e:
            emit("idle", f"실패: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "classId": cid, "n_good": len(goods)}


@router.post("/class/validate")
async def class_validate(payload: dict = Body(...)):
    from aria.perception.scorer.feature_bank import cosine_score
    from aria.simulation.validation.validate import run_validation
    cid = payload.get("classId")
    root = Path(payload.get("mvtec_path", ""))
    bank_path = BANKS_DIR / f"{cid}.npy"
    if not bank_path.exists():
        return {"ok": False, "error": f"bank 없음 — 먼저 학습: {cid}"}
    test_imgs = [str(p) for p in (root / "test").rglob("*") if p.suffix.lower() in IMG_EXT]
    if not test_imgs:
        return {"ok": False, "error": f"test 이미지 없음: {root / 'test'}"}
    bank = np.load(bank_path)
    manifest = {"images": test_imgs, "work_dir": str(BANKS_DIR)}
    result = run_validation(manifest, score_fn=lambda p: cosine_score(p, bank), criteria=payload.get("criteria"))
    result["classId"] = cid
    await manager.broadcast({"type": "class_result", "classId": cid,
        "escape_rate": result.get("escape_rate"), "fp_rate": result.get("fp_rate"),
        "fat_verdict": result.get("fat_verdict"), "threshold": result.get("threshold")})
    return result


@router.get("/mvtec/scan")
async def mvtec_scan(root: str):
    base = Path(root)
    if not base.is_dir():
        return {"ok": False, "error": f"디렉토리 없음: {root}"}
    classes = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "train" / "good").is_dir() and (d / "test").is_dir():
            classes.append(d.name)
    return {"ok": True, "root": str(base), "classes": classes}


@router.get("/class/samples")
async def class_samples(classId: str, mvtec_path: str, n: int = 9):
    test = Path(mvtec_path) / "test"
    if not test.is_dir():
        return {"ok": False, "error": f"test 없음: {test}"}
    def url(p): return "/api/image?path=" + urllib.parse.quote(str(p))
    items = []
    good_dir = test / "good"
    if good_dir.is_dir():
        for p in sorted(good_dir.glob("*"))[:max(1, n // 3)]:
            if p.suffix.lower() in IMG_EXT:
                items.append({"url": url(p), "label": "OK"})
    for d in sorted(test.iterdir()):
        if d.is_dir() and d.name != "good":
            for p in sorted(d.glob("*"))[:2]:
                if p.suffix.lower() in IMG_EXT:
                    items.append({"url": url(p), "label": "NG", "defect": d.name})
                if len(items) >= n:
                    break
        if len(items) >= n:
            break
    return {"ok": True, "classId": classId, "items": items[:n]}


@router.get("/image")
async def serve_image(path: str):
    p = Path(path).resolve()
    allowed = [ROOT.resolve(), DATA_ROOT.resolve(), UPLOAD_DIR.resolve()]
    if not any(str(p).startswith(str(a)) for a in allowed) or not p.is_file():
        return JSONResponse({"error": "허용되지 않은 경로"}, status_code=403)
    return FileResponse(str(p))


@router.get("/result/{filename}")
async def serve_result(filename: str):
    path = OUTPUT_DIR / filename
    if not path.is_file():
        return JSONResponse({"error": "결과 없음"}, status_code=404)
    return FileResponse(str(path))
