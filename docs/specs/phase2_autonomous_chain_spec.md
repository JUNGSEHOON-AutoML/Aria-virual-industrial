# ARIA 명세서 — Phase 2(B): 자율 체이닝 (드롭 한 번 → 전 과정 자동) for Antigravity

> "멈추지 않고 알아서 가동되는 가상 공장"의 첫 실현. **데이터셋 드롭 한 번 → 인테이크 → 학습 → 검증이 버튼 없이 자동 순차 실행.**
> 백엔드 무변경 — 기존 `/api/dataset/intake`·`/api/sim/train`·`/api/sim/validate` 3개를 *잇기만* 한다. 프론트(SimulationView) 1파일.

## 0. 흐름 + 트리거

```
드롭 → intakeDataset → run_id 획득
     → (자동) simTrain(run_id)              # 학습은 비동기(WS 'training' 이벤트로 진행)
     → WS 'training' status==='done' 수신   # ← 이 시점에 자동 트리거
     → (자동) simValidate(run_id) → escape율 표시
```
- 학습 완료를 폴링하지 않고 **WS 'done' 이벤트**로 검증을 깨운다.
- stale closure 방지를 위해 **ref**로 run_id·체인상태·검증가드를 들고 간다.

## 1. 범위 (Scope)

**포함:**
- 드롭 시 인테이크→학습→검증 **자동 체이닝**(ref 기반, 검증은 'done' 이벤트에서 1회).
- 수동 버튼(학습 시작·검증 실행) **제거**(체인이 대체).
- **파이프라인 상태 한 줄**(인테이크→학습→검증 진행 시각화).
- **실패 가드**(단계 실패 시 체인 중단·에러 표시).

**제외:** 백엔드 변경, 실제 모델 score_fn, 다중 데이터셋 큐, 무한 반복 루프(후속).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/components/SimulationView.jsx` | 자동 체이닝 + 상태줄 + 가드, 수동 버튼 제거 |

> `intakeDataset`·`simTrain`·`simValidate`는 이미 apiClient에 있음. 재사용.

## 3. 작업 명세 (What)

### 3-A. ref + 상태
```jsx
import { useRef } from 'react'
const runIdRef     = useRef(null)   // WS 콜백이 읽을 최신 run_id
const chainRef     = useRef(false)  // 자율 체인 진행 중인가
const validatedRef = useRef(false)  // 검증 1회 가드
// 기존 simAgents / trainState / validation / intake 상태 유지
```

### 3-B. WS 'training' 핸들러에 자동 검증 트리거 (기존 onmessage 안)
```jsx
if (d.type === 'training') {
  setTrainState({ step: d.step, total: d.total_steps, status: d.status, loss: d.metrics?.loss })
  if (d.status === 'error') { chainRef.current = false }                 // 학습 실패 → 체인 중단
  if (d.status === 'done' && chainRef.current && !validatedRef.current && runIdRef.current) {
    validatedRef.current = true                                          // 1회 가드
    simValidate(runIdRef.current)
      .then(setValidation)
      .catch(err => setValidation({ ok: false, error: String(err) }))
  }
}
```

### 3-C. 드롭 = 체인 시작 (onIntake 교체)
```jsx
async function onIntake(e) {
  const f = e.target.files?.[0]; if (!f) return
  // 체인 상태 리셋
  setSimAgents({}); setTrainState(null); setValidation(null)
  validatedRef.current = false; chainRef.current = true
  setIntake({ status: 'running' })
  try {
    const r = await intakeDataset(f)                      // ① 인테이크
    setIntake(r); runIdRef.current = r.run_id
    const t = await simTrain(r.run_id)                    // ② 자동 학습
    if (!t?.ok) { chainRef.current = false; setIntake({ error: '학습 시작 실패' }); return }
    // ③ 검증은 'training' done 이벤트에서 자동 (3-B)
  } catch (err) {
    chainRef.current = false                              // 실패 가드
    setIntake({ error: String(err) })
  }
}
```

### 3-D. 수동 버튼 제거 + 파이프라인 상태 한 줄
- Phase 2(A)/(A+)에서 넣은 **"학습 시작"·"검증 실행" 버튼 제거**(체인이 대체). 인테이크 업로드만 단일 진입점.
- 상태줄(파생):
```jsx
const phase =
  validation ? '검증 완료'
  : trainState ? (trainState.status === 'done' ? '검증 중…' : '학습 중…')
  : intake?.domain ? '학습 시작…'
  : intake?.status === 'running' ? '인테이크 중…'
  : '대기';
// 렌더:
<div style={{ fontSize:11, color:'#1FB8CD', fontFamily:'monospace' }}>
  자율 파이프라인 · {phase}
</div>
```
(기존 agent 칩·trainState·validation 표시는 그대로 두면 각 단계가 자연히 narrate 됨.)

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "runIdRef\|chainRef\|validatedRef" frontend/src/components/SimulationView.jsx
grep -n "simTrain(r.run_id)\|simValidate(runIdRef" frontend/src/components/SimulationView.jsx
grep -n "자율 파이프라인\|phase" frontend/src/components/SimulationView.jsx
grep -c "학습 시작\|검증 실행" frontend/src/components/SimulationView.jsx   # 수동 버튼 제거 → 0
```

### 4-2. 회귀 가드
```
grep -c "/api/dataset/intake\|/api/sim/train\|/api/sim/validate" app.py     # 3개 엔드포인트 무변경
grep -c "getWebSocketUrl\|agent_status\|simAgents" frontend/src/components/SimulationView.jsx  # Phase 2a 보존
grep -c "SwarmChat\|TrainingViewer" frontend/src/components/Dashboard.jsx     # 엔진 보존
```

### 4-3. 빌드
- `npm run build` 무에러 + 8080 반영.

### 4-4. 런타임 (당신 — 자율 공장 데모)
- 시뮬: **데이터셋 드롭 한 번** → 클릭 없이 **SCAN·DOMAIN 칩 → 학습 진행/loss → escape율** 이 자동 순차로 흐름. 상태줄이 인테이크→학습→검증 단계를 표시.
- **실패 케이스**: 깨진/빈 파일 드롭 → 체인이 인테이크 단계에서 멈추고 에러 표시(학습·검증으로 안 넘어감). Antigravity 녹화(정상 1회·실패 1회).

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep(체인·버튼제거), 4-2 회귀. 4-3 빌드·4-4 자율 흐름은 Antigravity 녹화. 통과 시 — **실제 모델 score_fn 교체**(진짜 추론) 또는 **무한 반복 루프**(드롭 없이 주기적 재가동 = 진짜 "계속 가동")로.

## 6. 커밋
- 브랜치: `feat/phase2-autonomous-chain`
- 메시지(예): `feat(sim): autonomous chain — drop dataset auto-runs intake→train→validate (WS-driven, guarded)`

## 7. 주의
- **ref로 처리** — WS 콜백 안에서 setState 값(run_id 등)을 직접 읽으면 stale. `runIdRef`/`validatedRef`/`chainRef` 사용.
- **검증 1회 가드** 필수 — 'done' 이벤트가 여러 번 와도(다중 WS) 검증은 한 번만(`validatedRef`).
- **실패 시 `chainRef=false`** — 다음 단계로 넘어가지 않게.
- 백엔드·엔진·Phase 2a 배선 **무변경** — SimulationView 흐름만.
- 체인은 **시뮬 뷰에 머무는 동안** 동작(탭 이탈 시 WS close로 자동 검증은 안 깨움) — 데모는 시뮬 탭에서.
- 학습은 여전히 6A **dummy**, 검증 score_fn도 dummy — *흐름의 자율성*을 보이는 슬라이스. 진짜 모델은 다음.
