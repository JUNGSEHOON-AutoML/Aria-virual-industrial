"""시뮬레이션 데이터 파이프라인 라우터 — aria.simulation / feature_bank 재사용.
/api/sim/{dataset,train,validate}. 학습 진행은 WS 'training' + agent_status 로 송출.
"""
import json
import asyncio
import threading
import time
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Body

from server.config import UPLOAD_DIR
from server.ws import manager, broadcast_threadsafe

router = APIRouter(prefix="/api/sim", tags=["sim"])


@router.post("/dataset")
async def dataset(payload: dict = Body(default={})):
    from aria.simulation.dataset import save_sim_dataset
    run_id = f"sim_{int(time.time())}"
    work = UPLOAD_DIR / run_id
    m = save_sim_dataset(
        payload.get("images", []), str(work),
        defect_ratio=float(payload.get("defect_ratio", 0.3)),
        defect_type=payload.get("defect_type", "scratch"),
    )
    return {"run_id": run_id, "n_images": m["n_images"], "classes": m["classes"], "work_dir": m["work_dir"]}


@router.post("/train")
async def train(payload: dict = Body(...)):
    from aria.perception.scorer.feature_bank import build_bank
    from aria.learning.training.events import make_training_event
    run_id = payload.get("run_id")
    work = UPLOAD_DIR / str(run_id)
    mpath = work / "manifest.json"
    if not run_id or not mpath.exists():
        return {"ok": False, "error": "manifest 없음 — 먼저 생성/인테이크"}
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    imgs = manifest.get("images", [])
    good = [p for p in imgs if Path(p).parent.name.lower() in ("good", "normal", "ok")] or imgs
    loop = asyncio.get_running_loop()

    def publish(ev):  # make_training_event 는 type='training'
        broadcast_threadsafe(loop, ev)

    def emit_agent(state, detail):
        broadcast_threadsafe(loop, {"type": "agent_status", "agent": "TRAINER", "state": state, "detail": detail})

    def worker():
        try:
            emit_agent("running", "메모리뱅크 구축")
            publish(make_training_event(run_id, 0, len(good), "running", loss=0.0))
            bank = build_bank(good, run_id, publish)
            np.save(str(work / "bank.npy"), bank)
            publish(make_training_event(run_id, len(good), len(good), "done", loss=0.0))
            emit_agent("done", f"{len(good)} img · {bank.shape[0]} patch")
        except Exception as e:
            publish(make_training_event(run_id, 0, 0, "error", loss=0.0))
            emit_agent("idle", f"실패: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "run_id": run_id}


@router.post("/validate")
async def validate(payload: dict = Body(...)):
    from aria.simulation.validation.validate import run_validation
    run_id = payload.get("run_id")
    mpath = UPLOAD_DIR / str(run_id) / "manifest.json"
    if not run_id or not mpath.exists():
        return {"ok": False, "error": "manifest 없음"}
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    await manager.broadcast({"type": "agent_status", "agent": "VERIFIER", "state": "running", "detail": "NG 검증"})
    result = run_validation(manifest, criteria=payload.get("criteria"))
    er = result.get("escape_rate")
    detail = f"escape {er:.0%}" if er is not None else (result.get("error") or "검증")
    await manager.broadcast({"type": "agent_status", "agent": "VERIFIER", "state": "done", "detail": detail})
    v = result.get("fat_verdict", "N/A")
    st = "done" if v == "PASS" else ("idle" if v == "FAIL" else "running")
    await manager.broadcast({"type": "agent_status", "agent": "FAT", "state": st,
                             "detail": f"{v} · escape {er:.0%}" if er is not None else f"{v}"})
    return result
