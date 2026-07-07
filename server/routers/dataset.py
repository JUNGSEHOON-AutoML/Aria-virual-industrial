"""데이터셋 인테이크 라우터 — aria.perception.intake 재사용.
/api/dataset/intake: zip/tar 업로드 → 스캔 → 도메인 판단. 진행은 WS agent_status.
"""
import json
import time
import asyncio
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

from server.config import UPLOAD_DIR
from server.ws import manager

router = APIRouter(prefix="/api/dataset", tags=["dataset"])


@router.post("/intake")
async def intake(file: UploadFile = File(...)):
    from aria.perception.intake.scan_agent import scan_dataset
    from aria.perception.intake.domain_agent import classify_domain

    run_id = f"ds_{int(time.time())}"
    if file.filename and file.filename.endswith(".tar.gz"):
        ext = ".tar.gz"
    elif file.filename and file.filename.endswith(".tgz"):
        ext = ".tgz"
    else:
        ext = (Path(file.filename).suffix if file.filename else "") or ".zip"

    arc = UPLOAD_DIR / f"{run_id}{ext}"
    arc.write_bytes(await file.read())
    work = UPLOAD_DIR / run_id

    async def emit(agent, state, detail=""):
        await manager.broadcast({"type": "agent_status", "agent": agent, "state": state, "detail": detail})

    try:
        await emit("SCAN", "running", "압축 해제·구조 분석")
        rep = await asyncio.to_thread(scan_dataset, str(arc), str(work))
        (work / "manifest.json").write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
        await emit("SCAN", "done", f"{rep['n_images']}장 · 클래스 {len(rep['classes'])}")
        await emit("DOMAIN", "running", "VLM 도메인 판단")
        dom = await asyncio.to_thread(classify_domain, rep)
        await emit("DOMAIN", "done", dom["domain"])
        return {"run_id": run_id, "n_images": rep["n_images"], "classes": rep["classes"],
                "resolution": rep["resolution"], "formats": rep["formats"], "domain": dom}
    except Exception as e:
        await emit("SCAN", "idle", f"실패: {e}")
        await emit("DOMAIN", "idle", "중단됨")
        raise HTTPException(status_code=500, detail=str(e))
