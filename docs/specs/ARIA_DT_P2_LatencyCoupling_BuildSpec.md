# ARIA DT P2 — 검사 지연 결합

## 입력과 범위
2026-10-12, 첨부 ARIA_DT_BuildSpec(2026-10-11)의 P0와 독립 가능한 P2. 원본 PDF는 사용자 첨부이며 저장소 정책 파일이 아니다. 기존 production refactor를 포함한 working tree를 baseline/source.tar.gz에 보존했다.
먼저 읽은 파일: `aria/simulation/des/{model,engine,inspection,robot,service}.py`, `tests/{test_industrial_des,golden_trace}.py`, `tools/benchmark_factory.py`.

## 계약
- 기본 `latency_mode=constant`, `latency_profile=''`: 기존 processing_time과 로봇 동작, 판정 RNG 및 공정 결과 유지.
- constant 필드 추가 후 수정 전 DES의 3seed × inline/robot 6개 trace에서 events/metrics/parts canonical JSON bytes 동일성을 먼저 확인한다. 모델 계약에 추가된 설정 키와 비결정적 run_token은 실행 trace 비교 대상이 아니다.
- profile: `config/latency_profiles/` 내부 JSON을 SHA-256으로 고정하고 Engine 생성 시 검증·메모리에 고정. 임의 경로와 심볼릭 링크 탈출을 거부한다. reset은 동일 bytes와 seed를 재사용한다.
- profile RNG는 seed + component ID 기반 별도 stream. failure/mock RNG를 소비하지 않는다.
- total_ms 표본을 초로 바꾸고 handling_time_s를 더한다. 로봇은 기존 program의 INSPECT 시간만 대체한다.
- 각 stage 표본은 같은 sample index로 읽는다. 총 지연을 stage 합으로 재구성하거나 wall clock 차이로 대체하지 않는다.
- optional inspection_deadline_s는 검사 셀 입장(sensor trigger로 간주)부터의 기한. 시간 경과·setup·고장 대기도 포함. P4에서 d/v-act로 계산할 필드.
- 기한 초과 결정을 한 번 고정하고 이후 늦은 결과는 재분기하지 않는다. 내부 legacy verdict SKIPPED + route HOLD를 사용한다. HOLD를 OK/NG로 세지 않는다.
- 모델은 blocking-after-service이므로 timeout 결정 후에도 검사 resource는 잔여 서비스 종료까지 점유하며 HOLD 이동은 서비스 완료 후다. 연속 벨트/비동기 worker 물리 모델이라고 주장하지 않는다.
- GT 입력 없음. 원본 CCIFPS·bank·과거 결과·persisted factory 설정 변경 없음.

## 게이트와 범위 제한
- P0의 전체 pytest, 기존 30seed × 4조건 benchmark, 기존 비전 golden verify.
- 기본 DES 동작 동일성 통과 후 profile 구현.
- seed 재현, 기한 경계/초과/고장/늦은 완료, robot 7 ACK, 잘못된 파일/hash, conservation/backpressure 검사.
- synthetic_test 프로파일은 기능 검증 전용으로 실측 또는 CCIFPS 성능으로 표시하지 않는다.
- P1의 논문 AP 허용오차·bank 원실험 출처는 미확정. P3–P6 및 실제 모델 매트릭스는 그 게이트를 통과한 것으로 간주하지 않는다.
- 이전 DB integration 환경 미존재로 skip된 검사는 별도 명시; P0 전체 gate는 조건부 상태.

## 산출물
`docs/validation/aria_dt_20261012_01/`에 기준선, 회귀 JSON/로그, profile 동작 원자료, REPORT를 보존. 실측 bank profiler/30seed 모델비교/HMI 완료를 이 P2 검증으로 대신하지 않는다.
