"""백본무관 코사인 메모리뱅크 스코어러 (S1: FM baseline).
학습=good 특징 뱅크 구축, 추론=패치별 최근접 코사인거리 최댓값."""
import numpy as np
from aria.core.config.backbone import get_backbone

def _np(feats):
    try: feats = feats.detach().cpu().numpy()
    except AttributeError: feats = np.asarray(feats)
    return feats.astype(np.float32)

def _l2(x, eps=1e-8):
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + eps)

# ── 순수함수(테스트 가능) ──────────────────────────────
def build_bank_from_features(feature_arrays, subsample=4000, seed=0):
    bank = np.concatenate([_l2(_np(f)) for f in feature_arrays], axis=0)   # [ΣN, D] L2정규화
    if subsample and bank.shape[0] > subsample:
        idx = np.random.default_rng(seed).choice(bank.shape[0], subsample, replace=False)
        bank = bank[idx]
    return bank

def cosine_patch_scores(feats, bank, query_chunk=256, bank_chunk=1024):
    """Exact max-cosine scores with bounded similarity workspace.

    Bank rows use the existing normalized-bank contract; no re-normalization,
    clipping, approximate search or threshold change is introduced.
    Float32 BLAS reduction order can differ from one full matrix multiply.
    """
    f = _np(feats)
    bank = np.asarray(bank)
    if f.ndim != 2 or bank.ndim != 2 or not len(f) or not len(bank):
        raise ValueError("features and bank must be nonempty 2D arrays")
    if f.shape[1] != bank.shape[1]:
        raise ValueError("feature and bank dimensions differ")
    if query_chunk <= 0 or bank_chunk <= 0:
        raise ValueError("chunk sizes must be positive")
    if not np.isfinite(f).all() or not np.isfinite(bank).all():
        raise ValueError("features and bank must be finite")
    f = _l2(f)
    scores = np.empty(len(f), dtype=np.result_type(f.dtype, bank.dtype))
    for qs in range(0, len(f), query_chunk):
        q = f[qs:qs + query_chunk]
        best = np.full(len(q), -np.inf, dtype=scores.dtype)
        for bs in range(0, len(bank), bank_chunk):
            best = np.maximum(best, (q @ bank[bs:bs + bank_chunk].T).max(axis=1))
        scores[qs:qs + len(q)] = 1.0 - best
    return scores


def cosine_score_features(feats, bank):
    return float(cosine_patch_scores(feats, bank).max())

# ── 이미지 경로 래퍼(실제 백본) ───────────────────────
def _extract(path):
    return get_backbone().extract_features(path)

def build_bank(image_paths, run_id=None, publish=None, subsample=4000):
    feats, total = [], len(image_paths)
    for i, p in enumerate(image_paths):
        feats.append(_extract(p))
        if publish:
            from aria.learning.training.events import make_training_event
            publish(make_training_event(run_id, i + 1, total, "running", loss=0.0))
    return build_bank_from_features(feats, subsample)

def cosine_score(image_path, bank):
    return cosine_score_features(_extract(image_path), bank)
