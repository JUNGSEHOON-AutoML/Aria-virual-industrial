# ARIA 프로젝트 구조 (리팩토링 v0.2)

이 문서는 평면적으로 흩어져 있던 루트 스크립트를 **단일 `aria/` 패키지 + 도메인별 하위 패키지**로
재편한 결과를 정리한다. 설계 로직은 두 참고 프로젝트에서 가져왔다.

| 참고 프로젝트 | 차용한 설계 로직 |
|---|---|
| `mobile_robot_Simulation` (ROS+Gazebo) | 관심사를 독립 패키지로 분리(perception / simulation / control), 이벤트 버스로 연결 |
| `xlerobot-learning-guide` | 계층형 구조 + 코드와 문서(`docs/`) 분리 |

## 새 디렉토리 구조

```
aria/                     # 단일 파이썬 소스 루트
├── api/  ← (진입점 app.py 는 루트 유지, 호환성 위해)
├── perception/           # 이상탐지·비전 (감각)  = darknet_ros 역할
│   ├── vision_router.py · cmdiad_inference.py · threshold_calibrator.py
│   ├── detectors/ · scorer/ · intake/
├── simulation/           # 가상 공장 데이터/결함 + FAT 게이트 = Gazebo 역할
│   ├── dataset.py · defects.py
│   └── validation/
├── agents/               # 스웜 노드 (행동) = control nodes 역할
│   ├── base_agent.py · vision_agent.py · ... · autonomous_agent.py · local_agent.py
├── orchestration/        # 스웜 라우팅/상태/이벤트 = ROS 토픽 버스 역할
│   ├── agent_orchestrator.py · harness_loop.py · state_manager.py · event_bus.py
├── mcp/                  # Model Context Protocol
│   ├── mcp_client.py
│   └── servers/          # filesystem · system · database · huggingface · shell_exec
├── learning/             # 자가개선/모델탐색/학습
│   ├── self_improvement_loop.py · model_discovery.py · model_scout.py
│   └── training/
└── core/                 # 공통 인프라
    ├── database.py · product_registry.py
    ├── config/ (backbone·models·vlm) · resource/ · utils/

docs/                     # 모든 설계 문서 (코드와 분리)
├── specs/   ← 루트 *_spec.md + 구 files/*
├── harness/ ← 구 harness/*.md
├── protocol/← 구 agent_bridge/PROTOCOL.md
└── report/  ← 구 report/main.tex
```

## 이동 매핑 (old → new)

| 이전 위치 | 새 위치 |
|---|---|
| `agent_orchestrator.py` `harness_loop.py` `state_manager.py` `event_bus.py` | `aria/orchestration/` |
| `agents/` `autonomous_agent.py` `local_agent.py` | `aria/agents/` |
| `vision_router.py` `cmdiad_inference.py` `threshold_calibrator.py` `detectors/` `scorer/` `intake/` | `aria/perception/` |
| `sim/` `validation/` | `aria/simulation/`, `aria/simulation/validation/` |
| `mcp_client.py` `mcp_servers/` | `aria/mcp/mcp_client.py`, `aria/mcp/servers/` |
| `model_discovery.py` `model_scout.py` `self_improvement_loop.py` `training/` | `aria/learning/` |
| `database.py` `product_registry.py` `config/` `resource/` `utils/` | `aria/core/` |
| 루트 `*_spec.md` · `files/` · `harness/` · `agent_bridge/` · `report/` | `docs/` |

## 의도적으로 루트에 남긴 것 (안전상 deviation)

런타임에서 검증할 수 없는(MVTec 데이터·conda·ollama 부재) 환경이라, **거동을 바꿀 수 있는 항목은 이동하지 않았다.**

- **`app.py`** — `uvicorn app:app` 진입점. 내부 import 만 `aria.*` 로 갱신했고 위치는 유지(BASE_DIR / static / frontend 경로 안정성).
- **`backend/main.py`** — `uvicorn backend.main:app` 호환 래퍼. 그대로 동작.
- **`src/patchcore/`** — `import patchcore...` 절대 임포트를 쓰는 벤더링된 알고리즘. src-layout 유지.
- **`memory_bank.npy` · `products/` · `uploads/` · `models/` · `static/`** — 문자열 경로로 참조되는 런타임/데이터. 이동 시 무검증 파손 위험이 있어 보류.

## 검증 방법

리팩토링 후 다음으로 정합성을 확인했다.

```bash
# 1) 이동된 모듈에 대한 stale import 0건 확인 (AST 스캔)
# 2) 전체 .py py_compile 통과
# 3) aria 패키지 import 해석 정상 (외부 의존성 제외)
python -c "import aria, aria.orchestration.event_bus, aria.core.config.models"
```

import 경로 외에 바뀐 설정 파일: `mcp_config.json` 의 서버 스크립트 경로
(`mcp_servers/*.py` → `aria/mcp/servers/*.py`).
