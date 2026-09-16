# ARIA 자율 순찰 및 문제 보고 에이전트

## 구현
- 휴머노이드 2대(ARIA-01, ARIA-02)가 벽시계 시간 기준으로 상시 순찰한다. 생산 시뮬레이션 일시정지와 순찰 제어는 독립적이다.
- 설비와 컨베이어의 보수적인 평면 점유 영역을 피해 A* 경로를 계산한다. 관절 동작은 이동 상태를 표현한다. 물리 기반 보행, 로봇 간 충돌 회피 또는 실제 하드웨어 진단은 구현 범위에 포함되지 않는다.
- 보고 에이전트는 DES의 DOWN, 정체, 자재 부족 및 실제 inspection_result의 SKIPPED를 근거로 사건을 생성한다. 설비 고장 출동을 우선하고 로봇 도착 시 관측 상태와 확인자를 기록한다.
- 감지와 현장 확인을 구분하며, 상태 해소 시 복구 관측을 기록한다. 재시작/모델 변경은 interrupted 처리하여 수리 완료로 오인하지 않는다.
- 최근 200개 사건을 outputs/factory/patrol_reports.json에 보관하고 Markdown 보고서를 내려받는다. 로컬 규칙 기반 관측/보고이며 LLM 호출이나 자동 수리를 수행하지 않는다.
- Patrol 탭에서 순찰 정지/재개, 보고서 다운로드, 명시적인 60초 가상 설비 고장 시나리오를 실행할 수 있다. 고장 주입은 저장된 설비 MTTR을 변경하지 않는다.
- API: /api/factory/patrol, /patrol/control, /patrol/fault, /patrol/report. MCP와 채팅에서 get_patrol_report 제공.

## 검증
- 전체 Python 테스트 59개 통과: 경로/정지 중 순찰, 고장 감지·중복 방지·현장 확인·복구, 재시작 의미, 검사 누락, 고장 지속시간, HTTP 제어/보고/채팅 계약 포함.
- 프런트엔드 production build 통과. 기존 대형 번들 경고 존재.
- 실제 Chrome/WebGL 브라우저 검증: 설비 고장 시나리오 → ARIA-01 현장 확인 → recovered 전환 확인. 브라우저 예외 및 HTTP 오류 0건.
- 화면 증거: images/industrial_patrol_confirmed.png, images/industrial_patrol_recovered.png.

## GitHub 업데이트 원칙
사용자 요청에 따라 검증된 작업 단위로 커밋하고 푸시한다. 데이터셋, 모델 가중치, 런타임 보고서 및 자격 증명은 커밋하지 않는다. 인증이 없으면 로컬 커밋을 보존하고 원격 반영 여부를 명확히 보고한다. 이 문서는 별도 상주 GitHub 동기화 프로세스를 설치하지 않는다.
