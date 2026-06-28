# ARIA 명세서 — 실 FM 루프 안정화 + 에이전트 배치 for Antigravity

> 목표: S1(진짜 FM 스코어러)을 얹은 자율 공장이 **느린 진짜 학습에도 끊기지 않고 계속** 돌고, **학습 단계에 에이전트(TRAINER)가 켜져** 배치가 실제 파이프라인을 비추게.
> 논문(τ 선별)은 이번엔 **안 씀** — 참고용 보관(S2).

## 0. 고치는 것 두 개

1. **하트비트 타임아웃** — 고정 30초 대신, *진행 이벤트가 올 때마다 타임아웃을 리셋.* 진짜 DINO가 오래 걸려도 진행 중이면 안 끊기고, *진짜 멈췄을 때만* 정지.
2. **TRAINER 에이전트** — `/api/sim/train`의 진짜 뱅크 구축 동안 `agent_status`(TRAINER)를 쏴서 칩이 켜짐. 루프 사이클마다 **TRAINER → VERIFIER**가 보임.

## 1. 범위 (Scope)

**포함:**
- SimulationView `waitTrainingDone`를 **하트비트**로 교체(+ 첫 사이클 모델로딩 대비 넉넉한 stall 한도).
- `/api/sim/train` 워커가 **TRAINER agent_status**(running→done, 실패 idle) + **초기 'running' 이벤트**(모델 로딩 표시 겸 조기 하트비트) emit.

**제외:** 논문 τ(S2), DINOv2 교체, 루프에 SCAN/DOMAIN 추가, 검증 스코어링 최적화.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/components/SimulationView.jsx` | 하트비트 타임아웃 |
| `app.py` `/api/sim/train` | TRAINER agent_status + 초기 진행 이벤트 |

## 3. 작업 명세 (What)

### 3-A. 하트비트 타임아웃 (SimulationView)
```jsx
const trainDoneRef  = useRef(null)   // { resolve, reject } | null
const trainTimerRef = useRef(null)

function armStall(ms) {                         // 무응답 ms 지나면 정지
  clearTimeout(trainTimerRef.current)
  trainTimerRef.current = setTimeout(() => {
    const d = trainDoneRef.current
    if (d) { trainDoneRef.current = null; d.reject(new Error('학습 정지(무응답)')) }
  }, ms)
}
function waitTrainingDone(stallMs = 120000) {   // 첫 사이클 모델 로딩 대비 넉넉히
  return new Promise((resolve, reject) => {
    trainDoneRef.current = { resolve, reject, stallMs }
    armStall(stallMs)
  })
}
```
WS `'training'` 핸들러:
```jsx
if (d.type === 'training') {
  setTrainState({ step: d.step, total: d.total_steps, status: d.status, loss: d.metrics?.loss })
  const w = trainDoneRef.current
  if (w && d.status === 'running') armStall(w.stallMs)          // ★ 하트비트: 진행 = 타임아웃 리셋
  if (d.status === 'done') {
    clearTimeout(trainTimerRef.current)
    if (w) { trainDoneRef.current = null; w.resolve() }          // 루프 모드 깨우기
    else if (chainRef.current && !validatedRef.current && runIdRef.current && !loopRef.current) {
      validatedRef.current = true                                // 수동 체인(기존)
      simValidate(runIdRef.current).then(setValidation).catch(e => setValidation({ ok:false, error:String(e) }))
    }
  }
  if (d.status === 'error') {
    clearTimeout(trainTimerRef.current)
    if (w) { trainDoneRef.current = null; w.reject(new Error('학습 실패')) }
    chainRef.current = false
  }
}
```
> 핵심: `running` 이벤트마다 `armStall` 재호출 → 진행 중이면 영원히 안 끊김. 진짜 무응답(예: 모델 로드 실패로 이벤트 끊김)일 때만 stall 한도 후 정지.

### 3-B. TRAINER 에이전트 + 초기 진행 이벤트 (app.py `/api/sim/train`)
워커 안, 기존 `publish`(training 이벤트)와 나란히 agent_status emit 추가:
```python
loop = asyncio.get_running_loop()
def publish(ev):
    asyncio.run_coroutine_threadsafe(event_bus.publish(TRAINING_TOPIC, ev), loop)
def emit_agent(agent, state, detail):
    asyncio.run_coroutine_threadsafe(
        manager.broadcast({"type": "agent_status", "agent": agent, "state": state, "detail": detail}), loop)
def worker():
    try:
        emit_agent("TRAINER", "running", "메모리뱅크 구축")
        publish(make_training_event(run_id, 0, len(good), "running", loss=0.0))  # 조기 하트비트(모델 로딩)
        bank = build_bank(good, run_id, publish)            # 진짜 FM 추출(여기서 모델 로드)
        np.save(str(work / "bank.npy"), bank)
        publish(make_training_event(run_id, len(good), len(good), "done", loss=0.0))
        emit_agent("TRAINER", "done", f"{len(good)} 이미지 · {bank.shape[0]} 패치")
    except Exception as e:
        print(f"[sim_train] bank build 실패: {e}")
        publish(make_training_event(run_id, 0, 0, "error", loss=0.0))
        emit_agent("TRAINER", "idle", f"실패: {e}")
threading.Thread(target=worker, daemon=True).start()
```
> 초기 `running`(step 0) 이벤트가 모델 로딩 중에도 UI·하트비트를 깨워, 첫 사이클이 30~수십 초 걸려도 루프가 안 끊김.

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "armStall\|trainTimerRef\|stallMs\|waitTrainingDone" frontend/src/components/SimulationView.jsx
grep -n "TRAINER\|emit_agent\|step.*0.*running\|make_training_event(run_id, 0" app.py
```

### 4-2. 회귀 + 구문
```
grep -c "loopRef\|factoryLoop\|runCycle" frontend/src/components/SimulationView.jsx   # 루프 보존
grep -c "build_bank\|bank.npy" app.py                                                 # S1 스코어러 보존
grep -c "/api/sim/train\|/api/sim/validate" app.py                                    # 엔드포인트
grep -c "VERIFIER\|agent_status" app.py                                               # 기존 에이전트 보존
python -m py_compile app.py
```

### 4-3. 런타임 (당신/Antigravity — *끊김 없는* 자율 공장)
- "▶ 자동 순환 시작" → **첫 사이클이 모델 로딩으로 수십 초 걸려도 루프가 안 멈추고** 학습 진행바가 뜸(하트비트). 이후 사이클은 빠름(싱글톤).
- 매 사이클 **TRAINER 칩이 켜졌다(running) 꺼지고(done) → VERIFIER 칩**으로 이어짐 = 에이전트 배치가 실제 학습·검증을 비춤.
- 모델 로드가 진짜 실패하면 stall 한도(2분) 후 루프가 *정지*(폭주 없음).
- Antigravity 녹화: 3사이클 연속 + TRAINER/VERIFIER 칩 점등.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep(하트비트·TRAINER), 4-2 회귀+py_compile. 하트비트의 *실제 끊김 없음*과 TRAINER 점등은 GPU/런타임이라 Antigravity 녹화. (헤드리스로는 타이머 로직을 직접 못 돌림 — 코드 구조만 확인.)

## 6. 커밋
- 브랜치: `feat/loop-heartbeat-trainer-agent`
- 메시지(예): `fix(sim): heartbeat training timeout + TRAINER agent — real-FM loop runs continuously`

## 7. 주의
- **하트비트가 핵심** — 고정 타임아웃을 진행 이벤트로 리셋. 진행=계속, 무응답=정지.
- 첫 사이클 **모델 로딩 공백**을 초기 `running` 이벤트 + 넉넉한 stall(2분)로 커버.
- 모델 싱글톤이라 **재로드 없음**(이미 그렇게 되어 있음 — 깨지 말 것).
- TRAINER는 **새 에이전트 칩**(AgentSwarm이 미지 에이전트를 자동 추가하므로 프론트 변경 불필요).
- 검증(simValidate)은 await라 타임아웃 없음 — 느려도 루프를 멈추진 않음(다음 사이클이 늦어질 뿐).
- 논문 τ·DINOv2는 범위 밖(S2/후속).
