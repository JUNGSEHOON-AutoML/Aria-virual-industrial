# gemini 명세 — 서브에이전트 실작동화 (MCP·DB·위임)

> [!IMPORTANT]
> front/back/docker/detector 레지스트리는 이미 반영 완료. 이 명세는 **남은 블로커**만 다룬다:
> ① MCP 서버 설정↔기동↔대시보드 정합, ② DB agent_memory/learning_state 실배선, ③ 서브에이전트 위임 증명.
> 모든 항목은 **현재 상태(증거) → 목표(관찰 가능) → 금지 → 제출 증거** 형식. "되었습니다"가 아니라 **실제 로그/JSON/스크린샷**으로만 인정.

> [!WARNING]
> gemini에게 지시하는 법: "파일 고쳐라"가 아니라 **"이 입력을 넣으면 이 결과가 보여야 한다"**. 검증은 **mock·문자열 grep 금지, 실제 런타임 산출물 첨부**.

---

## 1. (최우선) MCP 서버 — 설정·기동·표시 정합

### 현재 상태 (증거)
`mcp_config.json`에 실제 정의된 서버: **filesystem, system, database, huggingface** (4개).
그런데 `app.py`는 없는 서버를 기동 시도:
```
ESSENTIAL_SERVERS = ["filesystem", "shell_exec", "web_search", "arxiv"]   # 3개가 config에 없음
OPTIONAL_SERVERS  = ["huggingface", "youtube", "weather", "kaggle", "google-workspace", "notion"]  # huggingface 외 전부 없음
```
→ system·database는 어느 목록에도 없어 기동 안 됨. 살아남는 건 huggingface(±filesystem)뿐. 그래서 research/code 서브에이전트가 호출할 도구가 없어 항상 Idle.

### 목표 (관찰 가능)
- `app.py`의 기동 목록과 `mcp_config.json`이 **정확히 일치**. 둘 중 하나를 진실로 정해 동기화:
  - (택1-A) config에 있는 4개(filesystem, system, database, huggingface)만 기동하도록 app.py 목록 수정, **또는**
  - (택1-B) research에 정말 필요하면 web_search/arxiv 서버 스크립트를 `mcp_servers/`에 실제로 추가하고 config에 등록.
- 대시보드 MCP NODES는 **런타임에 실제 기동 성공 + 도구≥1개인 서버만 LIVE**로 표시. 실패는 표시 안 함(또는 error+사유).
- 각 서브에이전트(특히 research/code)가 **실제 기동된 도구 목록**을 받아 호출 가능.

### 금지
- config에 없는 서버명을 기동 목록에 남겨두는 것.
- config에 정의돼도 기동 안 한 서버(system/database)를 방치하는 것.
- 설정 파일만 읽어 무조건 LIVE로 표시하는 것.

### 제출 증거
- `app.py` 기동 목록과 `mcp_config.json` 키가 일치함을 보이는 diff.
- 백엔드 기동 로그: 각 서버 `시작 완료`/`실패(사유)`.
- `GET /api/mcp/servers` 응답 JSON 전문 (LIVE 서버 + 각 도구 수).

---

## 2. DB agent_memory / learning_state 실배선 (협업·기억)

### 현재 상태 (증거)
`database.py`에 `analysis_history`, `agent_memory`, `learning_state` 3테이블 생성. 그러나 `agent_orchestrator.py`에서 `agent_memory`·`learning_state` 사용 **0건** (analysis_history만 app.py가 기록). → 서브에이전트 간 작업 내 공유·세션 간 학습 배선 없음.

### 목표 (관찰 가능)
- **agent_memory = 작업(task) 단위 공유 스크래치패드.** 한 분석/질의 동안 각 서브에이전트가 자기 결과를 기록하고, 다음 에이전트가 **이전 에이전트의 결과를 읽어** 활용. (예: vision의 detector 결과를 synthesizer가 DB에서 읽어 요약)
- **learning_state = 세션 간 상태.** 예: 제품별 임계값 캘리브레이션 결과, 자주 쓰인 detector, 사용자 선호. 다음 기동 때 재사용.
- 한 번의 멀티에이전트 실행 후 **두 테이블에 실제 행이 쌓여야** 함.

### 금지
- 테이블만 만들고 읽기/쓰기 없이 두는 것(현재 상태).
- 모든 상태를 메모리 전역변수로만 들고 재기동 시 소실시키는 것.

### 제출 증거
- 질의 1회 실행 → `SELECT * FROM agent_memory WHERE task_id=...` 결과(여러 에이전트 행) 첨부.
- 재기동 후 `learning_state`에서 이전 값이 복원됨을 보이는 로그.

---

## 3. 서브에이전트 위임이 실제로 일어남을 증명

### 현재 상태
Router→Synthesizer만 도는 정황(research/code/verifier가 Idle). §1·§2가 선행되어야 가능.

### 목표 (관찰 가능)
- 도구가 필요한 질의(예: "최신 이상탐지 논문 찾아서 우리 결과와 비교해줘") →
  - **research LED 점등** + 그 에이전트가 **실제 MCP 도구를 호출**(WS `tool` 메시지에 기록).
  - 결과가 synthesizer로 모여 최종 답에 반영.
- Router 프롬프트에 **§1에서 실제 기동된 도구 목록**을 주입해, LLM이 도구를 실제로 선택하게 함.

### 금지
- 도구 목록을 주지 않아 LLM이 도구를 못 부르는 것.
- 항상 huggingface.search_models 하나만 호출하는 고정 배선.

### 제출 증거
- 위 질의 1회의 **WS 메시지 로그 전문**: `agent_status`(research running→ok) + `tool` 호출 기록 포함.

---

## 4. (검증) 이미지 종류별 출력 분기 — 회귀 확인

> vision_agent에서 `판정` 문자열은 0건으로 확인됨. 끝단(synthesizer/터미널)까지 분기가 유지되는지만 검증.

### 목표
- **문서·표 이미지** → 이상 판정/결함확률 없이 **내용 추론 자연어**. `[판정]/[소견]/[조치]` 0건.
- **산업 제품 이미지** → detector 수치 기반 pass/fail + 히트맵.

### 제출 증거
- 표 이미지 1장 출력 전문(`[판정]` 0건, 표 설명 자연어 존재) + 산업 이미지 1장 출력(verdict+heatmap) 대조.

---

## 우선순위
1. **§1 MCP 정합** — 도구가 살아야 서브에이전트가 일한다. 다른 모든 것의 전제.
2. **§2 DB 배선** — 에이전트 협업·기억의 토대.
3. **§3 위임 증명** — §1·§2 위에서 LED+tool 로그로 확인.
4. **§4 출력 분기 회귀 확인.**

> [!NOTE]
> §1을 먼저 끝내고 그 증거(기동 로그 + /api/mcp/servers JSON)를 제출한 뒤 §2로. 한 번에 다 했다고 보고하지 말 것. 증거 없는 항목은 미완료.
