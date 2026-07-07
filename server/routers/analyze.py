"""단일 이미지 분석 라우터 — 깨끗한 PatchCore 추론(feature_bank 재사용).
/api/analyze: 이미지 업로드 + category → score/verdict/heatmap.
(VLM/오케스트레이터 기반 풀 분석은 MCP 의존이라 B3 에이전트 트랙에서 별도 검토.)
"""
import time
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, Body

from server.config import UPLOAD_DIR, BANKS_DIR, ROOT, DATA_ROOT
from aria.core.config import inference as _cfg

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze_path")
async def analyze_path(payload: dict = Body(...)):
    """서버 측 이미지 경로 분석 → score/verdict + image_b64/heatmap_b64/defect_xy(결함 3D 뷰어용)."""
    category = payload.get("category", "bottle")
    path = payload.get("path")
    tau = float(payload.get("tau", _cfg.tau(category)))
    bank = BANKS_DIR / f"{category}.npy"
    if not bank.exists():
        return {"ok": False, "error": f"bank 없음 — 먼저 학습: {category}"}
    p = Path(path).resolve() if path else None
    allowed = [ROOT.resolve(), DATA_ROOT.resolve()]
    if not p or not p.is_file() or not any(str(p).startswith(str(a)) for a in allowed):
        return {"ok": False, "error": "허용되지 않은 이미지 경로"}
    from aria.inspection.detectors import PatchCoreDetector
    from aria.inspection.result_encode import enrich_result
    det = PatchCoreDetector(str(bank), tau=tau)
    out = det.infer(str(p))
    score = float(out.get("score", -1.0))
    ex = enrich_result(str(p), out.get("heatmap"))
    return {"ok": True, "category": category, "score": round(score, 4), "tau": tau,
            "verdict": "NG" if score > tau else "OK", **ex}


@router.post("/analyze")
async def analyze(file: UploadFile = File(...), category: str = Form("bottle"), tau: Optional[float] = Form(None)):
    from aria.inspection.detectors import PatchCoreDetector
    tau = tau if tau is not None else _cfg.tau(category)
    bank = BANKS_DIR / f"{category}.npy"
    if not bank.exists():
        return {"ok": False, "error": f"bank 없음: banks/{category}.npy — 먼저 학습"}
    ext = (Path(file.filename).suffix if file.filename else "") or ".png"
    save = UPLOAD_DIR / f"analyze_{int(time.time())}{ext}"
    save.write_bytes(await file.read())

    det = PatchCoreDetector(str(bank), tau=tau)
    t0 = time.time()
    out = det.infer(str(save))
    lat = (time.time() - t0) * 1000.0
    score = float(out.get("score", -1.0))
    hm = out.get("heatmap")
    return {
        "ok": True, "category": category, "score": round(score, 4),
        "verdict": "NG" if score > tau else "OK", "tau": tau,
        "latency_ms": round(lat, 1),
        "heatmap_shape": list(getattr(hm, "shape", [])) if hm is not None else None,
    }
