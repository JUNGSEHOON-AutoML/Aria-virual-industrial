"""건전성 지수 H & 잔여수명 RUL(T1-C C2) — 투명 열화 모델, 결정론적.

훈련 데이터 없이 방어 가능한 화이트박스:
  H = clamp(1 − Σ_i w_i·relu(z_i) / K, 0, 1)   (기준선을 나쁜 방향으로 벗어난 만큼만 감점)
  RUL = H(t) 선형 외삽으로 H_fail 도달 시각 − now  (밴드 = 적합 잔차 기반 CI)
정직성: RUL은 항상 {est, lo, hi, model} + 확인요망. 물리 단독 confidence ≤ 0.60(교차확증은 fusion에서 상향).
데이터 기반(Weibull/생존모형)은 run-to-failure 축적 후 별도 트랙.
"""
from __future__ import annotations
import math

H_FAIL = 0.30       # 고장 임계(기본)
K = 3.0             # 정규화 상수(z≈3 누적 시 H→0)
PHYS_CONF_CAP = 0.60

# 자산별 가중(어느 신호가 그 자산 건전성을 지배하는가) — 물리 근거를 상수로 노출.
PROFILE_WEIGHTS = {
    "robot_arm":      {"vib_rms_mm_s": 0.55, "temp_c": 0.30, "infer_p95_ms": 0.0,  "drop_rate": 0.15},
    "vision_camera":  {"vib_rms_mm_s": 0.0,  "temp_c": 0.30, "infer_p95_ms": 0.55, "drop_rate": 0.15},
    "conveyor_motor": {"vib_rms_mm_s": 0.35, "temp_c": 0.10, "infer_p95_ms": 0.0,  "drop_rate": 0.55},
}
# 특징명 → asset_health 컬럼(레벨) 매핑
_LEVEL_COLS = ["vib_rms_mm_s", "temp_c", "infer_p95_ms", "drop_rate"]
# 상승이 나쁨을 뜻하는 선행 기울기(리포트용)
_SLOPE_OF = {"vib_rms_mm_s": "rms_slope", "temp_c": "temp_slope",
             "infer_p95_ms": "p95_creep", "drop_rate": "drop_trend"}


def _profile(asset_id: str) -> dict:
    for key, w in PROFILE_WEIGHTS.items():
        if asset_id.startswith(key):
            return w
    return PROFILE_WEIGHTS["robot_arm"]


def _median(xs):
    s = sorted(xs); n = len(s)
    if n == 0:
        return 0.0
    m = n // 2
    return s[m] if n % 2 else (s[m - 1] + s[m]) / 2.0


def _mad(xs, med):
    if not xs:
        return 0.0
    return 1.4826 * _median([abs(x - med) for x in xs])


def _lstsq(xs, ys):
    """(slope, intercept, r2, resid_std) — hr 단위 xs."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-12:
        return None
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    resid = [ys[i] - (slope * xs[i] + intercept) for i in range(n)]
    ss_res = sum(r * r for r in resid)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    resid_std = math.sqrt(ss_res / max(1, n - 2)) if n > 2 else 0.0
    return slope, intercept, r2, resid_std


def _h_of(sample: dict, base: dict, scale: dict, weights: dict) -> float:
    """단일 표본의 건전성 지수(포인트별). 나쁜 방향 편차만 relu 감점."""
    penalty = 0.0
    for col in _LEVEL_COLS:
        w = weights.get(col, 0.0)
        if w <= 0:
            continue
        s = scale.get(col) or 0.0
        if s <= 1e-9:
            continue
        z = (float(sample.get(col) or 0.0) - base.get(col, 0.0)) / s
        penalty += w * max(0.0, z)      # relu: 기준선보다 나쁠 때만
    return max(0.0, min(1.0, 1.0 - penalty / K))


def estimate(rows: list, asset_id: str, features: dict | None = None,
             h_fail: float = H_FAIL, nmin: int = 4) -> dict | None:
    """윈도우 rows(recent_health) → {health_index, rul{est,lo,hi,model}, confidence, leading_signals}.
    데이터 부족 시 None(가설 미생성, 정직성)."""
    n = len(rows)
    if n < nmin:
        return None
    weights = _profile(asset_id)

    # 기준선(창 내 안정 p50) + 로버스트 스케일(MAD)
    cols = {c: [float(r.get(c) or 0.0) for r in rows] for c in _LEVEL_COLS}
    base = {c: _median(v) for c, v in cols.items()}
    scale = {c: _mad(v, base[c]) for c, v in cols.items()}

    ts_hr = [(float(r.get("ts", 0)) - float(rows[0].get("ts", 0))) / 3600.0 for r in rows]
    h_series = [_h_of(r, base, scale, weights) for r in rows]
    h_now = h_series[-1]

    fit = _lstsq(ts_hr, h_series)
    now_hr = ts_hr[-1]

    # 기본 RUL 결과(악화 추세 없으면 '임박 아님')
    rul = {"est_hours": None, "lo": None, "hi": None, "model": "linear"}
    conf_base = 0.0
    leading = _leading_signals(features)

    if fit is not None:
        slope, intercept, r2, resid_std = fit
        if slope < -1e-6:   # H 하강(열화 진행) → 외삽
            def t_at(hf):
                return (hf - intercept) / slope   # hr(창 시작 기준)
            t_fail = t_at(h_fail)
            est = max(0.0, t_fail - now_hr)
            # 밴드: 잔차로 H_fail 교차의 불확실성 근사(±resid_std를 절편에 반영)
            t_lo = t_at(h_fail + resid_std)   # 더 이른 고장(보수적)
            t_hi = t_at(h_fail - resid_std)
            lo = max(0.0, min(est, t_lo - now_hr))
            hi = max(est, t_hi - now_hr)
            rul = {"est_hours": round(est, 1), "lo": round(lo, 1),
                   "hi": round(hi, 1), "model": "linear"}
            # 물리 신뢰도: 적합 R² × 표본 충분성 (물리 단독 ≤ 0.60)
            conf_base = max(0.0, min(1.0, r2)) * min(1.0, n / 8.0)
        else:
            # 개선/평탄 → 임박 고장 없음(정직: RUL 미외삽)
            conf_base = max(0.0, min(1.0, (fit[2] if fit else 0.0))) * min(1.0, n / 8.0) * 0.3

    confidence = round(min(PHYS_CONF_CAP, conf_base), 3)
    # sim 채널 여부(정직성 노트)
    any_sim = any(int(r.get("sim", 0)) == 1 for r in rows)
    return {
        "asset": asset_id,
        "health_index": round(h_now, 3),
        "rul": rul,
        "confidence": confidence,
        "leading_signals": leading,
        "corroborated": False,   # fusion 단계에서 갱신
        "n": n,
        "sim_channels": any_sim,
        "note": "확인요망(단정 아님)" + ("· 온도/진동 트윈 프록시(sim)" if any_sim else ""),
    }


def _leading_signals(features: dict | None) -> list:
    """상승(나쁜 방향) 기울기가 있는 선행 신호명 목록."""
    if not features:
        return []
    out = []
    for col, key in _SLOPE_OF.items():
        v = features.get(key)
        if v is not None and v > 0:
            out.append(key)
    return out
