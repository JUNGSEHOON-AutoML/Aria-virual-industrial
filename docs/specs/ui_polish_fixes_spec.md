# ARIA UI 마감 수정 명세서 — 통합 React UI 3건 (for Antigravity IDE)

> 브랜치 `feat/unify-react-ui` 기준. 일원화는 성공했고, 새 UI의 마감 버그 3건을 고친다.
> 우선순위: ①(즉시) > ②(운영) > ③(기존 상태 불일치).

---

## ① [P1] TrainingViewer 업로드 버튼 세로 깨짐 — 확정 원인 있음

### 원인
`frontend/src/index.css`의 `.action-pill`은 **52×52px 고정 정사각형 + `flex-col`** 아이콘 버튼:
```css
.action-pill { @apply flex flex-col items-center justify-center ...; width: 52px; height: 52px; }
```
`TrainingViewer.jsx`의 업로드 `<label>`이 `action-pill`을 재사용 → "ZIP 업로드 (학습)"이 52px 세로 칸에 갇혀 글자당 1줄로 쌓임.

### 수정 (`frontend/src/components/TrainingViewer.jsx`)
업로드 `<label>`에서 **`action-pill` 제거**하고 가로 pill로 교체:
```jsx
<label
  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-white/[0.08]
             hover:border-[var(--cyan)] cursor-pointer transition-all whitespace-nowrap w-fit"
  style={busy ? { opacity: 0.5, cursor: 'not-allowed' } : {}}>
  <UploadCloud size={16} className={busy ? 'animate-bounce text-[var(--text-muted)]' : 'text-[var(--cyan)]'} />
  <span className="text-[10px] font-mono font-bold tracking-wider text-[var(--text-secondary)] whitespace-nowrap">
    {busy ? 'Ingesting ZIP...' : 'ZIP 업로드 (학습)'}
  </span>
  <input type="file" accept=".zip" hidden onChange={onPick} disabled={busy} />
</label>
```
핵심: `action-pill` 미사용 + `whitespace-nowrap` + `w-fit`(내용폭). flex 방향은 `items-center`(row).

### 수용 기준
```
grep -n "action-pill" frontend/src/components/TrainingViewer.jsx   # 업로드 라벨엔 없어야
grep -n "whitespace-nowrap" frontend/src/components/TrainingViewer.jsx  # 있어야
```
- 시각: 버튼이 **가로 한 줄**("⬆ ZIP 업로드 (학습)")로 렌더.

---

## ② [P2] MCP NODES "Initializing nodes..." — 운영(백엔드 기동) 문제

### 진단 (React는 정상)
- React: `/api/state` 2초 폴링 → `if (data.mcp_servers) setMcpServers(...)` (Dashboard L164). 정상.
- 백엔드: `/api/state`가 `mcp_client.servers`로 `servers_list` 구성해 반환(app.py L644~666). 정상.
- 따라서 **빈 목록 = 이번 런에서 MCP 서버 미기동**(mcp_client에 서버 없음). 코드 회귀 아님.

### 수정
**(a) 운영 — MCP 기동 확인 (먼저):**
```
# 좀비 없는 단일 인스턴스로 기동했는지
ss -ltnp | grep :8080
# state가 실제로 mcp_servers를 채워 주는지
curl -s localhost:8080/api/state | python3 -m json.tool | grep -A3 mcp_servers
```
- 비어 있으면 서버 기동 로그에서 `[MCP] 기동` 단계 에러 확인 → MCP 서버 정상 기동 보장.

**(b) UX — 영원히 "Initializing"으로 보이지 않게 (`Dashboard.jsx`):**
첫 폴링이 끝났는데도 비어 있으면 "연결된 MCP 노드 없음"으로 표시.
```jsx
const [mcpLoaded, setMcpLoaded] = useState(false)
// poll() 안, setMcpServers 직후:
setMcpLoaded(true)
// 렌더(L352~362):
{mcpServers.length > 0
  ? mcpServers.map(...)
  : (mcpLoaded ? '연결된 MCP 노드 없음' : 'Initializing nodes...')}
```

### 수용 기준
- MCP 기동 후 `curl .../api/state`의 `mcp_servers`가 비어있지 않고, 화면에 노드가 뜸.
- 미기동 시 화면이 "Initializing..."에 영구 고착되지 않고 "노드 없음"으로 전환.

---

## ③ [P3] VISION HUD "가동 중" vs DIAGNOSTIC "Idle" 불일치 — 기존 React 이슈

### 진단 (일원화/6A와 무관)
- HUD 오버레이는 `{isScanning && ...}`로만 표시(InspectionViewer L374) → 실제 스캔 중에만.
- 그러나 DIAGNOSTIC 패널은 **완료 시점에만 갱신** → 스캔이 오래 걸리면(이전 런 추론 167,858ms) 그 동안 HUD는 "가동 중", DIAGNOSTIC은 직전 idle(0.00) 잔상 → 모순으로 보임.
- `InspectionViewer.jsx`는 6A 포팅 전부터 있던 코드. 통합과 무관한 선재 이슈.

### 수정 (상태 단일화)
스캔 상태를 **HUD와 DIAGNOSTIC이 같은 소스**로 보게 한다.
- `InspectionViewer`는 이미 `onDiagnosticUpdate?.({ status: 'inspecting' })`를 스캔 시작 시 호출(L273). 이 status를 DIAGNOSTIC 패널이 **실제로 표시**하도록 보장:
  - DIAGNOSTIC 패널(상위 Dashboard 또는 별도 컴포넌트)에서 `status === 'inspecting'`이면 "INSPECTING / 추론 중 — {scanMs}ms"를 띄우고, Anomaly/Latency를 "Idle/0.00"로 보여주지 말 것.
  - 스캔 종료(`setIsScanning(false)`, L304/311) 시 status를 'idle'로 되돌려 양쪽 동시 idle.
- (선택) 추론 지연이 큰 경우(>몇 초) "장시간 추론 중" 힌트 노출 — 사용자 혼동 방지.

> 구현 시 Antigravity는 DIAGNOSTIC 패널이 status를 렌더하는 지점을 확인해 'inspecting' 분기를 추가할 것.

### 수용 기준
- 스캔 트리거 시 **HUD와 DIAGNOSTIC이 동시에 "추론 중"** 표시(한쪽만 idle인 모순 없음).
- 스캔 종료 시 양쪽 동시 idle.

---

## 4. 검증 절차 (내가 수행)
"푸시 완료" → `feat/unify-react-ui`(또는 새 브랜치) 재clone →
- ①: grep(`action-pill` 부재 / `whitespace-nowrap` 존재) + Antigravity 스크린샷(가로 버튼).
- ②: Antigravity가 `curl /api/state` mcp_servers 출력 + 화면 캡처 첨부.
- ③: Antigravity 녹화(스캔 중 HUD·DIAGNOSTIC 동시 "추론 중").

회귀 가드(여전히 통과해야):
```
grep -n "frontend/dist/index.html" app.py      # 서빙 일원화 유지
grep -c "/api/train/upload" app.py             # 6A 백엔드 유지
grep -c "TrainingViewer" frontend/src/components/Dashboard.jsx  # 마운트 유지
grep -c "inspect_via_registry" autonomous_agent.py             # 1~4단계 유지
```

## 5. 커밋
- 브랜치: `feat/unify-react-ui` 연속 또는 `fix/ui-polish`
- 메시지(예): `fix(ui): horizontal ZIP upload button, MCP empty-state, HUD/diagnostic state sync`

## 6. 주의
- ①만이 6A 포팅의 직접 버그 — **가장 확실·간단**하니 먼저.
- ②는 코드보다 **MCP 기동**이 핵심(좀비 프로세스 없는 단일 인스턴스로).
- ③은 선재 이슈라 범위를 "상태 단일화"로 한정 — 검사 로직 자체는 건드리지 말 것.
