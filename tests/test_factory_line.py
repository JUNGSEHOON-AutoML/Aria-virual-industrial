"""FactoryLine + telemetry 헤드리스 회귀 (GPU/torch 불필요 — 분류·상태기계는 순수).

실행: pytest tests/test_factory_line.py -q
"""
import time

from aria.planes.factory_line import FactoryLine
from hardware.telemetry import classify_thermal, classify_load


def _feed(fl, n=10, ng_every=2, tact_s=1.4):
    t0 = time.time()
    for i in range(n):
        ng = ng_every and (i % ng_every == 1)
        fl.on_result(part_id=f"P{i}", verdict="NG" if ng else "OK",
                     score=0.6 if ng else 0.2, latency_ms=42, ts=t0 + i * tact_s)


def test_thermal_classification():
    assert classify_thermal(None) == "cool"
    assert classify_thermal(40) == "cool"
    assert classify_thermal(60) == "warm"
    assert classify_thermal(75) == "hot"
    assert classify_thermal(90) == "critical"


def test_load_classification():
    assert classify_load(80, 50) == "training"
    assert classify_load(5, 2) == "idle"
    assert classify_load(30, 10) == "light"
    assert classify_load(None, None) == "idle"


def test_line_metrics_and_qa_alert():
    fl = FactoryLine()
    _feed(fl, n=10, ng_every=2)          # 불량률 0.5 > 목표 0.3
    s = fl.snapshot()
    assert s["stats"]["total"] == 10 and s["stats"]["ok"] == 5 and s["stats"]["ng"] == 5
    assert s["stats"]["line_status"] == "ALERT"
    assert s["line"]["equipment_status"] == "QA_ALERT"
    assert abs(s["line"]["tact_time_s"] - 1.4) < 0.05          # EMA 수렴
    assert s["line"]["transit_time_s"] == 8.0                  # 4m / 0.5mps
    assert s["line"]["throughput_per_min"] > 0


def test_warmup_then_normal():
    fl = FactoryLine()
    _feed(fl, n=2, ng_every=0)
    assert fl.snapshot()["stats"]["line_status"] == "WARMUP"
    _feed_more = [fl.on_result(part_id=f"Q{i}", verdict="OK", ts=time.time()) for i in range(4)]
    assert fl.snapshot()["stats"]["line_status"] == "NORMAL"
    assert fl.snapshot()["line"]["equipment_status"] == "RUNNING"


def test_thermal_derating_and_fault():
    fl = FactoryLine()
    _feed(fl, n=4, ng_every=0)
    fl.set_telemetry({"thermal": "hot", "training": False})
    s = fl.snapshot()
    assert abs(s["line"]["conveyor_speed_mps"] - 0.5 * 0.7) < 1e-6   # 발열 감속
    fl.set_telemetry({"thermal": "critical", "training": False})
    s = fl.snapshot()
    assert s["line"]["equipment_status"] == "THERMAL_FAULT"
    assert abs(s["line"]["conveyor_speed_mps"] - 0.5 * 0.35) < 1e-6


def test_training_linkage():
    fl = FactoryLine()
    _feed(fl, n=4, ng_every=0)
    # ① GPU 부하 실측으로 학습 감지
    fl.set_telemetry({"thermal": "warm", "training": True})
    assert fl.snapshot()["line"]["equipment_status"] == "MODEL_TRAINING"
    # ② WS training 이벤트로도 감지 (텔레메트리보다 우선 유지)
    fl.set_telemetry({"thermal": "cool", "training": False})
    fl.notify_training("running")
    assert fl.snapshot()["line"]["equipment_status"] == "MODEL_TRAINING"
    fl.notify_training("done")
    assert fl.snapshot()["line"]["equipment_status"] == "RUNNING"


def test_dedupe_and_skipped():
    fl = FactoryLine()
    fl.on_result(part_id="X1", verdict="OK")
    fl.on_result(part_id="X1", verdict="OK")           # 중복 무시
    fl.on_result(part_id="X2", verdict="SKIPPED")      # 보류 별도 집계
    fl.on_result(part_id="X3", verdict="ERROR")        # 무시
    s = fl.snapshot()["stats"]
    assert s["total"] == 2 and s["ok"] == 1 and s["deferred"] == 1


def test_configure_and_reset():
    fl = FactoryLine()
    cfg = fl.configure(base_speed_mps=1.0, line_length_m=6.0, defect_target=0.1)
    assert cfg["base_speed_mps"] == 1.0
    _feed(fl, n=4, ng_every=0)
    assert fl.snapshot()["line"]["transit_time_s"] == 6.0
    fl.reset()
    s = fl.snapshot()["stats"]
    assert s["total"] == 0 and s["line_status"] == "WARMUP"
