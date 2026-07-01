#!/usr/bin/env python3
"""골든 트레이스 하니스 — S2 착수 전 기준선 캡처 / 이후 무회귀 검증.

설계 원칙:
  - 입력 고정: MockDriver(seed=7) + mock_infer_factory(fixed 40ms) → 비결정론 없음.
  - 헬스/RUL: asset_proxy.proxy()를 고정 elapsed_s 시퀀스로 직접 호출 → DB 상태 무관.
  - SKIPPED 제어: trigger 간격 50ms, infer 40ms → 큐 드레인 보장 → SKIPPED=0 기준선.
  - float 정밀도: 소수점 4자리 반올림 후 비교(부동소수점 노이즈 제거).

사용:
  python tests/golden_trace.py --capture   # → tests/golden.json 저장
  python tests/golden_trace.py --verify    # → golden.json과 diff, 0건이어야 S2 착수 가능
  python tests/golden_trace.py --show      # → 현재 실행 결과만 출력(저장/비교 없음)
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
GOLDEN_PATH = Path(__file__).parent / "golden.json"
VERSION = "s1-post"  # S2 착수 시 "s2-post"로 갱신

# ─── 파이프라인 파라미터 (고정 — S2 이후에도 동일) ───
SEED = 7
N_FRAMES = 30
TAU = 0.5          # config.inference.tau_default 기본값
TRIGGER_INTERVAL_S = 0.10   # 100ms → infer(40ms)의 2.5× → 큐 항상 드레인, SKIPPED=0 보장
QUEUE_DEPTH = 4
N_WORKERS = 1

# ─── 헬스 파라미터 (고정) ───
ASSET_ID = "robot_arm"
T0_MS = 1_700_000_000_000   # 고정 기준 타임스탬프(ms) — 절대 변경 금지
HEALTH_INTERVALS_S = [i * 30.0 for i in range(12)]   # 0, 30, 60 … 330s
INFER_P95_MS = 50.0
DROP_RATE = 0.01


def _r(v, d=4):
    """float None-safe 반올림."""
    return round(float(v), d) if v is not None else None


def run_pipeline() -> dict:
    """고정 시드 파이프라인 30프레임 → 부분별 결과 + 집계."""
    sys.path.insert(0, str(ROOT))
    from aria.inspection.async_pipeline import AsyncPipeline, MockDriver, mock_infer_factory

    driver = MockDriver(grab_ms=0.0, seed=SEED)   # grab_ms=0 → 타이밍 노이즈 제거
    infer_fn = mock_infer_factory(lambda: 40.0)

    results_out = []
    telemetry_msgs = []

    def tele_cb(msg):
        telemetry_msgs.append(msg)

    pipe = AsyncPipeline(
        driver, infer_fn, tau=TAU,
        queue_capacity=QUEUE_DEPTH, n_workers=N_WORKERS,
        telemetry_cb=tele_cb,
    )
    pipe.start()

    for i in range(N_FRAMES):
        pipe.trigger(part_id=f"P{i:03d}")
        time.sleep(TRIGGER_INTERVAL_S)

    # 마지막 프레임이 처리될 때까지 대기 (infer 40ms + margin)
    time.sleep(0.30)
    snap = pipe.snapshot()
    raw_results = list(pipe.results())
    pipe.stop()

    for r in raw_results:
        results_out.append({
            "part_id": r.part_id,
            "verdict": r.verdict,
            "score": _r(r.score),
        })

    hold_count = snap.get("n_skipped", 0)
    return {
        "parts": results_out,
        "aggregate": {
            "n_ok": snap.get("n_ok", 0),
            "n_ng": snap.get("n_ng", 0),
            "n_skipped": hold_count,
            "hold_count": hold_count,
            "oee": _r(snap.get("oee")),
            "availability": _r(snap.get("availability")),
            "quality": _r(snap.get("quality")),
            "yield_rate": _r(snap.get("yield_rate")),
        },
    }


def run_pdm() -> dict:
    """고정 시퀀스 헬스 행 → features → RUL(DB 접근 없음)."""
    sys.path.insert(0, str(ROOT))
    from aria.inspection.asset_proxy import proxy
    from aria.inspection.health_features import extract
    from aria.inspection.rul_estimator import estimate

    rows = []
    for elapsed in HEALTH_INTERVALS_S:
        snap = proxy(ASSET_ID, infer_p95_ms=INFER_P95_MS, drop_rate=DROP_RATE, elapsed_s=elapsed)
        rows.append({
            "ts": T0_MS + int(elapsed * 1000),
            "infer_p95_ms": INFER_P95_MS,
            "drop_rate": DROP_RATE,
            "temp_c": snap["temp_c"],
            "vib_rms_mm_s": snap["vib_rms_mm_s"],
            "sim": snap["sim"],
        })

    features = extract(rows, baseline=None)
    rul = estimate(rows, ASSET_ID, features)

    if rul is None:
        return {"health_index": None, "rul_est": None, "rul_lo": None, "rul_hi": None,
                "model": None, "confidence": None}

    band = rul.get("rul", {})
    return {
        "health_index": _r(rul.get("health_index")),
        "rul_est": _r(band.get("est_hours")),
        "rul_lo": _r(band.get("lo")),
        "rul_hi": _r(band.get("hi")),
        "model": band.get("model"),
        "confidence": _r(rul.get("confidence")),
    }


def capture() -> dict:
    pipe_data = run_pipeline()
    pdm_data = run_pdm()
    return {
        "version": VERSION,
        "config": {
            "seed": SEED, "n_frames": N_FRAMES, "tau": TAU,
            "trigger_interval_s": TRIGGER_INTERVAL_S,
            "queue_depth": QUEUE_DEPTH, "n_workers": N_WORKERS,
            "asset_id": ASSET_ID, "health_intervals": len(HEALTH_INTERVALS_S),
            "infer_p95_ms": INFER_P95_MS, "drop_rate": DROP_RATE,
        },
        "parts": pipe_data["parts"],
        "aggregate": pipe_data["aggregate"],
        "pdm": pdm_data,
    }


def _flatten(obj: dict, prefix="") -> dict:
    """중첩 dict를 key.subkey 플랫 dict로 변환(diff 용이)."""
    out = {}
    for k, v in obj.items():
        fk = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, fk + "."))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out.update(_flatten(item, f"{fk}[{i}]."))
                else:
                    out[f"{fk}[{i}]"] = item
        else:
            out[fk] = v
    return out


def diff(golden: dict, current: dict) -> list[dict]:
    """골든 vs 현재 diff 목록 반환. 빈 리스트 = 무회귀."""
    diffs = []

    # 부분별 결과 (parts 리스트)
    gparts = {p["part_id"]: p for p in golden.get("parts", [])}
    cparts = {p["part_id"]: p for p in current.get("parts", [])}
    all_ids = sorted(set(gparts) | set(cparts))
    for pid in all_ids:
        gp = gparts.get(pid)
        cp = cparts.get(pid)
        if gp is None:
            diffs.append({"field": f"parts[{pid}]", "golden": None, "current": cp})
            continue
        if cp is None:
            diffs.append({"field": f"parts[{pid}]", "golden": gp, "current": None})
            continue
        for key in ("verdict", "score"):
            gv, cv = gp.get(key), cp.get(key)
            if gv != cv:
                diffs.append({"field": f"parts[{pid}].{key}", "golden": gv, "current": cv})

    # 집계 비교
    for key, gv in golden.get("aggregate", {}).items():
        cv = current.get("aggregate", {}).get(key)
        if gv != cv:
            diffs.append({"field": f"aggregate.{key}", "golden": gv, "current": cv})

    # PdM 비교
    for key, gv in golden.get("pdm", {}).items():
        cv = current.get("pdm", {}).get(key)
        if gv != cv:
            diffs.append({"field": f"pdm.{key}", "golden": gv, "current": cv})

    return diffs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true", help="기준선 캡처 → golden.json")
    parser.add_argument("--verify",  action="store_true", help="재실행 후 diff(0건=PASS)")
    parser.add_argument("--show",    action="store_true", help="현재 결과만 출력")
    args = parser.parse_args()

    if args.capture:
        print("[golden_trace] 캡처 실행 중…")
        data = capture()
        GOLDEN_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"[golden_trace] CAPTURED → {GOLDEN_PATH}")
        print(f"  parts={len(data['parts'])}  aggregate={data['aggregate']}  pdm={data['pdm']}")
        sys.exit(0)

    elif args.verify:
        if not GOLDEN_PATH.exists():
            print(f"[golden_trace] FAIL: golden.json 없음 — 먼저 --capture 실행", file=sys.stderr)
            sys.exit(2)
        golden = json.loads(GOLDEN_PATH.read_text())
        print("[golden_trace] 검증 실행 중…")
        current = capture()
        diffs = diff(golden, current)
        if not diffs:
            print(f"[golden_trace] PASS — diff 0건 (무회귀 확인)")
            sys.exit(0)
        else:
            print(f"[golden_trace] FAIL — diff {len(diffs)}건:", file=sys.stderr)
            for d in diffs:
                print(f"  {d['field']}: {d['golden']!r} → {d['current']!r}", file=sys.stderr)
            sys.exit(1)

    elif args.show:
        print("[golden_trace] 현재 실행 결과:")
        data = capture()
        print(json.dumps(data, indent=2, ensure_ascii=False))
        sys.exit(0)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
