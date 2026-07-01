"""P-core 내부 수신 엔드포인트 — P-producer → P-core 단방향 IPC.

외부 API 아님. docker-compose 내부 네트워크에서만 노출.
kind 필드로 텔레메트리 유형 구별 (record / health / ng / ws).

수신 기반 헬스: _last_seen는 POST 도착 시 갱신.
get_producer_last_seen() — /api/health에서 producer_last_seen_s 계산용.
"""
from __future__ import annotations
import threading
import time
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["internal"])

_last_seen: float = 0.0
_seen_lock = threading.Lock()


def get_producer_last_seen() -> float:
    """마지막 ingest POST 수신 시각 (monotonic)."""
    with _seen_lock:
        return _last_seen


class _IngestBody(BaseModel):
    events: List[dict]


@router.post("/internal/ingest")
async def ingest(body: _IngestBody):
    global _last_seen
    with _seen_lock:
        _last_seen = time.monotonic()
    for ev in body.events:
        kind = ev.get("kind", "")
        payload = ev.get("payload") or {}
        try:
            await _route(kind, payload)
        except Exception:
            pass
    return {"ok": True, "n": len(body.events)}


async def _route(kind: str, payload: dict) -> None:
    if kind == "ws":
        from server.ws import manager
        await manager.broadcast(payload)
    elif kind == "record":
        from aria.inspection import timeseries
        snap = payload.get("snap") or payload
        timeseries.record(
            snap,
            lane=payload.get("lane", 0),
            category=payload.get("category") or "",
        )
    elif kind == "health":
        from aria.inspection import timeseries
        timeseries.record_health(payload)
    elif kind == "ng":
        from aria.inspection.pdm_fusion import get_fusion
        get_fusion().note_ng(payload.get("asset_id"), payload.get("cell"))
