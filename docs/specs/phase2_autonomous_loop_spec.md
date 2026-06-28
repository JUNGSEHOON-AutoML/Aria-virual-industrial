# ARIA 명세서 — Phase 2(C): 무한 반복 루프 (자기 데이터 생성 → 학습 → 검증 → 반복) for Antigravity

> "멈추지 않고 계속 가동되는 가상 공장"의 마침표. **드롭 없이 공장이 자기 데이터를 만들어 끝없이 순환한다.**
> 백엔드 무변경 — 기존 SIM 캡처(`captureDataset`) + `simTrain` + `simValidate`를 *하나의 루프로 묶기만*. 프론트(SimulationView) 1파일.

## 0. 루프 + 트리거 변환

```
[순환 ON] while(loopRef):
  ① captureDataset(24)  → /api/sim/dataset → run_id (합성데이터 생성, 씬 재랜덤화)
  ② simTrain(run_id)    → (WS 'training' done 대기 = Promise)
  ③ simValidate(run_id) → escape율 표시
  ④ 대기(3초) → 반복 (cycle++)
```
- 학습 완료는 **WS 'done' 이벤트를 Promise로 변환**해 await(타임아웃 가드).
- 매 사이클 씬이 재랜덤화돼 **3D 공간이 눈에 보이게 가동**된다.

## 1. 범위 (Scope)

**포함:**
- 자기 데이터 생성→학습→검증→반복 **무한 루프**.
- **순환 ON/OFF 토글** + **사이클 카운터** + 루프 상태/마지막 escape율.
- 가드: **토글 정지**, **단계 실패 시 정지**, **학습 done 타임아웃**, **루프 중 수동 체인 중복검증 억제**.
- `captureDataset`가 **run_id를 return**(없으면 추가).

**제외:** 백엔드 변경, 실제 모델 score_fn(다음), 새로고침 넘어 지속되는 루프, 무한 누적 디스크 정리(후속).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/components/SimulationView.jsx` | 루프 드라이버 + 토글/카운터 + done-Promise + 가드, captureDataset return |

> `uploadSimDataset`/`simTrain`/`simValidate`는 이미 apiClient에 있음. 재사용.

## 3. 작업 명세 (What)

### 3-A. captureDataset가 run_id 반환
기존 `captureDataset`(SIM-3) 마지막에 업로드 결과를 **return**:
```jsx
const res = await uploadSimDataset(shots, defectRatio)
// (기존 alert는 두거나 제거 — 루프는 return값 사용)
return res            // { run_id, n_images, classes, work_dir }
```

### 3-B. done-Promise + 루프 ref/상태
```jsx
const loopRef       = useRef(false)
const trainDoneRef  = useRef(null)   // 학습 done resolver
const [cycle, setCycle]       = useState(0)
const [looping, setLooping]   = useState(false)
const [loopError, setLoopError] = useState(null)

function waitTrainingDone(timeoutMs = 30000) {     // WS 'done' → Promise (타임아웃 가드)
  return new Promise((resolve, reject) => {
    trainDoneRef.current = resolve
    setTimeout(() => {
      if (trainDoneRef.current) { trainDoneRef.current = null; reject(new Error('학습 타임아웃')) }
    }, timeoutMs)
  })
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms))
```

### 3-C. WS 'training' done 핸들러 (루프 우선, 수동 체인 억제)
```jsx
if (d.type === 'training') {
  setTrainState({ step: d.step, total: d.total_steps, status: d.status, loss: d.metrics?.loss })
  if (d.status === 'done') {
    if (trainDoneRef.current) {                        // 루프 모드: 사이클 깨우기
      trainDoneRef.current(); trainDoneRef.current = null
    } else if (chainRef.current && !validatedRef.current && runIdRef.current && !loopRef.current) {
      validatedRef.current = true                      // 수동 드롭 체인(루프 아닐 때만)
      simValidate(runIdRef.current).then(setValidation).catch(e => setValidation({ ok:false, error:String(e) }))
    }
  }
}
```

### 3-D. 루프 드라이버
```jsx
async function runCycle() {
  const res = await captureDataset(24)                 // ① 합성데이터 생성
  if (!res?.run_id) throw new Error('데이터 생성 실패')
  runIdRef.current = res.run_id
  const done = waitTrainingDone()                       // ★ resolver 먼저 등록(레이스 방지)
  const t = await simTrain(res.run_id)                  // ② 학습 시작
  if (!t?.ok) throw new Error('학습 시작 실패')
  await done                                            //    학습 done 대기
  const v = await simValidate(res.run_id)               // ③ 검증
  setValidation(v)
}

async function factoryLoop() {
  setLoopError(null); setLooping(true); loopRef.current = true
  while (loopRef.current) {
    setCycle(c => c + 1)
    try { await runCycle() }
    catch (e) { setLoopError(String(e)); loopRef.current = false; break }   // 실패 → 정지
    if (!loopRef.current) break
    await sleep(3000)
  }
  setLooping(false)
}
function stopLoop() { loopRef.current = false; setLooping(false) }
```

### 3-E. UI — 토글 + 카운터
```jsx
<button onClick={() => looping ? stopLoop() : factoryLoop()}
  style={{ padding:'6px 12px', borderRadius:8, cursor:'pointer', fontSize:12,
    border:`1px solid ${looping ? 'rgba(248,113,113,0.5)' : 'rgba(52,211,153,0.5)'}`,
    background: looping ? 'rgba(248,113,113,0.12)' : 'rgba(52,211,153,0.12)',
    color: looping ? '#f87171' : '#34d399', width:'fit-content' }}>
  {looping ? '■ 순환 정지' : '▶ 자동 순환 시작'}
</button>
{(looping || cycle > 0) && (
  <div style={{ fontSize:11, color:'#cbd5e1', fontFamily:'monospace' }}>
    사이클 {cycle} {looping ? '· 가동 중' : '· 정지'}
    {validation?.escape_rate != null && ` · escape ${(validation.escape_rate*100).toFixed(0)}%`}
  </div>
)}
{loopError && <span style={{ fontSize:11, color:'#f87171' }}>루프 정지: {loopError}</span>}
```

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "loopRef\|factoryLoop\|runCycle\|waitTrainingDone\|trainDoneRef" frontend/src/components/SimulationView.jsx
grep -n "자동 순환\|순환 정지\|사이클\|setCycle" frontend/src/components/SimulationView.jsx
grep -n "return res" frontend/src/components/SimulationView.jsx   # captureDataset run_id 반환
```

### 4-2. 회귀 가드
```
grep -c "/api/sim/dataset\|/api/sim/train\|/api/sim/validate" app.py     # 3 엔드포인트 무변경
grep -c "captureDataset\|uploadSimDataset\|sampleSceneParams" frontend/src/components/SimulationView.jsx  # SIM-3/4 보존
grep -c "simTrain\|simValidate\|agent_status" frontend/src/components/SimulationView.jsx  # Phase 2 보존
grep -c "SwarmChat\|TrainingViewer" frontend/src/components/Dashboard.jsx  # 엔진 보존
```

### 4-3. 빌드
- `npm run build` 무에러 + 8080 반영.

### 4-4. 런타임 (당신 — 자율 공장 클라이맥스)
- **"▶ 자동 순환 시작"** → 드롭 없이 사이클이 자동 반복: **씬 재랜덤화 → 데이터 생성 → 학습 진행 → escape율 → 사이클 카운터 증가** 가 끝없이.
- **"■ 순환 정지"** → 현재 사이클 후 멈춤.
- 학습이 안 끝나거나 단계 실패 시 **루프가 정지 + 에러 표시**(폭주/멈춤 없음).
- Antigravity 녹화: 2~3 사이클 도는 모습 + 정지.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep(루프·done-Promise·토글·return), 4-2 회귀. 4-3 빌드·4-4 순환은 Antigravity 녹화. 통과 시 — **실제 모델 score_fn 교체**(루프를 *진짜로* 만들기)로.

## 6. 커밋
- 브랜치: `feat/phase2-autonomous-loop`
- 메시지(예): `feat(sim): self-feeding infinite factory loop — generate→train→validate→repeat (toggle + guards)`

## 7. 주의
- **resolver 먼저 등록**(`waitTrainingDone()` → `simTrain`) — 빠른 dummy 학습이 done을 먼저 쏴도 놓치지 않게(레이스).
- **타임아웃 가드** — 학습 done이 안 오면 루프가 영원히 멈춤 방지(reject→정지).
- **루프 중 수동 체인 억제**(`!loopRef.current`) — 검증 중복 방지.
- **토글/실패 = 정지** — 진짜 무한이 아니라 *제어되는* 무한(폭주 방지).
- 백엔드·엔진·Phase 2a 배선 **무변경**.
- 매 사이클 합성데이터가 `uploads/sim_*`에 쌓임 — 장시간이면 디스크 정리는 후속 과제.
- 여전히 dummy 학습/검증 — *자율 순환의 흐름*을 보이는 마침표. 진짜 모델은 다음.
