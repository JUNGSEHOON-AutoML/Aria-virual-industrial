"""NG 검증: good에서 임계값(mean+3σ) 캘리브레이션 → defect escape율 측정.
score_fn은 seam — 지금 demo dummy, 나중에 실제 CMDIAD anomaly_score로 교체."""
import hashlib
from pathlib import Path

def dummy_score(path: str, label: str) -> float:        # ★ seam (demo)
    h = (int(hashlib.md5(path.encode()).hexdigest(), 16) % 1000) / 1000.0
    return (6 + h * 8) if label == "normal" else (12 + h * 12)   # good 낮음·defect 높음(겹침)

def _label_of(path: str) -> str:
    name = Path(path).parent.name.lower()
    return "normal" if name in ("good", "normal", "ok") else "anomaly"

def run_validation(manifest: dict, score_fn=None, criteria=None) -> dict:
    from pathlib import Path
    if score_fn is None:
        bank_path = Path(manifest.get("work_dir", "")) / "bank.npy"
        if bank_path.exists():
            import numpy as np
            from aria.perception.scorer.feature_bank import cosine_score
            bank = np.load(bank_path)
            score_fn = lambda p: cosine_score(p, bank)      # ★ 진짜 FM 코사인 스코어
        else:
            score_fn = lambda p: dummy_score(p, _label_of(p))   # 폴백(뱅크 없을 때)
    # ── 이하 기존 로직 그대로: good→threshold=mean+3σ, defect→escape율 ──
    imgs = manifest.get("images", [])
    good   = [p for p in imgs if _label_of(p) == "normal"]
    defect = [p for p in imgs if _label_of(p) == "anomaly"]
    if not good:
        return {"ok": False, "error": "good(정상) 클래스 없음 — 캘리브레이션 불가"}
    gs = [score_fn(p) for p in good]
    mean = sum(gs)/len(gs); std = (sum((x-mean)**2 for x in gs)/len(gs))**0.5
    threshold = max(mean + 3.0*std, 0.0)     # 코사인 스케일이라 최소 5.0 캡 제거(또는 작게)
    ds = [score_fn(p) for p in defect]
    escapes = sum(1 for s in ds if s <= threshold); fp = sum(1 for s in gs if s > threshold)
    n_def = len(defect)

    max_escape = (criteria or {}).get("max_escape_rate", 0.05)   # 놓침 ≤ 5%
    max_fp     = (criteria or {}).get("max_fp_rate",     0.20)   # 오검출 ≤ 20%
    er = escapes / n_def if n_def else None
    fpr = fp / len(good)
    if n_def == 0:
        fat_verdict = "N/A"        # NG 표본 없음 → 합격 판정 불가
    else:
        fat_verdict = "PASS" if (er <= max_escape and fpr <= max_fp) else "FAIL"

    return {"ok": True, "scorer": "cosine_bank" if (Path(manifest.get("work_dir",""))/"bank.npy").exists() else "dummy",
            "threshold": round(threshold,4), "mean_good": round(mean,4), "std_good": round(std,4),
            "n_good": len(good), "n_defect": n_def, "escapes": escapes,
            "escape_rate": round(escapes/n_def,3) if n_def else None,
            "false_positives": fp, "fp_rate": round(fp/len(good),3),
            "pass_criteria": {"max_escape_rate": max_escape, "max_fp_rate": max_fp},
            "fat_verdict": fat_verdict}
