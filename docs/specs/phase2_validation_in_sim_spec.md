# ARIA 명세서 — Phase 2(A+): 추론·판정 in-sim (NG 검증) for Antigravity

> 가상공간 파이프라인의 마지막 기둥 — **인테이크→학습→검증.** 그리고 **맨 처음 비평을 그 시스템의 방식으로 종결**한다:
> *good에서 임계값(mean+3σ) 캘리브레이션 → defect의 escape율(놓친 불량률) 측정.*
> 데모 흐름 먼저: 점수는 **dummy score_fn(seam)**, 실제 CMDIAD `anomaly_score`는 나중에 교체.

## 0. 설계 (재사용 + seam)

```
시뮬 '검증 실행' → /api/sim/validate(run_id) → manifest 로드
   → run_validation: good→threshold=mean+3σ, defect→escape율, good→오검출율
   → VERIFIER 에이전트 agent_status(running→done) + 결과 반환 → 시뮬 오버레이 표시
```
- 임계값 방식은 `threshold_calibrator`(mean+3σ, 최소 5.0)와 **동일**.
- `score_fn`이 seam: 지금 dummy, 나중에 `cmdiad_inference`의 anomaly_score로 교체.

## 1. 범위 (Scope)

**포함:**
- `validation/validate.py` — `run_validation(manifest, score_fn)` + `dummy_score`(seam).
- `POST /api/sim/validate` — run_id로 manifest 로드 후 검증 + **VERIFIER agent_status** emit.
- SimulationView: **"검증 실행" 버튼**(학습 후) + escape율·오검출율·임계값 오버레이.
- apiClient `simValidate(runId)`.

**제외(다음):** 실제 CMDIAD 모델 추론(seam 교체), 자율 체이닝, 검사 Dashboard 제거.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `validation/validate.py` (신규) | `run_validation` + `dummy_score` seam |
| `app.py` | `POST /api/sim/validate` (+ VERIFIER agent_status) |
| `frontend/src/api/apiClient.js` | `simValidate(runId)` |
| `frontend/src/components/SimulationView.jsx` | 검증 버튼 + 결과 표시 |

## 3. 작업 명세 (What)

### 3-A. `validation/validate.py` (신규)
```python
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

def run_validation(manifest: dict, score_fn=dummy_score) -> dict:
    imgs = manifest.get("images", [])
    good   = [p for p in imgs if _label_of(p) == "normal"]
    defect = [p for p in imgs if _label_of(p) == "anomaly"]
    if not good:
        return {"ok": False, "error": "good(정상) 클래스 없음 — 캘리브레이션 불가"}
    gs = [score_fn(p, "normal") for p in good]
    mean = sum(gs) / len(gs)
    std  = (sum((x - mean) ** 2 for x in gs) / len(gs)) ** 0.5
    threshold = max(mean + 3.0 * std, 5.0)               # threshold_calibrator와 동일
    ds = [score_fn(p, "anomaly") for p in defect]
    escapes = sum(1 for s in ds if s <= threshold)        # 임계값 못 넘은 결함 = 놓침
    fp      = sum(1 for s in gs if s > threshold)         # 정상인데 결함 판정 = 오검출
    n_def = len(defect)
    return {
        "ok": True, "scorer": "dummy",
        "threshold": round(threshold, 2),
        "mean_good": round(mean, 2), "std_good": round(std, 2),
        "n_good": len(good), "n_defect": n_def,
        "escapes": escapes,
        "escape_rate": round(escapes / n_def, 3) if n_def else None,
        "false_positives": fp,
        "fp_rate": round(fp / len(good), 3),
    }
```

### 3-B. `app.py` — `/api/sim/validate` (+ VERIFIER 에이전트)
```python
from fastapi import Body
@app.post("/api/sim/validate")
async def sim_validate(payload: dict = Body(...)):
    import json
    from validation.validate import run_validation
    run_id = payload.get("run_id")
    mpath = UPLOAD_DIR / str(run_id) / "manifest.json"
    if not run_id or not mpath.exists():
        return {"ok": False, "error": "manifest 없음 — 먼저 인테이크 필요"}
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    await manager.broadcast({"type": "agent_status", "agent": "VERIFIER",
                             "state": "running", "detail": "NG 검증"})
    result = run_validation(manifest)                     # dummy는 즉시(빠름)
    er = result.get("escape_rate")
    detail = f"escape {er:.0%}" if er is not None else (result.get("error") or "검증")
    await manager.broadcast({"type": "agent_status", "agent": "VERIFIER",
                             "state": "done", "detail": detail})
    return result
```
> dummy는 즉시 끝나 inline 처리. 실제 모델(느림)로 교체 시 thread + run_coroutine_threadsafe로.

### 3-C. apiClient
```javascript
export async function simValidate(runId) {
  const { data } = await api.post('/api/sim/validate', { run_id: runId })
  return data
}
```

### 3-D. SimulationView — 검증 버튼 + 결과
import에 `simValidate` 추가. 상태 `const [validation, setValidation] = useState(null)`.
오버레이(학습 영역 아래):
```jsx
{lastRunId && (
  <button onClick={async () => setValidation(await simValidate(lastRunId))}
    style={{ padding:'6px 12px', borderRadius:8, cursor:'pointer', fontSize:12,
      border:'1px solid rgba(167,139,250,0.45)', background:'rgba(167,139,250,0.12)',
      color:'#a78bfa', width:'fit-content' }}>
    검증 실행 (NG)
  </button>
)}
{validation?.ok && (
  <div style={{ fontSize:11, color:'#cbd5e1', lineHeight:1.6 }}>
    임계값 {validation.threshold} (good μ{validation.mean_good}+3σ)<br/>
    <span style={{ color: validation.escape_rate > 0.2 ? '#f87171' : '#34d399' }}>
      escape율 {(validation.escape_rate*100).toFixed(0)}%
    </span> ({validation.escapes}/{validation.n_defect} 놓침) · 오검출 {(validation.fp_rate*100).toFixed(0)}%
  </div>
)}
{validation?.ok === false && <span style={{ fontSize:11, color:'#f87171' }}>{validation.error}</span>}
```
> escape율을 강조(높으면 빨강) — "3σ on good-only가 결함을 얼마나 놓치는가"가 *눈에* 보인다.

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "def run_validation\|def dummy_score\|mean + 3\|escape" validation/validate.py
grep -n "/api/sim/validate\|VERIFIER\|run_validation" app.py
grep -n "simValidate" frontend/src/api/apiClient.js
grep -n "simValidate\|validation\|검증 실행\|escape" frontend/src/components/SimulationView.jsx
```

### 4-2. Headless smoke (내가 실행 — python)
- good 폴더 경로 N개 + defect 경로 M개를 담은 manifest → `run_validation` →
  `threshold == round(mean_good + 3*std_good, 2)`(최소 5.0), `escape_rate ∈ [0,1]`, `fp_rate ∈ [0,1]`, 카운트 일치.
- good 없는 manifest → `{ok:False, error:...}`(graceful).

### 4-3. 회귀 가드
```
grep -c "/api/sim/train\|/api/dataset/intake" app.py        # Phase 2 학습·인테이크 유지
grep -c "simTrain\|agent_status\|simAgents" frontend/src/components/SimulationView.jsx  # Phase 2a/2A 보존
grep -c "SwarmChat\|TrainingViewer" frontend/src/components/Dashboard.jsx               # 엔진 보존
python -m py_compile validation/validate.py app.py
```

### 4-4. 런타임 (당신 — 비평 종결의 순간)
- 시뮬: 인테이크 → 학습 → **"검증 실행 (NG)"** → **VERIFIER 칩 점등** + **escape율·오검출율·임계값** 표시.
- (SIM-4 합성 good/defect 데이터를 인테이크하면) escape율이 *의미 있게* 뜸 — "mean+3σ가 결함을 X% 놓친다"가 보임. Antigravity 녹화.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-2 python smoke(threshold=mean+3σ·escape율·graceful), 4-3 회귀. 4-4는 Antigravity. 통과 시 — **실제 CMDIAD score_fn 교체**(진짜 추론) 또는 **자율 체이닝**(드롭 한 번에 전 과정)으로.

## 6. 커밋
- 브랜치: `feat/phase2-validation-in-sim`
- 메시지(예): `feat(sim): in-space NG validation — calibrate threshold (mean+3σ) on good, measure defect escape rate`

## 7. 주의
- `score_fn`은 **seam** — 지금 dummy(데모 흐름), 실제 추론은 cmdiad anomaly_score로 교체. dummy는 *재현 가능한 의사난수*(good 낮음·defect 높음·겹침)로 *그럴듯한* escape율을 보일 뿐, 진짜 성능 아님.
- 임계값은 **mean+3σ(최소 5.0)** — `threshold_calibrator`와 일치. 임의로 바꾸지 말 것.
- good 클래스 없으면 **graceful**(에러 메시지) — 죽지 않게.
- Phase 2/2a·엔진 **무변경**.
- 이건 비평을 *데모 수준으로* 닫는다. 진짜 종결은 실제 모델 score_fn 교체 후.
