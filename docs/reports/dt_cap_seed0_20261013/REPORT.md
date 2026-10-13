# ARIA 상한 seed0 비용 실측 보고서

상한 270회에 포함되는 9회만 완료했다. 전체 A와 B 사후 계산 완료 보고서가 아니다.

- 실측: 9회 / 166.90초 / 280,316,789 bytes.
- 전체 시간 추정: 6.725시간. 8시간 게이트: True.
- 남은 결과 저장량 추정: 30,235,570,897 bytes.
- 15% + 2 GiB 포함 필요 여유: 36,918,390,180 bytes.
- 현재 여유: 28,911,222,784 bytes. 부족: 8,007,167,396 bytes.
- 저장 게이트: False. 전체 게이트: False.

실패 시 사용자 조건에 따라 여기서 중단한다. 기존 자료를 삭제하거나 실험 조건을 축소하지 않는다.

Baseline: 15 saved A class/cell/speed strata x179; selector/mode cost proxy. Cap: 9 measured class/model strata x29. Posthoc: saved pair costs with conservative x3 for 10s OFAT. Two workers, 25% time reserve; estimates, not measured full completion.

원자료: runs/의 events.jsonl.gz·parts.csv.gz·source_schedule.json·complete.json. 비용 실측: measurements.json. 판단: cost_gate.json.

## MCP 루트 수정과 검증

database·huggingface·shell_exec MCP의 루트를 `Path(__file__).resolve().parents[3]`로 수정했다. DB 읽기 전용 연결·캐시 경로·셸 기본 CWD와 외부 CWD 거부를 검증했다. 전체 백엔드 148 passed, 13 warnings, 11.82초. 상한 원자료 9개 모두 hash·보존식·실행 소스 검증을 통과했다.

## 상한 seed0 측정 내역

|클래스|모델|전체 worker 초|원자료 bytes|
|---|---|---:|---:|
|bottle|coreset|33.934|32974478|
|bottle|ccifps|34.284|32627489|
|bottle|random_same_k|34.052|32441140|
|screw|coreset|33.281|34141609|
|screw|ccifps|33.586|34211087|
|screw|random_same_k|33.801|34253179|
|carpet|coreset|34.079|27225991|
|carpet|ccifps|34.026|26885536|
|carpet|random_same_k|31.176|25556280|

단일 seed 비용 측정이며 모델 성능 순위를 일반화하지 않는다. 남은 A 2,946회·B 사후 4,320건은 실행하지 않았다. 공간 확보 요청에 따라 오래된 파일 후보를 조사 중이며 삭제는 아직 하지 않았다.

## 공간 확보 후 상태

승인된 홈 캐시·구버전 서버 정리로 8,247,353,344 bytes를 확보했다. 필요 여유를 충족하여 본 실행 준비로 전환했다. 최초 실패 판단 원자료는 수정하지 않는다. 재검사 값은 본 실행 폴더의 cost_gate_recheck.json에 별도로 기록한다.
