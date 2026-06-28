# ARIA 명세서 — Phase 2a: 시뮬 공간에서 에이전트 파이프라인 가동 (for Antigravity)

> "이 공간에서 일이 일어난다"의 첫 증거. **가상공간에 있는 채로 데이터셋(zip/tar)을 떨어뜨리면 SCAN·DOMAIN 에이전트가 그 자리에서 깜빡인다.**
> 핵심 원칙: **엔진(검사 Dashboard·SwarmChat) 무변경.** SimulationView가 *자체 WS 리스너* + *기존 인테이크 엔드포인트 재사용*. 프론트 1파일만.

## 0. 왜 안전한가 (설계)

- 백엔드 `/api/dataset/intake`는 **이미 `agent_status`(SCAN/DOMAIN)를 WS로 broadcast**한다(인테이크 슬라이스). → 백엔드 무변경.
- `manager.broadcast`는 **연결된 모든 WS 클라이언트**에 쏜다. → SimulationView가 *두 번째 WS 클라이언트*로 붙어 같은 이벤트를 받아도 충돌 없음. SwarmChat(검사)는 그대로.
- 따라서 이번 슬라이스는 **SimulationView.jsx 한 파일** 추가만. 엔진 리스크 0.

## 1. 범위 (Scope)

**포함:**
- SimulationView에 **데이터셋 인테이크 오버레이**(zip/tar 업로드 → 기존 `intakeDataset()` → `/api/dataset/intake`).
- SimulationView에 **자체 WS 리스너**(agent_status 수신 → 라이브 에이전트 칩).
- 결과(도메인·이미지 수) 표시.

**제외(다음):**
- WS 허브를 공유 컨텍스트로 끌어올리는 리팩터(Phase 2b — 검사 은퇴의 토대).
- 시뮬 공간 내 학습/추론(Phase 2 후속), 에이전트를 3D 엔티티로(후속), 검사 Dashboard 제거(Phase 3).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/components/SimulationView.jsx` | WS 리스너 + 인테이크 오버레이 + 에이전트 칩 (추가만) |

> `getWebSocketUrl`, `intakeDataset`는 이미 `apiClient.js`에 있음(SwarmChat·인테이크 슬라이스). 재사용.

## 3. 작업 명세 (What)

### 3-A. import 추가
```jsx
import { getWebSocketUrl, intakeDataset } from '../api/apiClient'
```

### 3-B. 상태 + 자체 WS 리스너 (agent_status만)
```jsx
const [simAgents, setSimAgents]   = useState({})    // { AGENT: {state, detail} }
const [intake, setIntake]         = useState(null)  // {status|domain|n_images|error}

useEffect(() => {
  let ws
  try {
    ws = new WebSocket(getWebSocketUrl())
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        if (d.type === 'agent_status') {
          setSimAgents(a => ({ ...a, [d.agent]: { state: d.state, detail: d.detail } }))
        }
      } catch {}
    }
  } catch {}
  return () => { try { ws && ws.close() } catch {} }   // 탭 이탈 시 정리(누수 방지)
}, [])
```

### 3-C. 인테이크 핸들러 (기존 엔드포인트 재사용)
```jsx
async function onIntake(e) {
  const f = e.target.files?.[0]; if (!f) return
  setSimAgents({}); setIntake({ status: 'running' })
  try {
    const r = await intakeDataset(f)         // POST /api/dataset/intake (agent_status를 WS로 흘림)
    setIntake(r)                              // { domain, n_images, classes, ... }
  } catch (err) { setIntake({ error: String(err) }) }
}
```

### 3-D. 오버레이 (캔버스 위, 좌하단)
> 캔버스 컨테이너가 `position:relative`인지 확인(기존 컨트롤 패널이 absolute이므로 대개 이미 relative).
```jsx
<div style={{ position:'absolute', left:16, bottom:16, zIndex:10,
  display:'flex', flexDirection:'column', gap:8, fontFamily:'monospace',
  background:'rgba(11,13,18,0.72)', border:'1px solid rgba(255,255,255,0.08)',
  borderRadius:10, padding:'10px 12px', minWidth:220 }}>
  <label style={{ padding:'6px 12px', borderRadius:8, cursor:'pointer', fontSize:12,
    border:'1px solid rgba(31,184,205,0.45)', background:'rgba(31,184,205,0.12)',
    color:'#1FB8CD', whiteSpace:'nowrap', width:'fit-content' }}>
    데이터셋 인테이크 (zip/tar)
    <input type="file" accept=".zip,.tar,.tar.gz,.tgz" hidden onChange={onIntake} />
  </label>

  {/* 라이브 에이전트 칩 */}
  <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
    {Object.entries(simAgents).map(([name, s]) => {
      const c = s.state === 'done' ? '#34d399' : s.state === 'running' ? '#fbbf24' : '#6b7280'
      return (
        <span key={name} style={{ fontSize:11, padding:'2px 8px', borderRadius:6,
          border:`1px solid ${c}66`, color:c, background:`${c}14` }}>
          {name} · {s.state}
        </span>
      )
    })}
  </div>

  {/* 결과 */}
  {intake?.status === 'running' && <span style={{ fontSize:11, color:'#9aa0aa' }}>인테이크 가동 중…</span>}
  {intake?.domain && <span style={{ fontSize:11, color:'#cbd5e1' }}>도메인: {intake.domain} · {intake.n_images}장</span>}
  {intake?.error && <span style={{ fontSize:11, color:'#f87171' }}>오류: {intake.error}</span>}
</div>
```

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "getWebSocketUrl\|intakeDataset" frontend/src/components/SimulationView.jsx
grep -n "agent_status\|simAgents\|onIntake" frontend/src/components/SimulationView.jsx
```

### 4-2. 회귀 가드 (엔진 무변경 확인 — 가장 중요)
```
grep -c "getWebSocketUrl\|onTrainingUpdate\|agent_status" frontend/src/components/SwarmChat.jsx   # 검사 WS 허브 그대로 >0
grep -c "SwarmChat\|TrainingViewer\|AgentSwarm" frontend/src/components/Dashboard.jsx              # 엔진 유지
grep -c "/api/dataset/intake" app.py                # 인테이크 엔드포인트 그대로(백엔드 무변경)
grep -c "Canvas\|sampleSceneParams\|captureDataset" frontend/src/components/SimulationView.jsx     # SIM-1~4 보존
```

### 4-3. 빌드
- `npm run build` 무에러 + 8080 반영.

### 4-4. 런타임 (당신 — "이 공간에서 일이 일어난다")
- **시뮬레이션 탭(랜딩)** 에서 좌하단 **데이터셋 인테이크 (zip/tar)** 로 데이터셋 업로드.
- **3D 공간 오버레이에 SCAN·DOMAIN 칩이 running→done으로 깜빡**이고, 끝나면 **도메인·이미지 수** 표시.
- 동시에 검사 탭의 스웜·학습이 여전히 정상(엔진 무변경). Antigravity 녹화 첨부.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep(WS·인테이크 배선), **4-2 회귀(엔진/SIM 보존)**. 4-3 빌드·4-4 가동은 Antigravity. 통과 시 — **Phase 2b: WS 허브를 공유 컨텍스트로 끌어올리기**(검사 은퇴의 토대) 또는 시뮬 내 학습/추론으로.

## 6. 커밋
- 브랜치: `feat/phase2a-pipeline-in-sim`
- 메시지(예): `feat(sim): dataset intake + live agent chips inside the simulation space (reuse intake endpoint + own WS)`

## 7. 주의
- **SwarmChat·Dashboard·백엔드 무변경** — SimulationView에 *추가만*. 엔진을 옮기는 건 Phase 2b.
- WS는 **두 번째 클라이언트**로 붙는 것뿐(중복 연결 OK). 단 **unmount 시 close**(누수 방지) 꼭.
- 인테이크는 **기존 `/api/dataset/intake` 재사용** — 새 엔드포인트 만들지 말 것.
- 캔버스 컨테이너 `position:relative` 확인(오버레이 기준).
- 범위 엄수: 학습/추론 in-sim, 검사 제거는 다음. 지금은 **"시뮬에서 데이터 넣으면 에이전트가 거기서 가동"** 까지.
