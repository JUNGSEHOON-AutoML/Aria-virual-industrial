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

def cosine_score_features(feats, bank):
    f = _l2(_np(feats))               # [N, D]
    sims = f @ bank.T                 # [N, M] 코사인 유사도(양쪽 정규화)
    patch_anom = 1.0 - sims.max(axis=1)   # 패치별 (1 − 최대유사도)
    return float(patch_anom.max())        # 이미지 점수 = 최악 패치

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
