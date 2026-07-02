# T3-A §0 감사 산출물 — 24h 라이프사이클 착수 전 실측

> 감사일: 2026-07-02  
> 방법: grep + 파일 읽기만. 코드 수정 없음. 가정 없음.

---

## 1. context.py

**실재 필드**: `sku`, `shift`, `tau_by_category`, `takt_s`, `recipe` — 모두 실재 (`aria/core/context.py`)  
**`tau()` 메서드**: 카테고리+시프트 스코프 τ 계산. shift_factor(day=1.0, night=0.95, weekend=1.05) 포함.  
**싱글톤**: `_current = ProductionContext.from_env()` — 모듈 임포트 시 env에서 읽음.

**배선 실측**:
```
grep "from aria.core.context import" → 0건
grep "get_context()"                → 0건 (server/, aria/inspection/ 기준)
```
- `aria/learning/self_improvement_loop.py:789` `_get_context()` — **별개 함수**, ProductionContext 무관
- `aria/orchestration/harness_loop.py:88` `_get_context()` — **별개 함수**, ProductionContext 무관
- `context.tau(category)` 호출: **0건** — 추론 경로(`async_pipeline.py`, `inspector.py`)가 config.inference.tau_default를 직접 읽음. context 경유 안 함.

**시프트 전환**: API 없음, 스케줄러 없음. env 재읽기(`reload()`) 정의됐으나 호출부 없음.

**시프트 태그 → 시계열**: `metrics_ts`·`asset_health_ts` 모두 shift 컬럼 없음.

**갭**:
- context.py는 싱글톤으로 존재하나 **아무도 읽지 않음** (배선 미완)
- τ 스코프가 추론 경로에 연결 안 됨 → 시프트별 τ 조정 미동작
- 시프트 전환 트리거 없음
- 시계열에 shift 태그 없음 → "시프트별 기준선 분리" 전제 없음

---

## 2. health_features

**입력 컬럼** (`recent_health()` → `asset_health_ts`):

| 컬럼 | 실재 | sim=1 여부 |
|------|------|-----------|
| `temp_c` | ✓ | 항상 1 (`asset_proxy.py` 유일 소스) |
| `vib_rms_mm_s` | ✓ | 항상 1 |
| `infer_p95_ms` | ✓ | 0 (실측: 추론 실지연) |
| `drop_rate` | ✓ | 0 (실측: 백프레셔 계산) |
| `current_a` | ✓ | None (inspector.py:40 `current_a=None`) |
| `sim` | ✓ | — |

**출력 스키마**: `rms_level`, `rms_slope`, `temp_slope`, `p95_creep`, `drop_trend`, `z{}`, `baseline{}` — 실재

**sim=1 처리 실측**:
- `rul_estimator.py:133`: `any_sim = any(int(r.get("sim",0))==1 ...)` → `rul.sim=True` 반환 (구분 있음)
- `health_features.extract()`: sim 컬럼 **미참조** — sim=1 행을 정상 행과 동일하게 처리

**결정론 proxy가 드리프트 감시에 미치는 영향**:
```python
# asset_proxy.py:
temp_c = temp0 + kp95 * p95 + thermal * (1 - exp(-elapsed/600))
vib    = vib0  + kdrop * drop + wear_per_hr * (elapsed / 3600)
```
- p95·drop·elapsed가 고정이면 temp_c·vib는 수학적으로 결정됨
- `rms_slope`·`temp_slope`는 항상 0이 아님 — 하지만 이 증가는 실측 마모가 아닌 **수식이 만든 것**
- 실제 모터가 과열돼도 `temp_c`는 proxy 수식 결과만 반영 → 드리프트 감지 불가
- `z["rms_level"]`·`z["temp_c"]`가 "drift"를 보여도 그건 elapsed 경과의 수학적 반영

**재사용 가능성**:
- `p95_creep`, `drop_trend`: **재사용 가능** — infer_p95_ms·drop_rate는 실측값
- `rms_slope`, `temp_slope`, `z["rms_level"]`, `z["temp_c"]`: **조건부 보류** — sim=1 필터 후 사용 (현재 필터 없음); HIL/실센서 연결 전까지 드리프트 입력으로 부적합
- 윈도우 파라미터 W: `recent_health(minutes=60)` 하드코딩 → 외부화 갭

---

## 3. metrics_ts / asset_health_ts

**metrics_ts 실재 컬럼**:
`ts, lane, category, oee, quality, availability, tact(=tact_time_ms), infer_p95(=infer_latency_p95_ms), drop_count, n_ok, n_ng, n_skipped`

- **anomaly score**: 없음. `infer_p95`는 추론 지연(ms)이지 PatchCore anomaly score가 아님.  
  Score는 WS `inspector_result` 메시지에만 있고, DB에 저장 안 됨.
- **shift 태그**: 없음
- **category 태그**: 있음 (`category TEXT`) — SKU 대체 가능성 있음

**asset_health_ts 실재 컬럼**:
`ts, lane, asset_id, temp_c, vib_rms_mm_s, infer_p95_ms, drop_rate, current_a(=None), sim`

- `sim` 컬럼 있음 — sim=1 필터링 가능하나 health_features에서 미사용

**해상도**:
- `recent()`: `max_points=200` 다운샘플. 8h 창에서 200포인트 = 2.4분/포인트 → 단기 스파이크 손실 가능
- `recent_health()`: `max_points=300`. 동일 문제.

**시프트 태그**: 없음 → 시프트별 기준선 분리 불가 (신규 설계 필요)

---

## 4. 롤링 FAT

**FAT 엔드포인트**:
- `app.py:1226` `escape_rate`, `fat_verdict` 존재 — 레거시. `server/` 라우터로 미이식.
- `server/routers/classes.py:83` `escape_rate`, `fat_verdict` 있음 — `class_result` WS에 실어 보냄.

**정답 라벨 소스**:
- `analysis_history` 테이블 컬럼: `id, timestamp, image_path, domain_type, score, defect_probability, heatmap_url`
- **`verdict` 컬럼 없음**, **`ground_truth` 컬럼 없음**
- `pdm_episode` 컬럼: `ts, asset_id, health_index, rul_est, corroborated, confidence, leading, note` — 실재
- YOLO `ground_truth`: MVTec 오프라인 데이터셋 마스크(`yolo_dataset_builder.py`) — 온라인 런타임 수집 아님

**escape_rate 계산 소스**: `server/routers/classes.py`에서 class_result로 전달되지만 `ground_truth` 없이 score > τ 기반 추산. 오퍼레이터 확인 없음.

**롤링 FAT 가능 범위**:

| 항목 | 가능 여부 | 소스 |
|------|----------|------|
| escape율 추세 (NG 누락) | 가능 | n_ng / (n_ok+n_ng) 시계열 |
| FP율 (OK 오판) | 불가 | ground_truth 없음 |
| PdM 가설 적중률 | 조건부 | `pdm_episode.corroborated` 있음 |

**1차 scope 결정**: escape율 추세 (`n_ng` 시계열 슬라이딩). FP는 오퍼레이터 피드백 루프 구현 후 defer.

---

## 5. 드리프트 감시

**기준선 저장소**: 없음 — 신규 설계 필요. 제안: `drift_baseline` 테이블 또는 json 파일 (시프트×자산별 p50).

**anomaly score 수집**: 없음. PatchCore score는 WS에만 존재, DB 미저장. 드리프트 감시를 score 분포로 하려면 `metrics_ts`에 score 컬럼 추가 필요.

**실제 변하는 신호 (드리프트 감시 1차 타깃)**:

| 신호 | 실재 | sim 여부 | 드리프트 감시 적합 |
|------|------|---------|----------------|
| `infer_p95_ms` | ✓ | 실측 | ✓ 1차 타깃 |
| `drop_rate` | ✓ | 실측 | ✓ 1차 타깃 |
| `n_ng / (n_ok+n_ng)` escape율 | ✓ | 실측 | ✓ 1차 타깃 |
| `vib_rms_mm_s` | ✓ | sim=1 | ✗ HIL 후 |
| `temp_c` | ✓ | sim=1 | ✗ HIL 후 |

**signalStore 드리프트 슬롯**: 없음. `lines: {}` 에 `escape_rate`·`fat_verdict` 있음. `drift` 전용 슬롯 신규 필요.

**카메라 53°C 수집**: `asset_health_ts.temp_c`에 기록되나 sim=1 (vision_camera 프록시). 실 광학 온도 채널 없음.

---

## 결론: 재사용 / 신규 / 갭 분류

### 재사용 가능 (코드 수정 없이)
- `health_features.extract()` — p95_creep·drop_trend 두 특징
- `pdm_episode.corroborated` — PdM 적중률 롤링 FAT
- `metrics_ts` n_ok·n_ng — escape율 추세 계산
- `signalStore.lines.escape_rate` — 프론트 escape 표출

### 조건부 재사용 (소규모 추가 후)
- `health_features.extract()` — sim=0 필터 인자 추가 시 rms/temp 특징도 사용 가능
- `recent_health()` — `sim=0` 필터 파라미터 추가 (1줄)
- `metrics_ts` — anomaly score 컬럼 추가 시 score 분포 드리프트 가능

### 신규 필요
- `drift_baseline` 저장소 — 시프트×자산별 p50 저장
- `metrics_ts.score` 컬럼 — anomaly score 수집 (드리프트 감시 핵심 입력)
- `metrics_ts.shift` 컬럼 (또는 조인 테이블) — 시프트별 기준선 분리
- context.py 배선 — `inspector.py`가 `get_context().tau(category)` 호출하도록
- 시프트 전환 API — `/api/context/shift` (ARIA_SHIFT env → 런타임 전환)

### 명시적 defer (HIL/실센서 연결 후)
- `temp_c`·`vib_rms_mm_s` 드리프트 감시 — sim=1 해제(실센서 연결) 후 활성화
- FP율 롤링 FAT — 오퍼레이터 피드백 루프 구현 후
- 시프트별 τ 스코프 — context.py 배선 완료 후

---

## T3-A 1차 구현 권장 범위

```
드리프트 감시:
  대상 신호: infer_p95_ms, drop_rate, escape율 (n_ng/n_total)
  기준선: 첫 시프트 창의 p50 → drift_baseline 저장
  알람: 현재 창 p50 vs 기준선 p50 z > 2.5σ
  defer: temp_c·vib (sim=1), score 분포 (score 컬럼 없음)

롤링 FAT:
  1차: escape율 추세 (최근 1h 슬라이딩, metrics_ts.n_ng 기반)
  defer: FP율 (ground_truth 없음)

context.py:
  최소 배선: inspector.py가 get_context().shift를 record snap에 포함
  → metrics_ts.category 필드로 대체 가능 (shift 컬럼 신규 전에)
```
