# ARIA 명세서 — Phase 2(A): 시뮬 공간에서 학습 가동 (for Antigravity)

> 인테이크(입구)에 이어 **그 데이터로 학습이 가상공간 안에서** 돈다. "데이터 넣음 → 에이전트가 봄 → 이 공간에서 배운다" 한 호흡 완성.
> 핵심: **이미 있는 것 재사용** — `run_dummy_training`은 인테이크 scan 리포트를 manifest로 받고, 학습 이벤트(`type:'training'`)는 event_bus→WS로 **이미 브리지됨**(6A). 시뮬은 그걸 받아 그리기만.

## 0. 설계 (재사용 위주)

```
인테이크(/api/dataset/intake) → scan 리포트(=manifest) → work_dir/manifest.json 저장(추가)
시뮬 '학습 시작' → /api/sim/train(run_id) → manifest.json 로드 → run_dummy_training(publish=event_bus)
   → 'training' 이벤트가 기존 event_bus→WS 브리지로 broadcast → SimulationView가 받아 진행/loss 표시
```

## 1. 범위 (Scope)

**포함:**
- 인테이크가 **manifest.json을 work_dir에 저장**(학습이 읽도록).
- **`POST /api/sim/train`** — run_id로 manifest 로드 후 `run_dummy_training` 기동(기존 event_bus publish 패턴 재사용).
- SimulationView: WS 리스너에 **`training` 처리 추가** + **"학습 시작" 버튼**(인테이크 후 표시) + 진행/loss 오버레이.
- apiClient `simTrain(runId)`.

**제외(다음):** 실제 모델 학습(지금은 6A dummy 그대로), 추론·판정 in-sim, 검사 Dashboard 제거(Phase 3), WS 공유 컨텍스트.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `app.py` | 인테이크에 manifest.json 저장 1줄 + `POST /api/sim/train` |
| `frontend/src/api/apiClient.js` | `simTrain(runId)` |
| `frontend/src/components/SimulationView.jsx` | `training` 수신 + 학습 버튼 + 진행 표시 |

## 3. 작업 명세 (What)

### 3-A. 인테이크가 manifest 저장 (app.py `/api/dataset/intake` 내)
`scan_dataset(...)` 직후, 그 work_dir에 리포트를 기록:
```python
import json
report = scan_dataset(str(arc), str(work))           # 기존
(work / "manifest.json").write_text(                  # ★ 추가: 학습이 읽을 manifest
    json.dumps(report, ensure_ascii=False), encoding="utf-8")
```
> scan 리포트는 `images`·`classes`·`n_images`를 가지므로 `run_dummy_training`이 그대로 소비 가능.

### 3-B. `POST /api/sim/train` (app.py) — 기존 6A 패턴 재사용
```python
from fastapi import Body
@app.post("/api/sim/train")
async def sim_train(payload: dict = Body(...)):
    import json, asyncio, threading
    from training.dummy_trainer import run_dummy_training
    from training.events import TRAINING_TOPIC
    from event_bus import event_bus
    run_id = payload.get("run_id")
    mpath = UPLOAD_DIR / str(run_id) / "manifest.json"
    if not run_id or not mpath.exists():
        return {"ok": False, "error": "manifest 없음 — 먼저 인테이크 필요"}
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    loop = asyncio.get_running_loop()
    def _publish(ev):                                  # /api/train/upload(L1036)과 동일 패턴
        asyncio.run_coroutine_threadsafe(event_bus.publish(TRAINING_TOPIC, ev), loop)
    threading.Thread(target=run_dummy_training,
                     args=(run_id, manifest, _publish), daemon=True).start()
    return {"ok": True, "run_id": run_id}
```

### 3-C. apiClient
```javascript
export async function simTrain(runId) {
  const { data } = await api.post('/api/sim/train', { run_id: runId })
  return data
}
```

### 3-D. SimulationView — 학습 수신 + 버튼 + 표시
import에 `simTrain` 추가. 상태:
```jsx
const [lastRunId, setLastRunId]   = useState(null)
const [trainState, setTrainState] = useState(null)   // TrainingViewer가 읽는 필드와 동일하게
```
WS onmessage에 `training` 분기 추가(agent_status 옆):
```jsx
if (d.type === 'training') {
  // ★ TrainingViewer.jsx가 training 이벤트를 파싱하는 방식과 동일한 필드로 매핑할 것
  setTrainState({ step: d.step, total: d.total_steps, status: d.status, loss: d.metrics?.loss })
}
```
인테이크 성공 시 run_id 저장(onIntake 안):
```jsx
const r = await intakeDataset(f); setLastRunId(r.run_id); setIntake(r)
```
오버레이에 버튼 + 진행:
```jsx
{lastRunId && (
  <button onClick={() => simTrain(lastRunId)}
    style={{ padding:'6px 12px', borderRadius:8, cursor:'pointer', fontSize:12,
      border:'1px solid rgba(52,211,153,0.45)', background:'rgba(52,211,153,0.12)',
      color:'#34d399', width:'fit-content' }}>
    학습 시작
  </button>
)}
{trainState && (
  <div style={{ fontSize:11, color:'#cbd5e1' }}>
    학습 {trainState.status} · {trainState.step}/{trainState.total}
    {trainState.loss != null && ` · loss ${Number(trainState.loss).toFixed(3)}`}
  </div>
)}
```
> `training` 이벤트 필드명은 **TrainingViewer.jsx가 쓰는 것과 동일하게** 맞출 것(make_training_event 출력).

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "/api/sim/train\|manifest.json" app.py
grep -n "simTrain" frontend/src/api/apiClient.js
grep -n "simTrain\|trainState\|'training'\|학습 시작" frontend/src/components/SimulationView.jsx
```

### 4-2. Headless smoke (내가 실행 — python)
- 작은 manifest(`{"images":[...],"classes":{...},"n_images":N}`)로 `run_dummy_training(run_id, manifest, collect)` 실행 → collect된 이벤트가 **`type=='training'`**, 마지막이 **`status=='done'` + loss 존재**, step이 0→n.
- 인테이크 후 `work_dir/manifest.json`이 존재하고 `images` 키를 가짐(저장 로직).

### 4-3. 회귀 가드
```
grep -c "/api/train/upload" app.py                 # 6A 업로드 학습 유지
grep -c "/api/dataset/intake" app.py                # 인테이크 유지
grep -c "getWebSocketUrl\|agent_status\|simAgents" frontend/src/components/SimulationView.jsx  # Phase 2a 보존
grep -c "SwarmChat\|TrainingViewer" frontend/src/components/Dashboard.jsx   # 엔진 보존
python -m py_compile app.py
```

### 4-4. 런타임 (당신 — "이 공간에서 배운다")
- 시뮬레이션 탭 → 데이터셋 인테이크 → SCAN·DOMAIN 칩 → **"학습 시작" 버튼** 등장 → 클릭 → **학습 진행/loss가 오버레이에서 움직임**(running→done).
- 검사 탭 학습(6A)도 여전히 정상(공유 브리지 재사용). Antigravity 녹화.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-2 python smoke(run_dummy_training 이벤트·manifest 저장), 4-3 회귀. 4-4는 Antigravity. 통과 시 — 추론·판정 in-sim 또는 인테이크→학습 **자동 연결**(버튼 없이 체이닝)으로.

## 6. 커밋
- 브랜치: `feat/phase2-training-in-sim`
- 메시지(예): `feat(sim): kick training in the simulation space after intake (reuse dummy_trainer + event_bus→WS bridge)`

## 7. 주의
- **재사용 우선** — `run_dummy_training`·event_bus→WS 브리지·`TrainingViewer` 파싱을 그대로. 새 학습기/새 브리지 만들지 말 것.
- `training` 필드명은 **make_training_event/TrainingViewer와 일치**(불일치 시 진행이 안 뜸).
- 인테이크 manifest 저장이 핵심 연결고리 — 빠지면 `/api/sim/train`이 404 처리(graceful).
- Phase 2a(인테이크·agent_status)·검사 엔진 **무변경**.
- 지금은 6A **dummy** 학습 — 실제 모델 학습은 후속. 범위 엄수.
