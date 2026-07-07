# T3-A · §0 감사 범위 — 24h 라이프사이클 착수 전 실측 체크리스트

> 목적: `context.py`·`health_features`·`timeseries`의 **실제 배선 상태**를 코드에서 확인하고,
> 드리프트 감시·롤링 FAT의 재사용 가능 범위와 갭을 실측한다. 가정 금지.

---

## 1. context.py 배선 실측

확인 항목:
- `ProductionContext` 필드 목록 — `sku`, `shift`, `tau_by_category`, `takt`, `recipe` 실제 존재 여부
- **실제로 읽히는 곳** grep: `from aria.core.context import` / `get_context()` / `ProductionContext(`
- 시프트 전환 트리거가 있는지(스케줄러·API·수동) — 없으면 갭
- τ 스코프가 실제 추론 경로에 연결됐는지: `config.tau(category)` 호출이 context를 보는지, 독립인지
- `shift` 필드가 시계열 레코드에 태깅되는지(드리프트를 시프트별로 볼 전제)

갭 예상:
- context가 싱글톤으로 존재하나 **아무도 안 읽을** 가능성(S1에서 만들었지만 배선 미완)
- 시프트 전환 API/스케줄러 없음 → 라이프사이클의 "시프트별 기준선" 전제 붕괴 가능

---

## 2. health_features 재사용 가능성 실측

확인 항목:
- `health_features.py` 출력 스키마: `rms_slope`·`temp_slope`·`p95_creep`·`drop_trend`·`rms_level` 실제 필드
- **입력 소스**: `recent_health()`의 실제 컬럼 목록 — `temp_c`·`vib_rms_mm_s`·`infer_p95_ms`·`drop_rate` 존재 여부
- `sim=1` 태깅된 컬럼(결정론 proxy)이 드리프트 감시에서 **구분 처리** 가능한지
- Python↔JS 미러(`healthFeatures.js`) 드리프트 감시에서도 재사용 가능한 형태인지
- 윈도우 파라미터(W=30분 기본)가 외부화됐는지(config에 있는지)

갭 예상:
- `vib_rms_mm_s`·`temp_c`가 `asset_proxy.py`의 결정론 값 → 드리프트가 **결정론 신호 위에서 돌면** 드리프트가 감지 안 됨(항상 고정)
- `rms_slope`·`temp_slope`가 사실상 0에 수렴 가능 → 드리프트 감지 로직이 p95·drop에 집중해야 할 수도

---

## 3. 시계열 컬럼 실측 (드리프트 감시 입력)

확인 항목:
- `metrics_ts` 실제 컬럼: `oee`·`quality`·`availability`·`tact`·`p95`·`drop`·`ok`·`ng`·`skip`
- `asset_health_ts` 실제 컬럼: + `sim` 컬럼 존재 여부
- `recent()`·`recent_health()`의 `max_points` 다운샘플 — 드리프트 윈도우(예: 8h)에서 충분한 해상도인지
- 시프트 태그(`shift`)가 시계열에 있는지 — 없으면 시프트별 기준선 분리 불가

---

## 4. 롤링 FAT 전제 확인

확인 항목:
- 현재 FAT 게이트(`/api/fat` 또는 유사)가 실제로 존재하는지
- escape/FP 계산에 쓸 **정답 라벨** 소스: `analysis_history`의 `verdict`·`ground_truth` 컬럼 실재 여부
- 롤링 FAT가 "최근 N시간" 슬라이딩인지, 아니면 일회성 배치인지
- `pdm_episode` 테이블: `corroborated`·`conf`·`ts` 실재 여부(롤링 FAT의 PdM 측 입력)

갭 예상:
- `ground_truth` 컬럼 없음 → 롤링 FAT는 **escape(NG인데 OK 판정)**만 사후 집계 가능, FP는 오퍼레이터 확인 피드백 없이는 불가
- 그렇다면 롤링 FAT의 1차 구현은 "escape율 추세"로 scoping 필요

---

## 5. 드리프트 감시 설계 전제 확인

확인 항목:
- 기준선(baseline) 저장소: 시프트별 p50이 어디에 저장될지(현재 없음 → 신규)
- 점수 분포 샘플: PatchCore anomaly score가 시계열에 기록되는지(`metrics_ts.p95`가 추론 지연인지 점수인지)
- 카메라 온도(`비전카메라 경고` 스크린샷에서 53°C)가 수집되는지 — 광학 드리프트 선행 지표
- `signalStore`에 드리프트 알람을 위한 슬롯이 있는지

---

## 6. 감사 산출물 — `docs/t3a_lifecycle_audit.md`

형식:
```
## context.py
- 실재: [필드 목록]
- 배선: [읽히는 곳 / 없음]
- 갭: [목록]

## health_features
- 입력 컬럼: [실재 / 미재]
- sim 컬럼: [있음 / 없음]
- 재사용 가능: [예 / 조건부(이유) / 아니오]

## metrics_ts / asset_health_ts
- 컬럼: [실재 목록]
- 시프트 태그: [있음 / 없음]
- 드리프트 입력 충분성: [예 / 조건부]

## 롤링 FAT
- ground_truth: [있음 / 없음]
- 1차 scope: [escape율 추세 / FP 포함]

## 드리프트 감시
- 기준선 저장소: [있음 / 없음(신규)]
- anomaly score 수집: [있음 / 없음]

## 결론: 재사용 / 신규 / 갭 분류
```

---

## Claude Code 미션 브리프 (S3b-4 완료 직후 §0으로)
```
목표: T3-A 24h 라이프사이클 착수 전 §0 감사.
범위: context.py 배선·health_features 재사용성·metrics_ts/asset_health_ts 컬럼·롤링 FAT 전제·드리프트 감시 전제.
방법: grep + 파일 읽기만. 코드 수정 없음.
산출: docs/t3a_lifecycle_audit.md (위 형식).
원칙: 가정 금지. 없으면 "없음(갭)"으로 기록.
```
