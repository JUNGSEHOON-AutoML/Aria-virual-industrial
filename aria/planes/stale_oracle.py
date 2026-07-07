"""두 층 stale 판정 오라클 — FastAPI 의존 없음 (테스트·서버 공용).

Layer 1 (프로세스): producer_connected = now_mono - _last_seen < threshold
  False면 전체 stale, reason="producer_disconnected"
Layer 2 (자산): producer_connected=True인데 자산별 last_health_ts 초과
  해당 자산만 stale, reason="signal_delay"

단일 임계값(stale_threshold_s)이 두 층에 동일 적용.
Layer 1은 monotonic, Layer 2는 wallclock — NTP 점프 영향 없음.

값 표기 규칙:
  stale=True여도 마지막 실측값 유지 — 0 리셋·보간·N/A 치환 금지.
  이 모듈은 판정만 한다; 값 유지는 호출측(internal._route, heartbeat)이 담당.
"""
from __future__ import annotations
import threading
import time
from typing import Optional

# ── 수신 기반 헬스 상태 (monotonic) ─────────────────────────────────────────
_last_seen: float = 0.0
_seen_lock = threading.Lock()

# 마지막 inspector_state 페이로드 — stale heartbeat 재사용
_last_ws_state: Optional[dict] = None
_ws_state_lock = threading.Lock()


def set_last_seen(mono_ts: float) -> None:
    """ingest POST 수신 시 갱신."""
    global _last_seen
    with _seen_lock:
        _last_seen = mono_ts


def get_last_seen() -> float:
    with _seen_lock:
        return _last_seen


def set_last_ws_state(payload: dict) -> None:
    """마지막 inspector_state 보관 (stale heartbeat 재사용용)."""
    global _last_ws_state
    with _ws_state_lock:
        _last_ws_state = payload


def get_last_ws_state() -> Optional[dict]:
    with _ws_state_lock:
        return _last_ws_state


def get_stale_status(
    now_mono: Optional[float] = None,
    now_wall: Optional[float] = None,
) -> dict:
    """두 층 stale 계산.

    반환:
      {
        stale: bool,
        stale_reason: None | 'producer_disconnected' | 'signal_delay',
        age_s: float | None,        # None = 아직 첫 신호 없음
        producer_connected: bool,
        assets_stale: {asset_id: {stale:True, age_s:float, reason:str}},
      }
    Layer 1이 False(단절)면 assets_stale은 항상 {} — 개별 확인 불필요.
    """
    if now_mono is None:
        now_mono = time.monotonic()
    if now_wall is None:
        now_wall = time.time()

    from aria.core.config import inference as _cfg
    threshold = _cfg.stale_threshold_s

    last_seen = get_last_seen()
    process_age_s = (now_mono - last_seen) if last_seen > 0 else None
    producer_connected = (process_age_s is not None and process_age_s < threshold)

    if not producer_connected:
        return {
            "stale": True,
            "stale_reason": "producer_disconnected",
            "age_s": round(process_age_s, 1) if process_age_s is not None else None,
            "producer_connected": False,
            "assets_stale": {},
        }

    # Layer 2 (producer 연결 중 — 자산별 신호 확인)
    try:
        from aria.inspection.timeseries import last_health_ts_per_asset
        last_ts_map = last_health_ts_per_asset(minutes=5)
    except Exception:
        last_ts_map = {}

    assets_stale: dict = {}
    for asset_id, last_ts in last_ts_map.items():
        asset_age = now_wall - last_ts
        if asset_age > threshold:
            assets_stale[asset_id] = {
                "stale": True,
                "age_s": round(asset_age, 1),
                "reason": "signal_delay",
            }

    return {
        "stale": False,
        "stale_reason": None,
        "age_s": round(process_age_s, 1),
        "producer_connected": True,
        "assets_stale": assets_stale,
    }
