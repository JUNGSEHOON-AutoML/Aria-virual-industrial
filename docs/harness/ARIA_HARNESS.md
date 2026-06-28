# ARIA Harness — 에이전트 아키텍처 명세

## 시스템 개요

ARIA (Anomaly Reasoning Intelligence Agent)는 **감독자(Supervisor) 패턴**으로 동작하는
자율 멀티 에이전트 시스템이다.

```
사용자 요청 (웹 대시보드)
        │
        ▼
AutonomousAgent (진입점)
        │
        ├─ Direct Actions (LLM 없이 즉시 실행)
        ├─ Pre-Router (키워드 기반 직접 도구 호출)
        │
        ▼
AgentOrchestrator (두뇌 — Supervisor 패턴)
        │
        ├─ ROUTER  (deepseek-r1/qwen2.5:14b → 다음 노드 결정)
        │
        ├─ VISION  → VisionAgent → VisionRouter → ModelDiscovery (7단계 파이프라인)
        ├─ DIPLOMAT → 웹 검색 + 팩트체크 (qwen2.5:14b)
        ├─ PHYSICAL → MCP 도구 실행 (ReAct 루프, 최대 8스텝)
        ├─ OPERATOR → 자율 작업 (ReAct 루프)
        ├─ CHAT    → 대화 처리 (qwen2.5:14b)
        └─ CRITIC  → 실패 시 자가 수정 (Self-Healing, 최대 3회)
```

## 핵심 에이전트 역할

### ROUTER 노드
- **모델**: `qwen2.5:14b`
- **역할**: 사용자 의도를 파악하여 적절한 노드로 라우팅
- **하네스**: `harness/router_harness.md`
- **출력**: `{"next_agent": "VISION|DIPLOMAT|PHYSICAL|OPERATOR|CHAT|CRITIC|END", "reason": "..."}`

### VISION 노드
- **모델**: `qwen2.5vl:7b` (VLM)
- **역할**: 이미지/PDF 분석, 결함 탐지, 이상치 감지
- **파이프라인**: VisionRouter → ModelDiscovery (arXiv + HF + timm 탐색 → 모델 선택 → 추론 → 검증)
- **핵심 알고리즘**: CCIFPS (My Proposed Algorithm) — 수학적 이상 탐지

### DIPLOMAT 노드
- **모델**: `qwen2.5:14b`
- **역할**: 웹 검색 + 팩트체크 + 최종 보고서 생성
- **도구**: `web_search`, `search_arxiv`

### PHYSICAL 노드
- **모델**: `qwen2.5:14b`
- **역할**: 터미널 명령 실행, 파일 조작, 시스템 제어
- **도구**: `filesystem`, `shell_exec` (MCP)
- **안전장치**: HITL (Human-in-the-Loop) 승인 게이트

### CHAT 노드
- **모델**: `qwen2.5:14b`
- **역할**: 자연어 대화, 검색 요청, 코드 생성
- **패턴**: 코드 블록 감지 시 → PHYSICAL 노드에 자동 핸드오프

### CRITIC 노드
- **모델**: `qwen2.5:14b`
- **역할**: 실패 분석 + 자가 수정 전략 생성
- **Self-Healing**: 최대 3회 재시도 후 실패 처리

## MCP 서버 구성

| 서버 | 우선순위 | 도구 |
|------|----------|------|
| filesystem | 필수 | read_file, write_file, list_directory |
| shell_exec | 필수 | run_command, run_python |
| web_search | 필수 | search_web, read_webpage |
| arxiv | 필수 | search_arxiv, download_paper |
| huggingface | 선택 | search_models, search_datasets |
| youtube | 선택 | search_youtube |
| weather | 선택 | get_weather |
| google-workspace | 선택 (OAuth) | gmail.search, drive.search |

## Harness 원칙

1. **단일 진입점**: `app.py` (uvicorn) → `start_aria.sh` 하나만 실행
2. **단계적 MCP 로딩**: 필수 4개 먼저 → 선택 서버 10초 지연
3. **Circuit Breaker**: 라우팅 루프 최대 5스텝
4. **Self-Healing**: CRITIC 노드 최대 3회 재시도
5. **Doom Loop 방지**: `tried_models` 리스트 + 이미 실행된 노드 재방문 금지
