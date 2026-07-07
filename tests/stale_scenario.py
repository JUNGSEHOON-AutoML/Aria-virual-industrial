"""S3b-3 stale 시나리오 테스트 — 두 층 stale 검증.

Layer 1: producer_disconnected — ingest가 오랫동안 안 온 경우
Layer 2: signal_delay — producer는 연결됐는데 특정 자산 신호가 늦는 경우

값 표기 규칙 확인:
  - stale=true여도 마지막 kpi 값은 유지 (0 리셋·보간·N/A 치환 없음)
  - age_s는 단조 증가 (시간 역전 없음)
  - reason 필드가 원인을 구분

골든 트레이스(tests/golden.json)는 stale=false 정상 경로이므로 이 파일은 별도 실행.
실행: PYTHONPATH=. python tests/stale_scenario.py
"""
from __future__ import annotations
import sys
import os
import time

# 프로젝트 루트를 sys.path에 추가 (aria.* import)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import aria.planes.stale_oracle as oracle


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def _set_last_seen(mono_ts: float):
    oracle.set_last_seen(mono_ts)


def _patch_timeseries(asset_ts_map: dict):
    """timeseries.last_health_ts_per_asset을 고정값으로 교체."""
    import aria.inspection.timeseries as ts_mod
    ts_mod._orig_last_health_ts = getattr(ts_mod, "last_health_ts_per_asset", None)
    ts_mod.last_health_ts_per_asset = lambda minutes=60: dict(asset_ts_map)


def _unpatch_timeseries():
    import aria.inspection.timeseries as ts_mod
    orig = getattr(ts_mod, "_orig_last_health_ts", None)
    if orig is not None:
        ts_mod.last_health_ts_per_asset = orig


def _stale(now_mono=None, now_wall=None):
    return oracle.get_stale_status(now_mono=now_mono, now_wall=now_wall)


# ── Layer 1: producer_disconnected ────────────────────────────────────────────

def test_layer1_disconnected():
    """ingest가 threshold 이상 안 왔을 때 → stale=True, reason='producer_disconnected'."""
    from aria.core.config import inference as _cfg
    threshold = _cfg.stale_threshold_s  # 기본 10.0s

    now_mono = time.monotonic()
    _set_last_seen(now_mono - (threshold + 30))

    status = _stale(now_mono=now_mono, now_wall=time.time())

    assert status["stale"] is True, f"Layer1: stale should be True, got {status}"
    assert status["stale_reason"] == "producer_disconnected", f"Layer1: wrong reason {status['stale_reason']}"
    assert status["producer_connected"] is False, "Layer1: producer_connected should be False"
    assert status["age_s"] is not None and status["age_s"] > threshold, f"Layer1: age_s={status['age_s']} too small"
    print(f"  [PASS] Layer1 disconnected: stale=True, age={status['age_s']}s, reason={status['stale_reason']}")


def test_layer1_connected():
    """ingest가 threshold 이내에 왔을 때 → stale=False."""
    now_mono = time.monotonic()
    _set_last_seen(now_mono - 2.0)  # 2초 전 — 정상

    _patch_timeseries({})  # 자산 없음 → Layer2 없음
    try:
        status = _stale(now_mono=now_mono, now_wall=time.time())
        assert status["stale"] is False, f"Layer1: stale should be False, got {status}"
        assert status["producer_connected"] is True, "Layer1: producer_connected should be True"
        assert status["stale_reason"] is None, f"Layer1: reason should be None, got {status['stale_reason']}"
        print(f"  [PASS] Layer1 connected: stale=False, age={status['age_s']}s")
    finally:
        _unpatch_timeseries()


# ── Layer 2: signal_delay (per-asset) ─────────────────────────────────────────

def test_layer2_signal_delay():
    """producer는 연결 중, 특정 자산 신호가 threshold 이상 안 옴 → 해당 자산만 stale."""
    from aria.core.config import inference as _cfg
    threshold = _cfg.stale_threshold_s

    now_wall = time.time()
    now_mono = time.monotonic()
    _set_last_seen(now_mono - 2.0)  # producer는 연결 중

    # cam_A: 30초 전 신호 (stale), cam_B: 1초 전 신호 (정상)
    asset_ts_map = {
        "cam_A": now_wall - (threshold + 20),
        "cam_B": now_wall - 1.0,
    }
    _patch_timeseries(asset_ts_map)
    try:
        status = _stale(now_mono=now_mono, now_wall=now_wall)

        assert status["stale"] is False, "Layer2: process-level stale should be False"
        assert status["producer_connected"] is True, "Layer2: producer should be connected"
        assets_stale = status["assets_stale"]
        assert "cam_A" in assets_stale, f"Layer2: cam_A should be stale, got {assets_stale}"
        assert assets_stale["cam_A"]["stale"] is True
        assert assets_stale["cam_A"]["reason"] == "signal_delay"
        assert "cam_B" not in assets_stale, f"Layer2: cam_B should not be stale, got {assets_stale}"
        print(f"  [PASS] Layer2 signal_delay: cam_A stale={assets_stale['cam_A']['age_s']}s, cam_B OK")
    finally:
        _unpatch_timeseries()


def test_layer2_all_fresh():
    """모든 자산이 threshold 이내 → assets_stale 빈 딕트."""
    now_wall = time.time()
    now_mono = time.monotonic()
    _set_last_seen(now_mono - 2.0)

    asset_ts_map = {
        "cam_A": now_wall - 1.0,
        "cam_B": now_wall - 3.0,
    }
    _patch_timeseries(asset_ts_map)
    try:
        status = _stale(now_mono=now_mono, now_wall=now_wall)
        assert status["stale"] is False
        assert status["assets_stale"] == {}, f"Layer2 fresh: expected empty, got {status['assets_stale']}"
        print(f"  [PASS] Layer2 all fresh: assets_stale={{}}")
    finally:
        _unpatch_timeseries()


# ── stale 정직성: 값 유지 (signalReducer 등가 Python) ────────────────────────

def test_reducer_stale_honesty():
    """stale=True여도 kpi 값(yield_rate 등)은 유지됨을 확인.
    signalReducer.js inspector_state case 핵심 로직의 Python 등가 검증.
    """
    STALE_META_KEYS = {"stale", "stale_reason", "age_s", "producer_connected", "assets_stale"}

    def apply_inspector_state(state_stale_status, msg):
        stale_status = state_stale_status
        if msg.get("stale") is not None:
            stale_status = {
                "stale": bool(msg["stale"]),
                "stale_reason": msg.get("stale_reason"),
                "age_s": msg.get("age_s"),
                "producer_connected": msg.get("producer_connected", not msg["stale"]),
                "assets_stale": msg.get("assets_stale", {}),
            }
        kpi_payload = {k: v for k, v in msg.items() if k not in STALE_META_KEYS}
        return kpi_payload, stale_status

    # 정상 메시지
    initial_stale = {"stale": False, "stale_reason": None, "age_s": None, "producer_connected": True, "assets_stale": {}}
    msg_ok = {
        "type": "inspector_state", "yield_rate": 0.95, "n_ok": 100, "n_ng": 5,
        "stale": False, "stale_reason": None, "age_s": 1.2, "producer_connected": True,
    }
    kpi, stale = apply_inspector_state(initial_stale, msg_ok)
    assert "stale" not in kpi, "stale meta must be removed from kpi"
    assert kpi["yield_rate"] == 0.95, "yield_rate must survive"
    assert stale["stale"] is False

    # stale 메시지 — yield_rate 유지가 핵심
    msg_stale = {
        "type": "inspector_state", "yield_rate": 0.95, "n_ok": 100, "n_ng": 5,
        "stale": True, "stale_reason": "producer_disconnected", "age_s": 35.0, "producer_connected": False,
    }
    kpi2, stale2 = apply_inspector_state(stale, msg_stale)
    assert kpi2["yield_rate"] == 0.95, f"stale=True여도 yield_rate 유지 필수, got {kpi2['yield_rate']}"
    assert "stale" not in kpi2, "stale meta must not bleed into kpi"
    assert stale2["stale"] is True
    assert stale2["stale_reason"] == "producer_disconnected"
    assert stale2["age_s"] == 35.0
    assert stale2["producer_connected"] is False
    print("  [PASS] reducer 정직성: stale=True여도 yield_rate 유지, stale 메타 kpi 분리")


# ── never_seen: _last_seen=0 (첫 기동, 아직 연결 없음) ──────────────────────

def test_never_connected():
    """P-producer가 한 번도 신호를 안 보낸 상태 → stale=True, age_s=None."""
    _set_last_seen(0.0)
    _patch_timeseries({})
    try:
        status = _stale()
        assert status["stale"] is True, f"never_connected: should be stale, got {status}"
        assert status["producer_connected"] is False
        assert status["age_s"] is None, f"never_connected: age_s should be None, got {status['age_s']}"
        assert status["stale_reason"] == "producer_disconnected"
        print(f"  [PASS] never_connected: stale=True, age_s=None (아직 첫 신호 없음)")
    finally:
        _unpatch_timeseries()


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("S3b-3 stale 시나리오 테스트")
    print("=" * 60)

    tests = [
        ("Layer1 disconnected", test_layer1_disconnected),
        ("Layer1 connected (stale=False)", test_layer1_connected),
        ("Layer2 signal_delay (per-asset)", test_layer2_signal_delay),
        ("Layer2 all fresh", test_layer2_all_fresh),
        ("Reducer stale 정직성", test_reducer_stale_honesty),
        ("Never connected (첫 기동)", test_never_connected),
    ]

    passed = failed = 0
    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"결과: {passed}/{len(tests)} PASS  {failed} FAIL")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
