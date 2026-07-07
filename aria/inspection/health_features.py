"""추세 특징 추출(T1-C C1) — 순수·결정론적·설명 가능(블랙박스 금지).

recent_health() 윈도우에서 자산별 선행 특징만 뽑는다. 난수 없음 → 동일 입력·동일 출력.
데이터 부족(N<Nmin) 시 해당 특징 null → 하류가 가설 미생성(정직성, §2/§9.2).
프론트 미러: frontend/src/hmi/scene/healthFeatures.js (동일 규칙, Node 헤드리스 검증).
"""
from __future__ import annotations

NMIN = 4          # 특징 산출 최소 표본
_MS_PER_HR = 3600_000.0


def _lstsq_slope(ts_ms: list, ys: list) -> float | None:
    """최소제곱 기울기(단위: y / hour). ts는 ms. 분산 0이면 None."""
    n = len(ts_ms)
    if n < 2:
        return None
    # 시간축을 시간(hr) 단위로 (수치 안정)
    xs = [(t - ts_ms[0]) / _MS_PER_HR for t in ts_ms]
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-12:
        return None
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return sxy / sxx


def _median(xs: list) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    m = n // 2
    return s[m] if n % 2 else (s[m - 1] + s[m]) / 2.0


def _mad(xs: list, med: float) -> float:
    """중앙값 절대편차(로버스트 산포). 1.4826=정규 일치 상수."""
    if not xs:
        return 0.0
    return 1.4826 * _median([abs(x - med) for x in xs])


def extract(rows: list, baseline: dict | None = None, nmin: int = NMIN) -> dict:
    """윈도우 rows(recent_health 형식) → 자산 특징 dict.
    rows: [{ts, temp_c, vib_rms_mm_s, infer_p95_ms, drop_rate, ...}] (ts 초 단위 가정, ms로 승격).
    baseline: {rms_level, temp_c, infer_p95_ms, drop_rate} 정상 스코프 p50(없으면 창 내 p50).
    반환: 특징값 + z(로버스트 정규화) + baseline + n. 데이터 부족 특징은 None.
    """
    n = len(rows)
    if n == 0:
        return {"n": 0, "rms_level": None, "rms_slope": None, "temp_slope": None,
                "p95_creep": None, "drop_trend": None, "z": {}, "baseline": {}}

    ts_ms = [float(r.get("ts", 0)) * 1000.0 for r in rows]
    vib = [float(r.get("vib_rms_mm_s") or 0.0) for r in rows]
    temp = [float(r.get("temp_c") or 0.0) for r in rows]
    p95 = [float(r.get("infer_p95_ms") or 0.0) for r in rows]
    drop = [float(r.get("drop_rate") or 0.0) for r in rows]

    enough = n >= nmin
    rms_level = _median(vib) if n else None
    rms_slope = _lstsq_slope(ts_ms, vib) if enough else None
    temp_slope = _lstsq_slope(ts_ms, temp) if enough else None
    p95_creep = _lstsq_slope(ts_ms, p95) if enough else None
    drop_trend = _lstsq_slope(ts_ms, drop) if enough else None

    # 기준선: 주어지면 사용, 없으면 창 내 p50
    base = baseline or {
        "rms_level": _median(vib), "temp_c": _median(temp),
        "infer_p95_ms": _median(p95), "drop_rate": _median(drop),
    }
    # 로버스트 z (레벨 특징만; 기울기는 이미 추세라 그대로 노출)
    z = {}
    if enough:
        z["rms_level"] = _z(vib, base.get("rms_level"))
        z["temp_c"] = _z(temp, base.get("temp_c"))
        z["infer_p95_ms"] = _z(p95, base.get("infer_p95_ms"))
        z["drop_rate"] = _z(drop, base.get("drop_rate"))

    return {
        "n": n,
        "rms_level": _round(rms_level), "rms_slope": _round(rms_slope),
        "temp_slope": _round(temp_slope), "p95_creep": _round(p95_creep),
        "drop_trend": _round(drop_trend),
        "z": {k: _round(v) for k, v in z.items()},
        "baseline": {k: _round(v) for k, v in base.items()},
    }


def _z(xs: list, base) -> float | None:
    if base is None or not xs:
        return None
    med = _median(xs)
    mad = _mad(xs, med)
    if mad <= 1e-9:
        return 0.0
    return (med - base) / mad


def _round(v):
    return None if v is None else round(v, 4)
