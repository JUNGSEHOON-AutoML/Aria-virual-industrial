# T1-B 빌드 명세 — SLM식 예지보전 (I-03 / 제3파급) ★데이터 융합

> "동일 위치 N회 연속 NG → 해당 셀/로봇 관절 마모 의심" — `inspector_result`를 **시간·위치로 집계**해
> 에이전트가 **가설 진단**(신뢰도 + 확인 요망)을 내고, **승인 게이트** 경유로만 조치한다.
> 이게 "검사기 → 공장의 두뇌" 격상의 핵심. **원인 단정 금지(가설만).**
> ⛔ verdict 로직 불변 · 새 ws 타입 없음(기존 `diagnostic_result` 재사용) · 단일 signalStore · 난수 금지(실 데이터 집계).

---

## 0. 현재 레포 상태 (재사용 / 갭)
| 요소 | 레포 현황 | 상태 |
|---|---|---|
| 결함 위치 (u,v)·blob | `inspector_result.defect_xy`/`defect_blob` (T1-A에서 확보) | ✅ 있음 |
| 이벤트 버스 | `aria/orchestration/event_bus.py` (`EventBus.subscribe/publish/publish_sync`) | ✅ 있음 |
| 영속 DB | `aria/core/database.py` (sqlite, `analysis_history`/`agent_memory`) | ✅ 있음 |
| VLM 가설 진단 | `aria/agents/vision_agent.py` `inspect_via_registry`(score/confidence) | ✅ 있음 |
| 진단 메시지 타입 | `signalReducer` `case 'diagnostic_result'` → messages | ✅ 있음(재사용) |
| 클라 가설 리포트 | `hmi/scene/vlmReport.js`(가설+신뢰도+확인요망) | ✅ 있음 |
| 유지보수 루프·승인·에피소드 | `MaintenanceController`·`ApprovalGate`·store.episodes | ✅ 있음 |
| **결함 패턴 집계(시간·위치)** | 없음 — 결과가 집계 없이 흘러감 | ❌ **갭(핵심)** |
| **연속 NG→가설 진단 생성** | 없음 | ❌ **갭** |
| **의심 셀 3D 강조** | 없음 | ❌ **갭** |

→ 빌드 범위 = **집계 엔진 + 가설 생성 + 3D 강조 + 승인 연계.** 추론/버스/DB/VLM/승인은 재사용.

---

## 1. 정의 — "동일 위치", "패턴"
- **셀(cell)** = (클래스, u-v 격자칸). `defect_xy`(0..1)를 `GRID×GRID`(기본 4×4)로 양자화 → `cellId = class:r,c`.
  - 의미: 부품 같은 위치에 반복 결함 = 계통적 원인(치구 마모·이송 정렬·로봇 관절 편차) 의심.
- **연속 NG**: 같은 cell에서 NG가 **N회 연속**(기본 N=3) 또는 **윈도우 M건 중 K회**(기본 5건 중 4회).
- **트리거 시** 가설 진단 1건 생성(쿨다운으로 중복 억제).

## 2. 산출물 (파일 단위)
### 백엔드(실 경로, event_bus/DB/VLM 재사용)
| 파일 | 신규/수정 | 내용 |
|---|---|---|
| `aria/inspection/defect_aggregator.py` | **신규** | 결과 stream 구독→cell 집계→임계 도달 시 `diagnostic_result`(가설) **publish** + DB 기록. |
| `aria/inspection/async_pipeline.py` 또는 `server/routers/inspector.py` `_ws` | 수정(경량) | emit 경로에서 aggregator에 결과 1건 feed(`aggregator.observe(res)`). |
| `aria/core/database.py` | 수정(경량) | `defect_episode` 기록 헬퍼(cellId, count, hypothesis, confidence, ts). |

`diagnostic_result` 페이로드(기존 타입 확장, **새 타입 아님**):
```json
{ "type":"diagnostic_result", "kind":"predictive",
  "cell":"bottle:1,2", "count":3, "window":"3/3 NG",
  "hypothesis":"해당 셀 치구/로봇 관절 마모 의심", "confidence":0.45,
  "note":"확인 요망(단정 아님)", "recommended_action":"해당 셀 점검·재교정",
  "asset_hint":"robot_arm", "ts":... }
```

### 프론트(검증 가능 + Standalone 동일 경로)
| 파일 | 신규/수정 | 내용 |
|---|---|---|
| `hmi/scene/defectPatternEngine.js` | **신규(순수)** | 실 scan stream을 cell 집계→연속 NG 감지→가설 객체. **Node 헤드리스 검증 가능.** |
| `hmi/scene/PredictiveMaintenance.jsx` | **신규(컨트롤러)** | `diagnostic_result` 수신(실 경로) **또는** 클라 집계(폴백)로 가설 도출→유지보수 루프/승인/에피소드 연계. |
| `hmi/scene/QCLine.jsx` | 수정 | 의심 cell/asset 3D 강조(경고 마커·펄스). |
| `hmi/panels/RightPanel.jsx`(또는 PiP) | 수정 | "예지보전" 가설 카드(cell·count·신뢰도·확인요망·권장조치). |
| `signalReducer.js` | 수정(경량) | `diagnostic_result.kind==='predictive'` → `predictions[]` 상태 누적(최근 N건). |

> 클라 집계는 **실 inspector_result만** 사용(난수/위조 없음). 백엔드 aggregator가 가동되면 그 `diagnostic_result`를 우선 사용, 없으면 클라 폴백(동일 규칙).

---

## 3. 집계 규칙 (defectPatternEngine — 정형)
```
observe(scan):                       // 실 inspector_result 1건
  if !scan.defect_xy: return
  cell = cellId(scan.class, quantize(scan.defect_xy, GRID))
  rec = cells[cell] ?? {streak:0, window:[], total:0}
  isNG = scan.verdict === 'NG'        // verdict 로직 불변(낮을수록 정상은 이미 verdict에 반영)
  rec.streak = isNG ? rec.streak+1 : 0
  rec.window = [...rec.window, isNG].slice(-WINDOW)
  if rec.streak >= N || count(rec.window,true) >= K:
     → emit hypothesis(cell, rec)  (쿨다운 적용)
```
- 가설 신뢰도 = 패턴 강도 함수(streak/N, window 적중률) — 상한 ~0.6, **단정 아님**.
- asset_hint 매핑: cell 행/위치 → robot_arm/vision_camera/conveyor_motor(휴리스틱, 가설).

## 4. 안전/거버넌스 (필수)
- 가설은 **항상 "추정 + 신뢰도 + 확인 요망"** (vlmReport 규약 준수). 원인 단정 금지.
- 실 조치(재교정/재시작)는 **`ApprovalGate` 승인 후에만** — 기존 Simulate-then-Approve 재사용.
- 모든 가설/승인/결과 → `episode`(클라) + `defect_episode`(DB) 로깅(평가·MLOps).

## 5. 3D 시각화
- 의심 cell이 속한 설비(asset_hint)에 **경고 펄스 + "예지: 마모 의심(0.45)" Html 라벨**.
- 부품 표면의 해당 cell 위치(역투영, T1-A `coordinateTransform` 재사용)에 누적 결함 히트 표시(옵션).

## 6. 데이터 바인딩 (실제만)
| 표출 | 소스 |
|---|---|
| 가설/cell/count/신뢰도 | `diagnostic_result`(백엔드 aggregator) 또는 클라 `defectPatternEngine`(실 scan 집계) |
| 의심 위치 3D | cell→(u,v)→`coordinateTransform`(T1-A) |
| 조치 | `ApprovalGate`→`/api/inspector|action`(승인 후) |
| 로깅 | store.episodes(클라) + `core/database`(서버) |
> 새 ws **타입** 없음(`diagnostic_result` 재사용). 새 엔드포인트/추론서버 없음.

## 7. 수용 기준 (런타임)
1. **데이터 유도**: 가설은 실 `inspector_result` 집계에서만 발생(난수면 발생 안 함 — 테스트로 고정).
2. 동일 cell 연속 NG가 임계(N/K) 도달 시 가설 1건(쿨다운 내 중복 없음).
3. 가설은 **가설+신뢰도+확인 요망**(단정 아님). 실 조치는 **승인 후에만**.
4. Live=백엔드 aggregator `diagnostic_result`, Standalone=클라 동일 규칙(폴백, 라벨).
5. anomaly score<τ=OK 불변. 단일 signalStore 유지.
- 시각 게이트는 본인 브라우저 확인(빌드 아님). 집계 규칙은 헤드리스 검증.

---

## 8. Claude Code 미션 브리프 (그대로 전달)
```
목표: inspector_result를 시간·위치로 집계해 "동일 위치 N회 연속 NG→마모 의심" 가설 진단을 내고,
      승인 게이트로만 조치. 재사용: event_bus·core/database·vision_agent·diagnostic_result·MaintenanceController·ApprovalGate.
★난수 금지: 가설은 실 inspector_result 집계에서만. ★원인 단정 금지: 항상 가설+신뢰도+확인 요망. verdict 불변.

[1] defectPatternEngine.js(순수): observe(scan)→cell=(class, quantize(defect_xy,GRID))→streak/window 집계→
    streak>=N(기본3) 또는 window K/M 도달 시 hypothesis{cell,count,confidence(<=0.6),asset_hint,recommended_action}. 헤드리스 검증.
[2] (백엔드) defect_aggregator.py: 결과 stream 구독(emit 경로 feed)→[1]과 동일 규칙→diagnostic_result(kind:'predictive') publish
    + core/database 기록. 새 ws 타입 금지(diagnostic_result 재사용).
[3] PredictiveMaintenance.jsx: diagnostic_result(predictive) 수신(실) 또는 클라 [1] 폴백→
    의심 asset로 MaintenanceController 시연→ApprovalGate 승인 게이트→episode/DB 로깅.
[4] signalReducer: diagnostic_result.kind==='predictive'→predictions[] 누적. RightPanel/PiP에 예지 가설 카드.
[5] 3D: 의심 cell/asset 경고 펄스+Html 라벨. cell→(u,v)→coordinateTransform(T1-A) 재사용.
[바인딩] inspector_result/diagnostic_result만(단일 store). 새 엔드포인트/추론서버 금지. 승인 없는 실 액션 금지.
[DONE] 동일 cell 연속 NG→가설1건(쿨다운) · 가설표기(신뢰도/확인요망) · 승인 후만 조치 · Live/Standalone 동일 규칙 · 로깅. 브라우저+헤드리스.
```

## 9. DO / DON'T
- ✅ 실 결과 시간·위치 집계 · 가설+신뢰도 진단 · 승인 게이트 · event_bus/DB/VLM/T1-A 재사용 · 3D 의심 강조.
- ⛔ 난수 가설 · 원인 단정 · 새 ws 타입/엔드포인트/추론서버 · verdict 변경 · 승인 없는 실 액션 · C#/HALCON 전환.
