# ARIA V2 파일별 구현·이행 계획

작성: 2026-10-07. 상태: **감사 및 계획만 작성. 제품 코드 구현 미착수.**
구조·소유권·좌표계·스키마: `ARIA_V2_ARCHITECTURE.md`.

## 0. 먼저 고정할 것

- 기존 DES/CCIFPS/robot/patrol/FreeCAD/QC Live/승인 흐름을 보존한다.
- canonical schema와 ID·축·단위 계약은 Phase0에서 정한다. 승인 저장소 전환만 Phase5에서 한다.
- 현재 모델 m/s/rad/Y-up 유지 권고. 임의 factory 치수·최적 공정 설정을 새로 선택하지 않는다.
- 기존 V1 graph와 신규 demonstration preset을 분리한다. 기존 AI-INSPECTION을 VISION-01로 강제 rename하지 않는다.
- 이행용 feature flag로 legacy Factory 화면에 접근 가능하게 유지한다.
- 각 phase는 backend regression·production build·browser console/HTTP·관련 사용자 동작 확인 후 완료 판정한다. API만 통과한 단계는 화면 완료가 아니다.

## 1. 파일별 변경 목록

신규 경로는 모두 **계획 경로**이며 아직 생성된 기능이 아니다. 기존 경로는 이번 감사에서 존재를 확인했다.

### Phase 0 — 계약과 기준 측정

| 경로 | 종류 | 변경/검증 |
|---|---|---|
| `docs/ARIA_V2_ARCHITECTURE.md` | 신규 문서 | 현재/목표 구조, 소유권, 충돌, 경계 |
| `docs/ARIA_V2_IMPLEMENTATION_PLAN.md` | 신규 문서 | 본 계획 |
| `aria/twin/contracts.py` | 신규 예정 | StaticTwin/RuntimeSnapshot/EventEnvelope 형식과 version |
| `aria/twin/compat.py` | 신규 예정 | V1 계약 읽기·roundtrip; 원본 파일 불변 |
| `aria/twin/__init__.py` | 신규 예정 | 범위 제한 모듈 |
| `tests/test_twin_contract.py` | 신규 예정 | m/mm/cm·axis roundtrip, ID 참조, 누락·불명확 정보 거절 |
| `tools/benchmark_control_tower.mjs` | 신규 예정 | 기존/새 UI 동일 브라우저·viewport·scenario 성능 수집; 사용 가능한 브라우저 제어 환경 확인 후 구현 |

기준 측정: 1440×900/1920×1080, 같은 scene/seed/speed/제품수, GPU 또는 software renderer 명시. FPS 평균·p95 frame time·React commit 수·WS bytes/s·API p95·메모리·초기 로딩을 기록한다. 실제 측정 전 개선율 약속 없음.

### Phase 1 — Overview와 기존 3D·실제 telemetry

| 경로 | 종류 | 변경/검증 |
|---|---|---|
| `frontend/src/hmi/AppShell.jsx` | 수정 | Overview 기본 진입과 legacy/QC 전환 |
| `frontend/src/hmi/factory/FactoryWorkspace.jsx` | 점진 축소 | 기존 화면 wrapper, 기능 보존 |
| `frontend/src/features/control-tower/ControlTowerShell.jsx` | 신규 | top/nav/viewport/inspector/timeline 레이아웃 |
| `frontend/src/features/control-tower/Overview.jsx` | 신규 | 실제 backend KPI, stale/source 표시 |
| `frontend/src/features/control-tower/controlTower.css` | 신규 | 밝은 산업 대시보드, 두 해상도 대응 |
| `frontend/src/shared/factoryApi.js` | 신규 | 기존 API helper 이동; 오류 형식 유지 |
| `frontend/src/shared/factoryConnection.js` | 신규 | 기존 WS fanout 구독, epoch/seq 검사, reconnect fetch, unsubscribe |
| `frontend/src/features/twin/runtimeStore.js` | 신규 | server state만, asset/metric별 선택 구독 |
| `frontend/src/features/twin/selectionStore.js` | 신규 | 선택 ID·view·hover만 |
| `frontend/src/features/control-tower/uiStore.js` | 신규 | workspace/drawer UI 상태 |
| `frontend/src/hmi/factory/factoryStore.js` | 수정 | legacy compatibility wrapper; 두 runtime owner 금지 |
| `frontend/src/hmi/signalFanout.js` | 유지/최소 수정 | 기존 single socket fanout 재사용 |

Gate: 기존 snapshot 값과 6개 KPI의 raw 값/단위 일치. live 없는 환경은 SIMULATION. 연결 끊김 때 0으로 초기화하지 않음. 기본 palette는 Overview에서 숨기되 engineering 진입 유지.

### Phase 2 — 상태에 연결된 전문 3D·센서·사건

| 경로 | 종류 | 변경/검증 |
|---|---|---|
| `aria/twin/poses.py` | 신규 | DES phase/entered/due/robot FK에서 world pose 계산; RNG/사건 순서 불변 |
| `aria/twin/events.py` | 신규 | 정규화 event ID/seq/correlation·이력·pagination |
| `aria/twin/sensors.py` | 신규 | backend 진입/이탈 trigger·workpiece 연결 |
| `aria/simulation/des/engine.py` | 제한 수정 | event producer hook, sensor trigger 지점, pose snapshot. 생산 로직 변경은 별도 테스트 |
| `server/routers/factory.py` | 수정 | versioned snapshot/event/history API, 기존 endpoint 유지 |
| `frontend/src/features/twin/TwinViewport.jsx` | 신규 | 기존 scene 감싸기, 오류/로딩/선택 |
| `frontend/src/features/twin/assetBindings.js` | 신규 | 임시 공통 binding adapter, Phase5 schema로 연결 |
| `frontend/src/features/twin/AssetInspector.jsx` | 신규 | type별 요약과 advanced disclosure |
| `frontend/src/features/operations/Operations.jsx` | 신규 | 운전 제어·투입/처리/적체 상태 |
| `frontend/src/features/incidents/EventTimeline.jsx` | 신규 | run/seq 정렬, 클릭→asset 선택 |
| `frontend/src/features/incidents/Incidents.jsx` | 신규 | open/recovered/escalated 근거 |
| `frontend/src/hmi/factory/FactoryScene.jsx` | 수정 | backend pose 소비, 보간만, stable asset ID·정적 geometry memoization |
| `frontend/src/hmi/factory/IndustrialEquipment.jsx` | 수정 | 치수/binding 하드코딩 제거, 출처 있는 자산·명시 fallback |
| `frontend/src/hmi/factory/CADBody.jsx`, `RobotArm.jsx` | 보존/최소 수정 | 실제 CAD/URDF 자산, 오류 fallback 라벨, cleanup |
| `frontend/src/hmi/factory/PatrolHumanoids.jsx`, `PatrolPanel.jsx` | 보존/연결 수정 | backend 위치/사건, 가상 상태 표시 |
| `tests/test_twin_events.py`, `tests/test_twin_poses.py`, `tests/test_twin_sensors.py` | 신규 | pause/fault/reset/reconnect, 센서와 이동·검사 상관관계 |

Gate: 정지·고장 때 제품 위치가 서버 상태와 일치. frontend가 pause 후 계속 이동시키지 않음. 센서 enter→inspection start/result→분기 timeline. snapshot 재전송은 중복 사건 생성 금지. 실제 물리 센서/충돌 시뮬레이션으로 표현하지 않음.

### Phase 3 — Quality

| 경로 | 종류 | 변경/검증 |
|---|---|---|
| `frontend/src/features/quality/QualityWorkspace.jsx` | 신규 | workpiece/asset/run·시각 기반 검사 이력 |
| `frontend/src/features/quality/InspectionEvidence.jsx` | 신규 | 이미지·heatmap·score·threshold·source·모델/run |
| `frontend/src/hmi/factory/EvidenceWorkbench.jsx` | 추출/호환 유지 | 기존 실제 evidence viewer 재사용, preview 분리 |
| `aria/simulation/des/inspection.py`, `evidence.py` | 제한 수정 | evidence correlation·보존 정책, 검사 수식 불변 |
| `server/routers/factory.py` | 수정 | 실제 이력 검색, preview scope 명시 |
| `tests/test_factory_quality.py` | 신규 | 결측 SKIPPED/HOLD, model/threshold/evidence 연결, preview가 생산 KPI를 바꾸지 않음 |

Gate: 저장된 같은 이미지·bank·threshold로 기존 score/verdict와 동등성 확인. mocked adapter 시험을 실 CCIFPS 추론 검증으로 세지 않는다. evidence 삭제/만료 시 이유 표시.

### Phase 4 — Ask ARIA·근거·제안·실험

| 경로 | 종류 | 변경/검증 |
|---|---|---|
| `aria/simulation/des/agent.py` | 확장 | OEE/incident/inspection/robot 질문을 read-only 근거 도구에 연결 |
| `aria/simulation/des/service.py` | 제한 수정 | 조회 도구·immutable experiment snapshot, revision 검사·적용 rollback 유지 |
| `aria/mcp/servers/factory_mcp.py` | 확장 | 새 read 도구 allowlist, apply/reject 계속 제외 |
| `server/routers/factory.py` | 수정 | evidence/experiment/proposal 식별자·진행 이벤트·선택 asset context |
| `frontend/src/features/agent/AgentWorkspace.jsx` | 신규 | context-aware Ask ARIA, 관찰/가설/제안 구분 |
| `frontend/src/features/agent/agentStore.js` | 신규 | request별 transcript/progress/trace; runtime 분리 |
| `frontend/src/features/agent/RecommendationCard.jsx` | 신규 | before/after·실험 scope·효과·한계 |
| `frontend/src/features/experiments/Experiments.jsx` | 신규 | baseline/candidate 비교·비용·기준 동일성 |
| `frontend/src/features/engineering/ProposalReview.jsx` | 신규 | 단일 Apply/Reject UI, stale/conflict 표시 |
| `tests/test_factory_agent_evidence.py` | 신규 | 수치 출처, 없는 인과 주장 억제, 승인 우회 차단·stale proposal |

Gate: trace/실험은 실제 결과만 표시. 비교는 동일 model·seed·horizon·inspection mode. 10% 개선 안 되면 미달로 보고, 추가 무제한 탐색 금지. 기존 최대12후보/3600초/15초 sweep 예산 유지. LLM 연결 불가 시 규칙 기반/미지원으로 명확히 표시.

### Phase 5 — canonical 파일과 Engineering 이행

| 경로 | 종류 | 변경/검증 |
|---|---|---|
| `config/factory_twin.json` | 신규 | 승인된 static twin; runtime 상태 금지 |
| `aria/twin/persistence.py` | 신규 | validation/hash/revision·원자적 단일 writer·실패 rollback |
| `aria/twin/compat.py` | 확장 | 기존 outputs/factory/factory.json과 scenario 이행; 백업·roundtrip |
| `aria/simulation/des/service.py` | 수정 | 승인 commit 저장 경로 전환, single owner 유지 |
| `frontend/src/features/engineering/EngineeringWorkspace.jsx` | 신규 | 기존 palette/Properties/transform/connect/save/load 이동 |
| `frontend/src/features/engineering/AssetBindings.jsx` | 신규 | CAD/URDF/GLB 단위·bounds·source·hash binding |
| `frontend/src/hmi/factory/CADPanel.jsx`, `RobotWorkbench.jsx` | 보존/연결 수정 | workbench 접근과 제안 UI 재사용 |
| `tests/test_twin_migration.py` | 신규 | 백업·멱등 이행·원본 보존·쓰기실패 rollback·중복 writer 방지 |

Gate: V1 model→V2→V1 동등성 및 같은 seed 생산 결과 일치. geometry가 불명확하면 unknown/fallback 명시. legacy 파일은 백업으로 남기고 live source로 동시에 읽고 쓰지 않음. UI에서 저장 파일 직접 수정 우회 금지.

### Phase 6 — Fusion 계약만

| 경로 | 종류 | 변경/검증 |
|---|---|---|
| `aria/twin/fusion_contract.py` | 신규 | 같은 ID/revision/run/seq·단위/frame, pose/state 메시지 |
| `integrations/fusion/README.md` | 신규 | Windows 내부 API 실행·queue/custom event·검증 단계 |
| `integrations/fusion/bridge_stub.py` | 신규 | 기본 unavailable, 미연결 시 명시 오류. 성공 ACK 위조 금지 |
| `tests/test_fusion_contract.py` | 신규 | axis/unit·메시지 버전·순서·unknown ID·미연결 상태 |

Gate: 계약 시험 통과는 실제 Fusion 통과와 구분. Windows 큐브·위치·화면 검증은 별도 작업으로 유지한다.

## 2. 시험 계획과 acceptance

기존 회귀 묶음: `tests/test_industrial_des.py`, `test_factory_api.py`, `test_factory_autonomy.py`, `test_patrol.py`, `test_cad.py`, `test_ccifps_contract.py`, `test_inference_contract.py`, `test_factory_line.py`. 각 phase 관련 subset 이후 통합 gate에서 전체 실행. 변경이 없는 동안 성공한 시험을 반복하지 않는다.

프런트 신규: `frontend/tests/control-tower.browser.mjs`에서 시작→이동→센서→검사→분기→고장→질문→실험→proposal→미적용 확인→Apply→reset/revision 증가를 검증. 기존 browser runner/설치 라이브러리를 먼저 재사용한다. 최소 viewport2개, browser console errors/HTTP failures/화면증거를 기록한다.

첨부 22단계의 검증 연결:

| 단계 | 자동 검증 | 시각 검증 |
|---|---|---|
| 1–2 Overview | snapshot과 KPI 일치·source·stale | 3D·6 KPI 보임, 두 해상도 clipping 없음 |
| 3–5 Run·이동·sensor | run_id/part_id/sequence·서버 pose·trigger | 동일 제품 경로·센서 강조 |
| 6–7 검사·분기 | actual 또는 명시 MOCK/SKIPPED, route 일치 | image/score/label 및 출구 |
| 8 자산 선택 | canonical ID 조회 일치 | 오른쪽 inspector·선택 강조 |
| 9–11 fault | 고장→진행 중단·incident 생성·scope | 설비·경고·timeline 일치 |
| 12–13 원인 질문 | 사용 도구·event/evidence reference | 관찰/가설 구분 |
| 14–17 what-if·proposal | 동일 baseline·실측 변화·제안 ID | 추천 카드와 diff |
| 18 미적용 | model hash/revision 불변 | pending 표시 |
| 19–21 Apply | 승인 endpoint·revision+1·새 run, stale 거절 | reset/sync 표시 |
| 22 새 지표 | 승인 model로 계산 | 새 run KPI, 과거 trend 혼합 없음 |

추가 acceptance: 유한 PASS/REJECT buffer full일 때 blocking; SKIPPED 전용 HOLD; 이벤트 유실 cursor gap; 초기 데이터 없음; 모델 미준비; 빠른 반복 클릭/중복 Apply; 시험 중 live revision 변경; 고장 중 pose 고정; 부품 수 보존.

## 3. 완료 기준과 미포함

- 디자인 변경만으로 완료하지 않는다. API·브라우저·실험·승인·데이터 출처를 함께 확인한다.
- 수치·FPS·비교 비용은 조건/실행 ID와 묶어 보고한다.
- 이번 명세는 실PLC/실로봇 제어·충돌/접촉 동역학·새 CCIFPS 튜닝·Fusion 실연동 완료를 포함하지 않는다.
- 넓은 repository 전면 교체나 과거 결과 삭제 없음.
- 이번 응답은 감사/파일별 계획 제시까지다. 코드 단계는 이 계획을 바탕으로 vertical slice로 진행한다.

## 4. 이번 감사에서 수행한 확인

문서·소스 조사 완료. 테스트 결과는 아래 실행 기록을 참조한다. 실제 브라우저·production build·실추론·FreeCAD 재생성·Fusion 실행은 이번 감사에서 수행하지 않았다. 기존 보고서의 통과 숫자로 대체하지 않는다.

### 감사 실행 결과

- DES·patrol·autonomy subset: **34 passed, 1 deselected, 3.98s**.
- factory API 3개 + 앞 subset에서 제외한 URDF HTTP route 1개: **4 passed, 4 warnings, 2.18s** (sandbox 밖에서 실행).
- 겹치지 않는 총 **38개 통과**. 전체 저장소 시험 수가 아니다. FastAPI on_event 사용 중단 예정 경고 4개는 기존 코드에서 발생했다.
- 최초 합동 실행은 진행 정체로 중단. API만 재실행한 sandbox 진단은 45초 timeout(exit124), 15초 stack dump에서 asyncio selector 대기를 확인. 동일 코드·격리된 새 임시 상태를 sandbox 밖에서 실행하면 통과했다. 특정 sandbox 제한을 원인으로 확정하지 않는다.
- 테스트는 기존 코드를 그대로 사용했고 state/pytest 작업 공간은 `/tmp/aria-v2-audit-r7CmnE`로 분리했다. 코드 수정·live 공정 실행·모델 재학습은 없었다.
- 증거: `docs/validation/aria_v2_20261007/core_tests.log`, `api_diagnostic.log`, `api_unrestricted.log`, `tests.log`, `audit_manifest.json`.
- 이번 검증은 factory API/엔진 회귀이다. 실제 CCIFPS 추론, CAD kernel 재생성, 브라우저의 3D 표시·콘솔·네트워크, frontend build 및 Fusion 실행은 **미실행**.
