"""ARIA 로봇 물리 환경 (R-1).

FactoryEnv: MuJoCo 듀얼암 검사공장 환경. Gym 스타일 reset()/step() 인터페이스.
randomization: 프론트 `sim/randomization.js`의 seam을 백엔드로 이식한 도메인 랜덤화.
"""
from .randomization import RANGES, sample_scene_params  # noqa: F401

__all__ = ["RANGES", "sample_scene_params", "FactoryEnv"]


def __getattr__(name):
    # FactoryEnv는 mujoco 의존 → 지연 임포트(미설치 환경에서 패키지 임포트 자체는 깨지지 않게).
    if name == "FactoryEnv":
        from .factory_env import FactoryEnv
        return FactoryEnv
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
