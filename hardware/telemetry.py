"""실측 텔레메트리 — GPU 온도/VRAM/util 분류 레이어 (HW-1 monitor 위에 구축).

hardware.monitor.get_snapshot()(원시 수치)을 재사용해 라인 연동용 파생값을 더한다:
  - thermal: cool(<55) | warm(<70) | hot(<84) | critical(>=84) °C
  - load:    idle | light | training (util>=50% & vram>=40% → training)
  - summary: 대표 GPU 1개로 요약(라인 상태기계·3D 표시가 소비)

불변식:
  - 읽기전용. GPU/pynvml/psutil 부재 시 gpus=[], mode="cpu"로 절대 죽지 않음.
  - 분류 임계값은 결정론(아래 상수) — LLM/추정 없음.
"""
from __future__ import annotations

from hardware.monitor import get_snapshot

# 발열 구간 (°C) — IMPLEMENTATION_SPEC §3-3
THERMAL_COOL_C = 55
THERMAL_WARM_C = 70
THERMAL_HOT_C = 84

# 부하 분류 임계 — util·vram 동시 충족 시 training
LOAD_TRAIN_UTIL_PCT = 50
LOAD_TRAIN_VRAM_PCT = 40
LOAD_LIGHT_UTIL_PCT = 10


def classify_thermal(temp_c) -> str:
    """GPU 온도 → 발열 단계. None(측정 불가)은 cool로 안전 폴백."""
    if temp_c is None:
        return "cool"
    t = float(temp_c)
    if t < THERMAL_COOL_C:
        return "cool"
    if t < THERMAL_WARM_C:
        return "warm"
    if t < THERMAL_HOT_C:
        return "hot"
    return "critical"


def classify_load(util_pct, vram_pct) -> str:
    """GPU util/VRAM → 부하 단계 (idle | light | training)."""
    u = float(util_pct or 0)
    v = float(vram_pct or 0)
    if u >= LOAD_TRAIN_UTIL_PCT and v >= LOAD_TRAIN_VRAM_PCT:
        return "training"
    if u >= LOAD_LIGHT_UTIL_PCT or v >= LOAD_TRAIN_VRAM_PCT:
        return "light"
    return "idle"


_THERMAL_RANK = {"cool": 0, "warm": 1, "hot": 2, "critical": 3}
_LOAD_RANK = {"idle": 0, "light": 1, "training": 2}


def get_telemetry() -> dict:
    """텔레메트리 스냅샷 (IMPLEMENTATION_SPEC §3-3 스키마).

    monitor 원시값 + gpu별 vram_pct/thermal/load + summary(최악 GPU 기준).
    """
    snap = get_snapshot()
    gpus = []
    for g in snap.get("gpus") or []:
        total = g.get("vram_total_mb") or 0
        used = g.get("vram_used_mb") or 0
        vram_pct = round(used / total * 100, 1) if total else 0.0
        gpus.append({
            **g,
            "vram_pct": vram_pct,
            "thermal": classify_thermal(g.get("temp_c")),
            "load": classify_load(g.get("util_pct"), vram_pct),
        })

    if gpus:
        # 대표 = 발열이 가장 높은 GPU (동률이면 부하 높은 쪽) — 안전측 요약
        rep = max(gpus, key=lambda g: (_THERMAL_RANK[g["thermal"]], _LOAD_RANK[g["load"]]))
        # 부하 요약은 전체 GPU 중 최대 부하 (한 장이라도 학습 중이면 training)
        load = max((g["load"] for g in gpus), key=lambda l: _LOAD_RANK[l])
        summary = {
            "has_gpu": True, "mode": "gpu", "n_gpus": len(gpus),
            "gpu_name": rep.get("name"), "temp_c": rep.get("temp_c"),
            "vram_pct": rep.get("vram_pct"), "util_pct": rep.get("util_pct"),
            "thermal": rep["thermal"], "load": load,
            "training": load == "training",
        }
    else:
        summary = {
            "has_gpu": False, "mode": "cpu", "n_gpus": 0,
            "gpu_name": None, "temp_c": None, "vram_pct": None, "util_pct": None,
            "thermal": "cool", "load": "idle", "training": False,
        }

    return {**snap, "gpus": gpus, "summary": summary}
