"""ARIA config package — backbone/model sub-modules + inference/pdm/production runtime settings (T2-A S1).

Runtime inference settings (env → default):
  from aria.core.config import inference, pdm, production, reload
  inference.tau_default, inference.tau(category), inference.lane_hz, ...
"""
from __future__ import annotations
import os


def _f(key: str, default: float) -> float:
    v = os.environ.get(key)
    return float(v) if v is not None else default


def _i(key: str, default: int) -> int:
    v = os.environ.get(key)
    return int(v) if v is not None else default


def _s(key: str, default: str) -> str:
    return os.environ.get(key, default)


class InferenceConfig:
    """추론 파이프라인 파라미터 — env로 교체 가능."""
    tau_default: float
    queue_depth: int
    n_workers: int
    lane_hz: float
    single_hz: float
    state_pump_hz: float
    lane_pump_hz: float
    yolo_conf: float
    snapshot_interval_s: float

    def __init__(self) -> None:
        self.tau_default = _f("ARIA_TAU", 0.5)
        self.queue_depth = _i("ARIA_QUEUE_DEPTH", 4)
        self.n_workers = _i("ARIA_N_WORKERS", 1)
        self.lane_hz = _f("ARIA_LANE_HZ", 6.0)
        self.single_hz = _f("ARIA_SINGLE_HZ", 20.0)
        self.state_pump_hz = _f("ARIA_STATE_PUMP_HZ", 5.0)
        self.lane_pump_hz = _f("ARIA_LANE_PUMP_HZ", 4.0)
        self.yolo_conf = _f("ARIA_YOLO_CONF", 0.25)
        self.snapshot_interval_s = _f("ARIA_SNAPSHOT_INTERVAL", 2.0)
        self.stale_threshold_s = _f("ARIA_STALE_THRESHOLD", 10.0)

    def tau(self, category: str | None = None) -> float:
        cat_env = f"ARIA_TAU_{(category or '').upper()}" if category else None
        if cat_env:
            v = os.environ.get(cat_env)
            if v is not None:
                return float(v)
        return self.tau_default


class PdMConfig:
    """PdM 융합 서비스 설정."""
    fusion_interval_s: float

    def __init__(self) -> None:
        self.fusion_interval_s = _f("ARIA_PDM_INTERVAL", 5.0)


class ProductionConfig:
    """SKU·시프트 컨텍스트 설정."""
    sku: str
    shift: str

    def __init__(self) -> None:
        self.sku = _s("ARIA_SKU", "default")
        self.shift = _s("ARIA_SHIFT", "day")


# 모듈 싱글톤
inference = InferenceConfig()
pdm = PdMConfig()
production = ProductionConfig()


def reload() -> None:
    """env 변경 후 설정 재로드."""
    global inference, pdm, production
    inference = InferenceConfig()
    pdm = PdMConfig()
    production = ProductionConfig()
