"""자산 온도·진동 트윈 프록시(T1-C C0) — 결정론적, 난수 없음.

실센서(온도·진동)가 아직 없으므로, **실 텔레메트리(infer_p95, drop_rate)와 가동시간**에
물리적으로 동기화된 결정론적 트윈 모델로 대체한다. 반드시 sim=1로 태깅해 정직성을 전파한다.
- 온도: 부하(p95)에 비례 + 열축적(포화 지수곡선). 재시작 시 elapsed=0에서 시작.
- 진동: 백프레셔(drop)에 비례 + 완만한 마모 상승(선형) → RUL이 외삽할 추세 제공.
동일 입력 → 동일 출력(§9.5 결정성). run-to-failure 실데이터가 쌓이면 이 프록시는 실채널로 교체.
"""
from __future__ import annotations
import math

# 자산별 기저/민감도 (로봇팔·비전·컨베이어). 물리 근거를 상수로 노출(블랙박스 아님).
_PROFILE = {
    "robot_arm":      {"temp0": 38.0, "kp95": 0.10, "thermal": 12.0, "vib0": 0.80, "kdrop": 0.04, "wear_per_hr": 0.35},
    "vision_camera":  {"temp0": 42.0, "kp95": 0.16, "thermal": 10.0, "vib0": 0.20, "kdrop": 0.02, "wear_per_hr": 0.10},
    "conveyor_motor": {"temp0": 36.0, "kp95": 0.04, "thermal": 8.0,  "vib0": 1.10, "kdrop": 0.09, "wear_per_hr": 0.45},
}
_TAU_S = 600.0   # 열 시정수(초)


def _base(asset_id: str) -> dict:
    for key, prof in _PROFILE.items():
        if asset_id.startswith(key):
            return prof
    return _PROFILE["robot_arm"]


def proxy(asset_id: str, infer_p95_ms: float, drop_rate: float, elapsed_s: float) -> dict:
    """결정론적 온도/진동 프록시. elapsed_s=가동 경과(초). 반환 sim=1."""
    p = _base(asset_id)
    p95 = float(infer_p95_ms or 0.0)
    drop = float(drop_rate or 0.0)
    el = max(0.0, float(elapsed_s or 0.0))
    thermal = p["thermal"] * (1.0 - math.exp(-el / _TAU_S))       # 포화 열축적
    temp_c = p["temp0"] + p["kp95"] * p95 + thermal
    wear = p["wear_per_hr"] * (el / 3600.0)                       # 완만한 선형 마모
    vib = p["vib0"] + p["kdrop"] * drop + wear
    return {"temp_c": round(temp_c, 2), "vib_rms_mm_s": round(vib, 3), "sim": 1}
