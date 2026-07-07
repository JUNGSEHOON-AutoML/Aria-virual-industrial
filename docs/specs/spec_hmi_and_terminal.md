# gemini 명세 — 검사시스템 HMI 외관 + Agent Terminal 인터랙티브화

> [!IMPORTANT]
> 결과물(이미지 분석)은 이미 양호. 이 명세는 **UI 외관(검사기 신호등)** 과 **Agent Terminal 동작**만 다룬다.
> 검증은 "되었습니다"가 아니라 **실제 화면 녹화/스크린샷 + WS 로그**로만 인정.

---

## 1. 검사시스템 HMI 외관 — 적층 신호등(타워 라이트/안돈) 도입

### 목표
실제 공장 검사기처럼, 시스템 상태를 **적층 신호등(tower light)** 으로 표시. 적색/황색/녹색이 상태에 따라 점등·점멸·글로우. FAIL이면 대시보드 테두리가 경광등처럼 깜빡.

### 상태 매핑 (분석 결과 verdict + 시스템 상태로 구동)
| 상태 | 신호등 | 의미 |
|---|---|---|
| `idle` | 전체 소등(흐림) | 대기 |
| `inspecting` | 황색 점멸 + 글로우 | 분석 진행 중 |
| `pass` | 녹색 점등 + 은은한 글로우 | 정상 판정 |
| `fail` | 적색 빠른 점멸 + 글로우 + 화면 테두리 경광 | 결함 판정 |
| `content` | 청색 점등 | 일반 이미지(내용 설명 모드, 판정 없음) |

### [NEW] `frontend/src/components/StatusBeacon.jsx`
```jsx
const LABELS = { idle:'STANDBY', inspecting:'INSPECTING', pass:'PASS', fail:'DEFECT', content:'CONTENT' }
export default function StatusBeacon({ state = 'idle' }) {
  return (
    <div className={`beacon beacon--${state}`} role="status" aria-label={LABELS[state]}>
      <div className="beacon__lamps">
        <span className="lamp lamp--red" />
        <span className="lamp lamp--amber" />
        <span className="lamp lamp--green" />
        <span className="lamp lamp--blue" />
      </div>
      <div className="beacon__label">{LABELS[state]}</div>
    </div>
  )
}
```

### [NEW] CSS (frontend/src/index.css 등) — 점멸·글로우·경광 키프레임
```css
.beacon{display:flex;flex-direction:column;align-items:center;gap:8px}
.beacon__lamps{display:flex;flex-direction:column;gap:6px;padding:8px;border-radius:8px;
  background:#0b0e14;border:1px solid #1c2230}
.lamp{width:26px;height:26px;border-radius:50%;opacity:.12}
.lamp--red{color:#ff4d4d;background:#ff4d4d}
.lamp--amber{color:#ffb020;background:#ffb020}
.lamp--green{color:#27d07a;background:#27d07a}
.lamp--blue{color:#3aa0ff;background:#3aa0ff}
.beacon__label{font:600 12px/1 var(--font-mono,monospace);letter-spacing:2px;color:#7f8b9e}

@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:.12}}
@keyframes glow{0%,100%{box-shadow:0 0 6px 1px currentColor}50%{box-shadow:0 0 20px 5px currentColor}}
@keyframes alarm{0%,100%{box-shadow:inset 0 0 0 0 rgba(255,77,77,0)}50%{box-shadow:inset 0 0 140px 0 rgba(255,77,77,.30)}}

.beacon--inspecting .lamp--amber{opacity:1;animation:blink 1s steps(1) infinite, glow 1.2s ease-in-out infinite}
.beacon--pass .lamp--green{opacity:1;animation:glow 2.2s ease-in-out infinite}
.beacon--fail .lamp--red{opacity:1;animation:blink .55s steps(1) infinite, glow .55s ease-in-out infinite}
.beacon--content .lamp--blue{opacity:1;animation:glow 2.4s ease-in-out infinite}

/* FAIL 시 대시보드 전체 경광등 */
.dashboard--alarm{animation:alarm 1s ease-in-out infinite;border-radius:12px}
```

### 배선
- 분석 응답 도착 시 verdict로 beacon state 설정: `pass`/`fail`/`content`(general_object), 분석 중엔 `inspecting`, 평상시 `idle`.
- `fail`일 때 최상위 대시보드 컨테이너에 `dashboard--alarm` 클래스 토글.
- 기존 AGENT SWARM MONITOR LED도 `running`일 때 `animation:glow`를 약하게 적용해 "살아있는" 느낌 통일.
- StatusBeacon은 상단 헤더(또는 VISION HUD 우상단)에 배치해 한눈에 들어오게.

### 금지
- 점멸/글로우를 항상 켜두는 것(상태와 무관한 장식 애니메이션 금지). 상태 머신에 묶을 것.
- light 테마 강제(검사기 HMI는 다크 유지).

### 증거
idle/inspecting/pass/fail/content **각 상태 스크린샷 5장** + fail 시 테두리 경광 점멸 녹화.

---

## 2. Agent Terminal — 분석 에코 제거하고 인터랙티브 채팅으로

### 현재 상태 (증거)
- app.py가 이미지 분석 결과를 채팅과 **같은 WS 채널**로 broadcast:
  `app.py:858 manager.broadcast(result_data)`, `app.py:922/958 manager.broadcast({"type":"response","content":obs})`.
- `SwarmChat.jsx:145 case 'response': addMessage('agent', data.content)` → 터미널이 분석 설명을 ARIA 메시지로 그대로 렌더 → **중복 에코**.

### 목표 (관찰 가능)
- **채널 분리**: 모든 WS 메시지에 `source` 필드 부여.
  - 이미지 분석 산출물 → `source:"analysis"` → **Diagnostic Report 패널 전용.**
  - 채팅 응답/사고 → `source:"chat"` (+ `thought`/`tool`/`agent_status`) → **Agent Terminal 전용.**
- **터미널은 `source:"analysis"` 메시지를 ARIA로 렌더하지 않는다.** 굳이 알리려면 한 줄 시스템 노티("🔬 분석 완료 — 우측 리포트 참조")만.
- **타이핑 → 즉각 반응형**: 사용자가 입력하면(이미 `{type:'chat'}` 전송됨) 오케스트레이터가 돌며 `thought`→`tool`→`response(source:chat)`가 터미널에 **실시간 스트리밍**. 그 응답은 Diagnostic Report에는 안 뜬다.

### [MODIFY] app.py
- 분석 경로의 broadcast에 `"source":"analysis"` 추가(858·922·958 등).
- `/ws/chat`(1551~)의 채팅 응답 broadcast에 `"source":"chat"` 추가.

### [MODIFY] frontend/src/components/SwarmChat.jsx
- `ws.onmessage`에서 `data.source === 'analysis'`면 ARIA 메시지로 추가하지 말 것(무시 또는 1줄 시스템 노티).
- `response`는 `source==='chat'`일 때만 `addMessage('agent', ...)`.
- `agent_status`/`thought`/`tool`은 그대로 받아 LED·로그에 반영.

### 금지
- 분석 결과와 채팅 응답이 같은 `type:"response"`로 구분 없이 섞이는 것.
- 타이핑 응답을 Diagnostic Report에 띄우는 것(반대도 금지).

### 증거
- 이미지 업로드 → **터미널엔 분석 설명 전문이 안 뜨고**(최대 1줄 노티), Diagnostic Report에만 표시되는 스크린샷.
- 터미널에 질문 타이핑 → `thought`→`response`가 실시간으로 흐르고 그 답이 리포트엔 안 뜨는 녹화 + 그때의 WS 로그(`source` 필드 보임).

---

## (참고) 성능 — "검사기"라면 357초는 너무 느림
로그상 일반 이미지 1장에 357초(VLM Inspector 73초 + debate + HF MCP 탐색). 검사기 느낌을 살리려면:
- `content`/`general_object` 도메인에선 **vlm_inspector escalation·debate를 생략**(이미 YOLO로 충분). debate는 산업 제품 모호 케이스에만.
- HuggingFace MCP 모델 탐색을 **분석 요청 경로에서 동기 호출하지 말 것**(별도 비동기/사용자 요청 시에만).
- 목표: 일반 이미지 < ~15초. (별도 항목으로 진행)

---

## 우선순위
1. **§2 터미널 채널 분리** — 동작 혼란 즉시 해소(작고 명확).
2. **§1 신호등 HMI** — 검사기 외관.
3. (참고) 성능 가드.

> [!NOTE]
> §2 먼저 끝내고 증거(WS 로그 + 스크린샷) 제출 후 §1. 한 번에 다 했다고 보고 금지.
