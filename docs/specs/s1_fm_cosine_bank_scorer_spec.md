# ARIA 명세서 — Slice 1 (S1): 파운데이션 모델 코사인 메모리뱅크 스코어러 for Antigravity

> 목표: **가상공간에서 *진짜* 학습·추론.** dummy를 걷어내고 — *학습 = good 특징 메모리뱅크 구축, 추론 = 코사인 최근접 거리.*
> 백본무관(`get_backbone()` seam) → 지금 DINO ViT-B/8로 즉시 동작, **DINOv2 교체는 provider 한 클래스**(후속). 이게 S1 baseline(AnomalyDINO/SuperAD 형태).

## 0. 설계 근거

- `get_backbone().extract_features(path)` → 패치 특징 `[N, D]`(ViT-B/8: `[784, 768]`).
- 메모리뱅크 = good 이미지들의 패치 특징(L2 정규화) 스택(+서브샘플). 점수 = 테스트 패치별 **최근접 코사인 거리(1−최대유사도)의 최댓값** = 이미지 이상점수.
- 임계값은 **이번엔 mean+3σ 유지**(논문 τ·CALIBRATOR는 Slice 2/3). escape율이 *진짜 FM 점수* 위에서 나오게 하는 게 S1의 목적.

## 1. 범위 (Scope)

**포함:**
- `scorer/feature_bank.py` — `build_bank`/`cosine_score`(+테스트 가능한 순수함수 `*_from_features`), 백본무관.
- `/api/sim/train` = **진짜 메모리뱅크 구축**(진행 이벤트 + `bank.npy` 저장), dummy 학습 대체.
- `run_validation` = **bank 로드 후 코사인 스코어**(없으면 dummy 폴백).

**제외(다음 슬라이스):** 논문 τ·feature selection(S2), CALIBRATOR(S3), VLM-CONFIRM, **DINOv2 provider 실제 추가**(주석/env만 준비), 실NG 데이터셋 정교 평가.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `scorer/feature_bank.py` (신규) | 메모리뱅크 + 코사인 스코어 (백본무관) |
| `app.py` `/api/sim/train` | dummy → 진짜 bank 구축 + 진행이벤트 + 저장 |
| `validation/validate.py` | bank 있으면 코사인 스코어, 없으면 dummy 폴백 |

## 3. 작업 명세 (What)

### 3-A. `scorer/feature_bank.py` (신규)
```python
"""백본무관 코사인 메모리뱅크 스코어러 (S1: FM baseline).
학습=good 특징 뱅크 구축, 추론=패치별 최근접 코사인거리 최댓값."""
import numpy as np
from config.backbone import get_backbone

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
            from training.events import make_training_event
            publish(make_training_event(run_id, i + 1, total, "running", loss=0.0))
    return build_bank_from_features(feats, subsample)

def cosine_score(image_path, bank):
    return cosine_score_features(_extract(image_path), bank)
```

### 3-B. `app.py` `/api/sim/train` — 진짜 뱅크 구축
```python
@app.post("/api/sim/train")
async def sim_train(payload: dict = Body(...)):
    import json, asyncio, threading
    import numpy as np
    from pathlib import Path
    from scorer.feature_bank import build_bank
    from training.events import TRAINING_TOPIC, make_training_event
    from event_bus import event_bus
    run_id = payload.get("run_id")
    work = UPLOAD_DIR / str(run_id)
    mpath = work / "manifest.json"
    if not run_id or not mpath.exists():
        return {"ok": False, "error": "manifest 없음 — 먼저 인테이크/생성 필요"}
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    imgs = manifest.get("images", [])
    good = [p for p in imgs if Path(p).parent.name.lower() in ("good", "normal", "ok")] or imgs
    loop = asyncio.get_running_loop()
    def publish(ev):
        asyncio.run_coroutine_threadsafe(event_bus.publish(TRAINING_TOPIC, ev), loop)
    def worker():
        try:
            bank = build_bank(good, run_id, publish)              # 진짜 FM 특징 추출
            np.save(str(work / "bank.npy"), bank)                  # 모델 저장
            publish(make_training_event(run_id, len(good), len(good), "done", loss=0.0))
        except Exception as e:
            print(f"[sim_train] bank build 실패: {e}")
            publish(make_training_event(run_id, 0, 0, "error", loss=0.0))  # 루프 가드가 정지
    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "run_id": run_id}
```
> 진행 이벤트는 기존 `training` 형식 그대로 → 루프 `waitTrainingDone`·UI 진행바 그대로 동작. 실패 시 `error` → 루프 정지.

### 3-C. `validation/validate.py` — bank 코사인 스코어(폴백 포함)
```python
def run_validation(manifest: dict, score_fn=None) -> dict:
    from pathlib import Path
    if score_fn is None:
        bank_path = Path(manifest.get("work_dir", "")) / "bank.npy"
        if bank_path.exists():
            import numpy as np
            from scorer.feature_bank import cosine_score
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
    return {"ok": True, "scorer": "cosine_bank" if (Path(manifest.get("work_dir",""))/"bank.npy").exists() else "dummy",
            "threshold": round(threshold,4), "mean_good": round(mean,4), "std_good": round(std,4),
            "n_good": len(good), "n_defect": n_def, "escapes": escapes,
            "escape_rate": round(escapes/n_def,3) if n_def else None,
            "false_positives": fp, "fp_rate": round(fp/len(good),3)}
```
> `score_fn(p)`가 인자 1개가 되도록(기존 dummy_score는 (path,label) — 폴백 람다에서 label 채움). 임계값 캡(5.0)은 코사인 스케일에 안 맞으니 제거/축소.

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "def build_bank\|def cosine_score\|build_bank_from_features\|cosine_score_features" scorer/feature_bank.py
grep -n "build_bank\|bank.npy" app.py
grep -n "cosine_score\|bank.npy\|scorer ==\|cosine_bank" validation/validate.py
```

### 4-2. Headless smoke (내가 실행 — 순수함수, 백본 없이)
- 합성 특징으로 `build_bank_from_features` + `cosine_score_features`:
  - bank를 한 군집(정상)으로 구성 → **정상 유사 특징은 낮은 점수, 직교(이상) 특징은 높은 점수**(정상 < 이상).
  - bank L2 정규화·shape 확인, 점수 ∈ [0,2].
- (실제 DINO 추론은 GPU 필요 → Antigravity/당신이 런타임 검증.)

### 4-3. 회귀 가드
```
grep -c "/api/sim/dataset\|/api/sim/train\|/api/sim/validate" app.py     # 엔드포인트 유지
grep -c "loopRef\|factoryLoop\|captureDataset" frontend/src/components/SimulationView.jsx  # 루프 보존
grep -c "SwarmChat\|TrainingViewer" frontend/src/components/Dashboard.jsx  # 엔진 보존
python -m py_compile scorer/feature_bank.py validation/validate.py app.py
```

### 4-4. 런타임 (당신/Antigravity — 진짜 FM)
- 시뮬: 데이터 생성/인테이크 → 자동 학습 시 **진행바가 *실제 이미지 처리 수*로 움직이고**(bank 구축), `uploads/<run>/bank.npy` 생성.
- 검증 → **escape율이 진짜 코사인 점수 기반**으로 나옴(`scorer: "cosine_bank"`). 결함이 정상보다 높은 점수인지.
- (처음 호출은 DINO 모델 로드로 수 초 지연 — 정상.) Antigravity 녹화.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-2 순수함수 smoke(정상<이상·정규화·범위), 4-3 회귀+py_compile. 4-4 실제 FM 추론은 GPU라 Antigravity/당신. 통과 시 — **Slice 2(논문 τ·feature selection)** 또는 **DINOv2 provider 교체**.

## 6. 커밋
- 브랜치: `feat/s1-fm-cosine-bank-scorer`
- 메시지(예): `feat(scorer): backbone-agnostic cosine memory-bank scorer (S1 FM baseline) — real bank build + cosine NN scoring`

## 7. 주의
- **백본무관 유지** — `get_backbone()`만 호출. DINOv2는 `config/backbone.py`에 provider 클래스 + `ARIA_BACKBONE=dinov2`로 후속(이번 슬라이스에선 추가 안 함).
- **graceful** — 모델 로드 실패 시 학습 'error'(루프 정지), 검증은 bank 없으면 dummy 폴백 → 시스템이 안 죽음.
- **점수 스케일**: 코사인 이상점수 ∈ [0,2]. mean+3σ 최소 캡(5.0) 제거(스케일 불일치).
- **성능**: 이미지당 1회 추출. 루프에선 bank를 한 번 만들어 재사용(검증은 테스트 이미지만), subsample로 뱅크 크기 제한.
- 임계값은 아직 mean+3σ(S1). 논문 τ·NG 최적화는 Slice 2/3 — 범위 엄수.
- 첫 추출은 DINO 가중치 로드로 느림(레포 기존 자산 사용).
