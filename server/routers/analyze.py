"""단일 이미지 분석 라우터 — 깨끗한 PatchCore 추론(feature_bank 재사용).
/api/analyze: 이미지 업로드 + category → score/verdict/heatmap.
(VLM/오케스트레이터 기반 풀 분석은 MCP 의존이라 B3 에이전트 트랙에서 별도 검토.)
"""
import time
import math
import re
import threading
import uuid

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, Body

from server.config import UPLOAD_DIR, BANKS_DIR, ROOT, DATA_ROOT
from aria.core.config import inference as _cfg

router = APIRouter(prefix="/api", tags=["analyze"])
_inference_lock = threading.Lock()


def _validate_request(category, tau):
    if not isinstance(category, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", category):
        raise HTTPException(422, "invalid category")
    try:
        value = float(tau)
    except (TypeError, ValueError):
        raise HTTPException(422, "tau must be finite")
    if not math.isfinite(value):
        raise HTTPException(422, "tau must be finite")
    return value


def _run_inference(bank, tau, path, enrich=False):
    from aria.inspection.detectors import PatchCoreDetector
    # The backbone singleton is lazily loaded and shared with other requests.
    # Serialize these API calls without holding the asyncio event loop.
    with _inference_lock:
        result = PatchCoreDetector(str(bank), tau=tau).infer(str(path))
    if enrich:
        from aria.inspection.result_encode import enrich_result
        result["_encoded"] = enrich_result(str(path), result.get("heatmap"))
    return result



@router.post("/analyze_path")
async def analyze_path(payload: dict = Body(...)):
    """서버 측 이미지 경로 분석 → score/verdict + image_b64/heatmap_b64/defect_xy(결함 3D 뷰어용)."""
    category = payload.get("category", "bottle")
    path = payload.get("path")
    _validate_request(category, 0.0)
    tau = _validate_request(category, payload.get("tau", _cfg.tau(category)))
    bank = BANKS_DIR / f"{category}.npy"
    if not bank.exists():
        return {"ok": False, "error": f"bank 없음 — 먼저 학습: {category}"}
    p = Path(path).resolve() if path else None
    allowed = [ROOT.resolve(), DATA_ROOT.resolve()]
    if not p or not p.is_file() or not any(p == a or a in p.parents for a in allowed):
        return {"ok": False, "error": "허용되지 않은 이미지 경로"}
    out = await run_in_threadpool(_run_inference, bank, tau, p, True)
    score = float(out.get("score", -1.0))
    ex = out.pop("_encoded", {})
    return {"ok": True, "category": category, "score": round(score, 4), "tau": tau,
            "verdict": "NG" if score > tau else "OK", **ex}


@router.post("/analyze")
async def analyze(file: UploadFile = File(...), category: str = Form("bottle"), tau: Optional[float] = Form(None)):
    tau = _validate_request(category, tau if tau is not None else _cfg.tau(category))
    bank = BANKS_DIR / f"{category}.npy"
    if not bank.exists():
        return {"ok": False, "error": f"bank 없음: banks/{category}.npy — 먼저 학습"}
    ext = (Path(file.filename).suffix if file.filename else "") or ".png"
    save = UPLOAD_DIR / f"analyze_{uuid.uuid4().hex}{ext}"
    save.write_bytes(await file.read())

    t0 = time.perf_counter()
    out = await run_in_threadpool(_run_inference, bank, tau, save)
    lat = (time.perf_counter() - t0) * 1000.0
    score = float(out.get("score", -1.0))
    hm = out.get("heatmap")
    return {
        "ok": True, "category": category, "score": round(score, 4),
        "verdict": "NG" if score > tau else "OK", "tau": tau,
        "latency_ms": round(lat, 1),
        "heatmap_shape": list(getattr(hm, "shape", [])) if hm is not None else None,
    }
