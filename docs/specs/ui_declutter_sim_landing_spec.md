# ARIA 명세서 — UI 재편(시뮬레이션 랜딩) + 군더더기 정리 (Tier 1, 안전) for Antigravity

> "열면 가상공간 + 쓸데없는 UI 제거." 단, **일괄 삭제 금지** — 물려 있는 건 보존한다.
> 이 슬라이스는 **UI에서 치우기**만(되돌리기 쉬움). 파일/엔드포인트 *삭제*는 별도 "죽은 코드 감사" 패스.

## 0. 안전 경계 (먼저 읽기)

- **삭제 금지:** `SwarmChat.jsx` — WebSocket 허브(`agent_status`·`training` 라우팅). 지우면 스웜·학습·인테이크 에이전트 표시가 전부 깨짐. → **채팅 입력 UI만** 제거, WS/로그 보존.
- **건드리지 않음:** `templates/`·`static/js/main.js`(app.py가 `/static` 마운트·Jinja 참조 중), 백엔드 `/api/quick`·chat 엔드포인트 — 별도 패스.

## 1. 범위 (Scope)

**포함(Tier 1, 안전):**
1. 랜딩 뷰 → **시뮬레이션**(App 기본값).
2. QUICK ACTIONS에서 **HF검색·파일시스템 버튼+핸들러 제거**(검사 이력 유지).
3. **Agent Terminal 채팅 입력창 제거** — `SwarmChat`의 WS 연결·메시지 처리·로그 렌더는 **그대로 유지**.

**제외(다음 패스):** templates/static 파일 삭제, 백엔드 죽은 엔드포인트 제거(import 그래프 감사 후).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/App.jsx` | `useState('inspection')` → `useState('simulation')` |
| `frontend/src/components/Dashboard.jsx` | `handleHuggingFace`·`handleFilesystem` 및 두 버튼 제거 (handleHistory/검사 이력 유지) |
| `frontend/src/components/SwarmChat.jsx` | 채팅 **입력 `<input>`+전송 버튼/핸들러만** 제거 — `useEffect` WS·`onmessage`·로그 렌더는 손대지 말 것 |

## 3. 작업 명세 (What)

### 3-A. App.jsx — 시뮬레이션 랜딩
```jsx
const [view, setView] = useState('simulation')   // inspection → simulation
```
(탭 3개·렌더 분기는 그대로. 시작 화면만 가상공간으로.)

### 3-B. Dashboard.jsx — HF/파일시스템 퀵액션 제거
- `handleHuggingFace`, `handleFilesystem` 함수 삭제.
- QUICK ACTIONS 버튼 배열에서 두 항목 삭제, **검사 이력만 남김**:
```jsx
// 기존(L372~374) → HF·파일시스템 줄 제거, 아래만 유지
{ label: '📊 검사 이력 조회', color: 'var(--violet)', onClick: handleHistory },
```
- `handleHistory`·`qaModal`·`ApprovalModal` 등 나머지는 유지.

### 3-C. SwarmChat.jsx — 입력창만 제거 (WS 보존)
- **유지(절대 손대지 말 것):** `useEffect`의 `new WebSocket(getWebSocketUrl())`, `ws.onmessage`, `agent_status`/`training` 분기(L120~206), 로그/메시지 렌더.
- **제거:** 하단 채팅 `<input>` + 전송 버튼 + `sendChatHttp` 호출 핸들러(자유 입력 부분).
- 결과: "Agent Terminal"은 **읽기 전용 활동 로그**가 되고, WS 심장은 그대로 뛴다.
> 패널 제목을 "AGENT TERMINAL" → "ACTIVITY LOG"로 바꿔도 좋음(선택).

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "useState('simulation')" frontend/src/App.jsx                 # 랜딩=시뮬
grep -c "handleHuggingFace\|handleFilesystem" frontend/src/components/Dashboard.jsx   # → 0
grep -c "handleHistory\|검사 이력" frontend/src/components/Dashboard.jsx               # > 0 (유지)
# SwarmChat WS 심장 보존 확인:
grep -c "getWebSocketUrl\|onTrainingUpdate\|agent_status" frontend/src/components/SwarmChat.jsx  # > 0
grep -c "sendChatHttp" frontend/src/components/SwarmChat.jsx           # 입력 제거로 0 또는 미사용
```

### 4-2. 빌드 (Antigravity)
- `npm run build` 에러 없음 + **빌드 후 8080 반영**(dist 갱신).

### 4-3. 회귀 가드 (심장 보존 확인 — 가장 중요)
```
grep -c "SwarmChat" frontend/src/components/Dashboard.jsx   # 여전히 마운트 >0 (WS 허브 유지)
grep -c "TrainingViewer\|AgentSwarm\|HardwarePanel" frontend/src/components/Dashboard.jsx  # 코어 유지
grep -c "frontend/dist/index.html" app.py                   # 서빙
grep -c "/api/train/upload\|/api/sim/dataset\|get_snapshot" app.py  # 6A·SIM·HW 유지
```

### 4-4. 런타임 (당신/Antigravity)
- 앱 열면 **바로 시뮬레이션(가상공간)** 이 뜨는지.
- 검사 탭으로 가면 — QUICK ACTIONS에 **HF·파일시스템 없고 검사 이력만**, Agent Terminal에 **입력창 없이 로그만**.
- **학습 패널·스웜·하드웨어가 여전히 작동**(SwarmChat WS 살아있음). ZIP 업로드 시 학습 진행 뜨는지로 확인.
- Antigravity 녹화 첨부.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-3 회귀(특히 SwarmChat WS 보존). 4-2 빌드·4-4는 Antigravity. 통과 시 — **"죽은 코드 감사"**(templates/static·죽은 엔드포인트를 import 그래프 확인 후 안전 제거)를 별도 슬라이스로.

## 6. 커밋
- 브랜치: `chore/ui-declutter-sim-landing`
- 메시지(예): `chore(ui): simulation as landing, drop HF/filesystem quick actions, strip chat input (keep WS hub)`

## 7. 주의 (꼭)
- **`SwarmChat` 컴포넌트·WS·메시지 처리 절대 삭제 금지** — 입력 UI만. WS가 끊기면 스웜·학습·인테이크 에이전트 표시가 모두 죽는다.
- **templates/·static/ 파일 rm 금지** — app.py L43/89/92가 참조. 별도 패스에서 app.py와 함께 좌표 맞춰 제거.
- 백엔드 죽은 엔드포인트는 이번에 손대지 않음.
- 이건 *되돌리기 쉬운 UI 정리*다. 진짜 파일 삭제는 import 그래프를 확인하고 한 조각씩.
