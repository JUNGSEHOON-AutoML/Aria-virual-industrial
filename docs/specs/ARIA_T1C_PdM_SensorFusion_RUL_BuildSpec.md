# T1-C 빌드 명세 — PdM 센서 융합 & RUL (I-04 / 제4파급) ★데이터 융합 실현

> 한 줄: T1-B는 **비전 NG(후행 지표)** 만으로 셀 패턴을 집계해 신뢰도 0.6에 묶여 있었다.
> T1-C는 방금 세운 **시계열 척추(`record`/`recent`)** 위에서 **진동·온도·지연 추세(선행 지표)** 를 특징화하고,
> 자산별 **건전성 지수(H)** 와 **잔여수명(RUL)** 을 추정한 뒤, **NG 공간 패턴으로 교차 확증**해
> 더 이르고·더 정직한 융합 가설을 낸다. **원인 단정 금지 · RUL은 밴드 있는 추정.**
>
> ⛔ 가드레일: verdict(anomaly score) 로직 불변 · **새 WS 타입 없음**(기존 `diagnostic_result` 확장) · 단일 signalStore ·
> **난수 금지**(실 `metrics_ts` 집계만) · RUL 단정 금지(추정+밴드+확인요망) · 실 조치는 `ApprovalGate` 승인 후 ·
> 물리엔진/실 로봇 제어 제외(Agentic Twin 스펙 가드레일 유지).

---

## 0. 현재 레포 상태 (재사용 / 갭)

| 요소 | 레포 현황 | 상태 |
|---|---|---|
| 시계열 저장/조회 | `timeseries.py` `record()`/`recent()`(다운샘플·재시작 복원) | ✅ **신규 완료** |
| 라인 지표 시계열 | `metrics_ts`(oee·quality·availability·tact·p95·drop·ok/ng/skip) | ✅ 있음 |
| **자산 건전성 시계열** | 설비 건전성 패널은 **순간값**만(온도·진동·p95·drop) — 지속화 안 됨 | ❌ **갭(핵심)** |
| 결함 위치 (u,v)·blob | `inspector_result.defect_xy`/`defect_blob` | ✅ 있음(T1-A) |
| NG 공간 집계 → 가설 | `defect_aggregator.py`(셀 streak → `diagnostic_result` kind=predictive, conf≤0.6) | ✅ 있음(T1-B) |
| 이벤트 버스 | `aria/orchestration/event_bus.py` | ✅ 있음 |
| 승인·에피소드 | `ApprovalGate` · store.episodes · `pdm_episode`용 DB 헬퍼 | ✅ 있음(확장 필요) |
| 가설 리포트 UI | `hmi/panels/RightPanel.jsx` · `PredictiveMaintenance.jsx` · `QCLine.jsx` | ✅ 있음(확장) |
| **추세 특징 추출(RMS/기울기/기준편차)** | 없음 | ❌ **갭** |
| **건전성 지수 · RUL 추정** | 없음 | ❌ **갭** |
| **선행(물리) × 후행(NG) 융합** | 없음 | ❌ **갭** |

→ 빌드 범위 = **자산 건전성 지속화 + 추세 특징 + H/RUL 추정 + NG 교차확증 융합 + 3D/HMI 표출.**
저장/조회·버스·승인·NG 집계는 재사용.

---

## 1. Step 0 — 자산 건전성 신호를 시계열에 지속화 (선행 지표 확보)

`metrics_ts`는 **라인 품질**을 담지만, PdM 선행 지표(온도·진동)는 여기 없다. 같은 `record`/`recent` 인터페이스로 확장.

```
asset_health_ts(ts, lane, asset_id, temp_c, vib_rms_mm_s, infer_p95_ms, drop_rate, current_a?)
```
- `inspector.py` 스냅샷 루프(~2s)에서 라인 지표와 **같은 tick**에 자산 신호도 `record()`.
- 예외를 밖으로 던지지 않음(텔레메트리 실패가 파이프라인 차단 금지 — ②와 동일 원칙).
- `current_a`(로봇 관절 전류)는 있으면 기록, 없으면 null(향후 채널).
- 규모 전환 시 `record`/`recent` 그대로 Timescale/Influx로 교체(②에서 확보한 계약 유지).

---

## 2. 추세 특징 추출 — `health_features` (순수·헤드리스 검증)

윈도우(기본 W=30분, `recent()`로 로드)에서 자산별 **설명 가능한** 특징만 뽑는다(블랙박스 금지).

| 특징 | 정의 | 의미 |
|---|---|---|
| `rms_level` | 윈도우 진동 RMS | 현재 진동 강도 |
| `rms_slope` | 최소제곱 기울기(mm/s per hr) | 진동 **상승 추세**(마모 선행) |
| `temp_slope` | 온도 최소제곱 기울기(°C/hr) | 발열 상승(베어링·모터) |
| `p95_creep` | 추론 p95 이동추세 | 비전 파이프라인 열화 |
| `drop_trend` | drop_rate 추세 | 백프레셔 악화 |

- **기준선(baseline)**: 시프트/SKU 컨텍스트가 있으면 그 스코프의 정상 구간 p50, 없으면 최근 안정 구간 롤링 p50.
- **로버스트 정규화**: `z_i = (feature_i − baseline_i) / MAD_i` (MAD로 이상치 내성).
- 데이터 부족(N<Nmin) 시 특징을 `null`로 반환하고 하류가 **가설 미생성**(정직성).
- 프론트 미러 `hmi/scene/healthFeatures.js`(동일 규칙)로 **Node 헤드리스 검증** 가능.

---

## 3. 건전성 지수 & RUL — `rul_estimator` (투명 모델)

훈련 데이터 없이도 방어 가능한 **투명 열화 모델**. 데이터 기반(Weibull/생존모형)은 run-to-failure가 쌓인 뒤 별도 트랙.

**건전성 지수 H (0..1, 1=정상):**
```
H = clamp( 1 − Σ_i w_i · relu(z_i) / K , 0, 1 )
```
- `relu(z_i)`: 기준선을 **나쁜 방향으로** 벗어난 만큼만 감점(정상 변동 무시).
- `w_i`: 자산별 가중(로봇팔=진동·온도, 컨베이어=drop·진동, 비전=p95·온도).

**RUL 추정:**
- 윈도우의 `H(t)` 추세를 선형(또는 지수감쇠) 적합 → **고장 임계 `H_fail`(기본 0.30)** 도달 시각으로 외삽.
- `RUL = t(H_fail) − now`, **밴드** = 적합 잔차 기반 CI(예: ±1σ).
- **정직성 규칙**: RUL은 항상 `{est, lo, hi, model:'linear|exp'}` 형태 + "확인요망". 점추정 단독 표기 금지.

**신뢰도(confidence):**
```
conf = base(fit_R², N충분성) × (corroborated ? 1.4 : 1.0), 상한 = corroborated ? 0.85 : 0.60
```
- 물리 단독은 T1-B와 같은 0.6 겸손 유지, **NG 교차확증 시에만** 0.85까지 정직하게 상승.

---

## 4. 융합 로직 — `pdm_fusion` (선행 × 후행, ★독립 서비스)

> 이 모듈은 **`recent()`(시계열) + 이벤트 버스만** 읽고 `diagnostic_result`를 publish한다.
> `app.py` 상태에 의존하지 않음 → **평면 분리의 첫 out-of-process 서비스**(§11).

집계 규칙:
1. `rul_estimator`가 자산별 **물리 가설**(H·RUL·물리 신뢰도) 산출(선행).
2. `defect_aggregator`(T1-B)의 셀 가설 → `asset_hint`로 자산 매핑(후행).
3. **동일 자산**이 창(window) 내에서 둘 다 지목 → `corroborated=true`, 신뢰도 상향, RUL은 **물리 모델값**, NG 패턴은 근거로 첨부.
4. 물리 단독(진동/온도 추세만) → **더 이른** 주의 가설(낮은 신뢰도).
5. NG 단독(물리 추세 없음) → T1-B 동작 유지(≤0.6) + note "물리 신호 미확인".
- 쿨다운으로 중복 억제. 모든 가설/승인/결과 → `pdm_episode` 로깅(평가·MLOps·향후 run-to-failure 라벨).

---

## 5. 출력 계약 — `diagnostic_result` 확장 (새 타입 아님)

```json
{ "type":"diagnostic_result", "kind":"predictive",
  "asset":"robot_arm_1", "health_index":0.71,
  "rul":{ "est_hours":42, "lo":28, "hi":63, "model":"linear" },
  "leading_signals":["rms_slope","temp_slope"],
  "corroborated":true, "ng_evidence":{ "cell":"bottle:1,2", "window":"4/5 NG" },
  "confidence":0.78, "note":"확인요망(단정 아님)",
  "recommended_action":"해당 관절 점검·재윤활 / 재교정",
  "ts": 0 }
```
- `signalReducer.js`: `predictions[]`에 `rul`·`health_index`·`corroborated` 누적(최근 N건).

---

## 6. 파일 산출물

### 백엔드 (실 경로 · 시계열/버스/DB/승인 재사용)
| 파일 | 신규/수정 | 내용 |
|---|---|---|
| `aria/core/timeseries.py` | 수정 | `asset_health_ts` 스키마 + `record_health()`/`recent_health()`(기존 패턴). |
| `aria/collectors/inspector.py` | 수정(경량) | 스냅샷 tick에서 자산 신호 `record_health()` feed. |
| `aria/inspection/health_features.py` | **신규(순수)** | 윈도우 특징(RMS·기울기·기준편차). **헤드리스 검증.** |
| `aria/inspection/rul_estimator.py` | **신규** | H 지수 + RUL 외삽 + 밴드 + 신뢰도. |
| `aria/inspection/pdm_fusion.py` | **신규(서비스)** | `recent()`+버스 구독 → 선행×후행 융합 → `diagnostic_result` publish. |
| `aria/core/database.py` | 수정(경량) | `pdm_episode`(asset·H·rul·corroborated·conf·ts) 헬퍼. |

### 프론트 (검증 가능 + Standalone 동일 경로)
| 파일 | 신규/수정 | 내용 |
|---|---|---|
| `hmi/scene/healthFeatures.js` | **신규(순수)** | 백엔드 특징 규칙 미러. **Node 헤드리스 검증.** |
| `hmi/scene/PredictiveMaintenance.jsx` | 수정 | 융합 `diagnostic_result` 수신 → 유지보수 루프/승인/에피소드 연계. |
| `hmi/panels/RightPanel.jsx` | 수정 | "예지보전" 카드에 H 게이지 + **RUL(밴드) + 선행신호 + 확인요망**. |
| `hmi/scene/QCLine.jsx` | 수정 | 의심 자산에 **건전성 링 + RUL 라벨**(NG 셀 펄스 대체·보강). |
| `signalReducer.js` | 수정(경량) | `predictions[]`에 rul·health·corroborated 확장. |

---

## 7. 3D / HMI 표출
- 자산별 **건전성 링**(H로 채움: 녹→황→적)과 `RUL ~42h(28–63)` 라벨.
- `corroborated=true`면 링에 **교차확증 배지**(물리+NG 일치) — 신뢰의 시각적 근거.
- 운영자 모드: "점검 권장 · RUL 밴드 · 확인요망"만. 전문가 모드: 선행신호·H 산식·적합 품질 펼침.

---

## 8. 안전 / 거버넌스 (필수)
- RUL·H는 **항상 추정 + 밴드 + 확인요망**. 점추정·단정 금지(vlmReport 규약 준수).
- 실 조치(재교정/재윤활/재시작)는 **`ApprovalGate` 승인 후에만**(Simulate-then-Approve 재사용).
- 모든 가설/승인/결과 → `pdm_episode` 로깅(평가·향후 데이터 기반 모델 학습 입구).
- **난수 금지**: 오직 실 `metrics_ts`/`asset_health_ts` 집계. verdict 로직 불변.

---

## 9. 검증 게이트 (본인 확인)
1. **특징 라운드트립**: 상승 진동 합성 시계열 → `rms_slope>0` 감지, RUL **단조 감소**.
2. **정직성**: 데이터 부족 시 가설 미생성; RUL 항상 밴드+확인요망 포함.
3. **융합**: 물리 단독 → 이른 주의(conf≤0.6); 물리+NG 동일 자산 → conf 상승(≤0.85)·더 이름.
4. **재시작 복원**: 커넥션 리셋 후 `recent_health()`로 추세·H 재구성(②의 복원과 동일 성질).
5. **결정성**: 동일 입력 시계열 → 동일 RUL(난수 없음).
6. **verdict 불변**: OK/NG 판정 경로 무영향(회귀 없음).

---

## 10. 단계 + 런타임 게이트
- **C0 지속화** — `asset_health_ts` + `record_health` feed. 게이트: 재시작 후 자산 추세 복원.
- **C1 특징** — `health_features` + 헤드리스 테스트. 게이트: 합성 시계열 기울기 검출.
- **C2 RUL** — `rul_estimator` H/RUL/밴드. 게이트: H 하강 시 RUL 감소·밴드 표기.
- **C3 융합** — `pdm_fusion` 선행×후행 → `diagnostic_result`. 게이트: 교차확증 시 conf 상승 로그.
- **C4 HMI** — RightPanel RUL 카드 + QCLine 건전성 링. 게이트: 브라우저에서 RUL·링 표출.

---

## 11. 왜 이걸 먼저 — 평면 분리의 쐐기
`pdm_fusion`은 `app.py` 전역 상태가 아니라 **`recent()` + 이벤트 버스**만 소비/발행하도록 설계한다.
따라서 이 서비스는 **별도 프로세스로 기동 가능한 첫 모듈**이 되고, 이후 3-split(검사 노드 / 트윈 상태 서비스 / UI 게이트웨이)은
"이미 하나를 out-of-process로 떼봤다"에서 출발한다. 즉 T1-C는 지능을 더하는 동시에 **모놀리스를 더 깊게 하지 않고 분리를 앞당긴다.**
또한 여기서 만든 추세-특징 계층(`health_features`)은 다음 트랙인 **24h 모델 라이프사이클의 드리프트 감시**가 그대로 재사용한다.

---

## 12. Claude Code 미션 브리프 (그대로 전달)
```
목표: 기존 ARIA 시계열(record/recent)·이벤트 버스·NG 집계(T1-B)·승인 게이트를 재사용하여
      자산 건전성 지속화 → 추세 특징 → H지수·RUL(밴드) → NG 교차확증 융합 → diagnostic_result 발행 → RUL/건전성 3D 표출.
불변: verdict 로직 · 새 WS 타입 없음(diagnostic_result 확장) · 단일 signalStore · 난수 금지 · RUL 단정 금지 · 실조치는 승인 후.
설계: pdm_fusion은 recent()+버스만 읽는 독립 서비스(app.py 상태 비의존) — 평면 분리의 쐐기.
검증: §9 게이트 6종 + health_features/healthFeatures 헤드리스 라운드트립 + 재시작 복원.
```
