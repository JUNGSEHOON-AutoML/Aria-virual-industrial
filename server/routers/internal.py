"""P-core 내부 수신 엔드포인트 — P-producer → P-core 단방향 IPC.

외부 API 아님. docker-compose 내부 네트워크에서만 노출.
kind 필드로 텔레메트리 유형 구별 (record / health / ng / ws).

멱등성 (§5 중복 0 보장):
  각 이벤트는 P-producer 측 단조 seq 번호를 가짐.
  P-core는 최근 5000개 seq를 rolling window로 추적 — 재전송 dedup.

수신 기반 헬스 + stale 두 층 (S3b-3):
  Layer 1 — 프로세스: producer_connected = 마지막 ingest POST 도착 기준
             producer_connected=false → 전 레인·전 자산 일괄 stale (reason="producer_disconnected")
  Layer 2 — 자산: producer_connected=true인데 특정 자산 신호 안 옴
             그 자산만 stale (reason="signal_delay")
  두 층이 다른 원인을 가지므로 UI에 reason 필드로 구분해서 전달.

비파괴 확장:
  기존 WS 메시지(inspector_state 등)에 stale·age_s·stale_reason 필드 부가.
  기존 소비자가 이 필드를 모르고도 지금과 동일하게 동작 (optional field).

값 표기 규율:
  stale=true일 때도 마지막 실측값을 유지 — 0 리셋·보간·N/A 치환 금지.
  마지막값 + age_s가 가장 정직한 표기.
"""
from __future__ import annotations
import collections
import threading
import time
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["internal"])

# ── stale oracle (FastAPI 의존 없음 — 테스트 공용) ─────────────────────────
from aria.planes.stale_oracle import (
    set_last_seen as _oracle_set_last_seen,
    get_last_seen as _oracle_get_last_seen,
    set_last_ws_state as _oracle_set_ws_state,
    get_last_ws_state,
    get_stale_status,
)


def get_producer_last_seen() -> float:
    """마지막 ingest POST 수신 시각 (monotonic)."""
    return _oracle_get_last_seen()


# ── seq rolling dedup (멱등성) ──────────────────────────────────────────────
_dedup_q: collections.deque = collections.deque(maxlen=5000)
_dedup_set: set = set()
_dedup_lock = threading.Lock()


def _is_dup(seq) -> bool:
    if seq is None:
        return False
    with _dedup_lock:
        if seq in _dedup_set:
            return True
        if len(_dedup_q) == _dedup_q.maxlen:
            old = _dedup_q[0]
            _dedup_set.discard(old)
        _dedup_q.append(seq)
        _dedup_set.add(seq)
        return False


# ── 수신 엔드포인트 ─────────────────────────────────────────────────────────

class _IngestBody(BaseModel):
    events: List[dict]


@router.post("/internal/ingest")
async def ingest(body: _IngestBody):
    _oracle_set_last_seen(time.monotonic())

    processed = 0
    for ev in body.events:
        seq = ev.get("seq")
        if _is_dup(seq):
            continue
        kind = ev.get("kind", "")
        payload = ev.get("payload") or {}
        try:
            await _route(kind, payload)
            processed += 1
        except Exception:
            pass

    return {"ok": True, "n": len(body.events), "processed": processed}


async def _route(kind: str, payload: dict) -> None:
    if kind == "ws":
        from server.ws import manager
        enriched = _inject_stale(payload)
        # inspector_state만 last_ws_state에 보관 (heartbeat 재사용)
        if payload.get("type") == "inspector_state":
            _oracle_set_ws_state(enriched)
        await manager.broadcast(enriched)
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


def _inject_stale(payload: dict) -> dict:
    """WS 메시지에 stale 컨텍스트 부가 — 비파괴(기존 필드 유지, optional 필드 추가).
    값 유지 규칙: stale=true여도 기존 값 그대로. 0 리셋·N/A 치환 없음."""
    status = get_stale_status()
    return {
        **payload,
        "stale": status["stale"],
        "stale_reason": status["stale_reason"],
        "age_s": status["age_s"],
        "producer_connected": status["producer_connected"],
    }
