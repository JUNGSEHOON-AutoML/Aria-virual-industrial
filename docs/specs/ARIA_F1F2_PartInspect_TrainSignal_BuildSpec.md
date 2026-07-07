# F1·F2 빌드 명세 — 분류함 부품 결함 3D 조회 + 클래스 학습 완료 신호

> 두 갭을 레포 파일 기준으로 메운다. ⛔ verdict 로직 불변 · 난수 금지 · 단일 signalStore · 스택 유지.

---

## F1. 분류함(OK/NG bin) 부품 클릭 → 그 부품의 결함 3D 조회

### 문제 / 현황
- `flowEngine.spawnFromResult`는 부품에 **`{id, partId, verdict}`만 저장** → 클릭해도 *그 부품*의 결함(이미지/heatmap/종류)을 못 보여줌.
- 현재 클릭 가능한 건 부스 아래 **고정 시편**(최신 scan만). 흘러가 쌓인 개별 부품은 색만 다른 큐브.

### 목표
레인/분류함에 쌓인 **개별 부품을 클릭 → 그 부품의 실제 MVTec AD 결함**(2D 원본·heatmap·결함종류·decal/relief)을 PiP+3D로 표시.

### 산출물 (파일)
| 파일 | 수정 | 내용 |
|---|---|---|
| `frontend/src/hmi/scene/flowEngine.js` | 수정 | 부품에 **검사 레코드 전체** 보관: `record = {part_id, verdict, score, tau, defect_class, defect_xy, defect_blob, image_b64, heatmap_b64}`. 메모리 가드(레코드 보유 부품은 active+done ≤ ~30개, 오래된 것 prune; image/heatmap는 **NG 우선** 보관 옵션). |
| `frontend/src/hmi/scene/QCLine.jsx` | 수정 | 흐름 부품 mesh에 `onClick` → 그 부품 `record`를 `onOpenPiP(record)`로 전달(+선택 하이라이트 링). done/lane 부품 우선 클릭. |
| `frontend/src/hmi/panels/ViewportSlot.jsx` | 수정 | `onOpenPiP(record)` → `pipData=record` (이미 override 지원). |
| `frontend/src/hmi/panels/VisionPiP.jsx` | (그대로) | `data` override로 그 부품 이미지/heatmap/score/verdict/defect_class 표시 — **이미 지원**. |
| `frontend/src/hmi/scene/InspectionSpecimen.jsx` | 옵션 | 선택된 부품 record로 decal/relief 재투영(T1-A `coordinateTransform`+heightTex 재사용)해 3D 결함 입체 표시. |

### 동작
```
부품(레인/분류함) 클릭(raycast)
  → 그 부품의 record(실 inspector_result) 로드
  → PiP: 2D 원본+heatmap 토글, score/verdict/defect_class(YOLO)
  → 3D: 시편/부품 표면에 decal(heatmap) + relief(displacement) + 레이저 마커  (T1-A 재사용)
  → ESC 원복
```
- 데이터는 **그 부품이 검사된 시점의 실 record**(난수/최신값 대체 아님).
- bin이 ≤6개만 잔류하므로 클릭 대상은 최근 부품들. (전체 이력은 F2/보고서/DB 트랙.)

### 바인딩 / 가드
- 소스: 각 부품에 보관된 실 `inspector_result` record(단일 store 경유). 새 ws 없음.
- 메모리: image_b64(~4.5KB)+heatmap_b64(~13KB)/부품 → 보유 부품 수 제한(≤~30) 또는 NG만 풀 레코드.
- verdict 로직 불변.

### 미션 브리프
```
[F1] flowEngine 부품에 검사 record 전체 보관(part_id/verdict/score/tau/defect_class/defect_xy/defect_blob/image_b64/heatmap_b64).
     QCLine 흐름부품 onClick→onOpenPiP(record). ViewportSlot pipData=record. VisionPiP는 data override로 표시(기존).
     선택 부품 record로 decal/relief 재투영(T1-A 재사용). ESC 원복. 메모리 가드(≤~30, NG 우선). 난수/최신값 대체 금지.
[DONE] 분류함 부품 클릭→그 부품 실제 결함(2D+heatmap+종류+3D decal/relief) 표시. 브라우저 확인.
```

---

## F2. 클래스 학습 완료 신호 (per-class ready)

### 문제 / 현황
- `server/routers/classes.py` `class/train`은 완료 시 **`agent_status {agent: CID, state:'done', detail:'bank N 패치'}`만** 방송.
- 전용 "이 클래스 학습 완료 · 검사 준비됨" 신호가 없어 **UI가 어느 클래스가 준비됐는지(뱅크 보유) 모름**.

### 목표
학습 완료 시 **클래스별 완료 신호**를 보내고, 프론트가 **클래스 준비 상태(학습됨/미학습)**를 추적·표시. 가동 가능한 클래스를 한눈에.

### 산출물 (파일)
| 파일 | 수정 | 내용 |
|---|---|---|
| `server/routers/classes.py` | 수정 | bank 저장 직후 **`class_trained` 방송**: `{type:'class_trained', classId, n_patches, ready:true, ts}`. (기존 `agent_status done`은 유지.) |
| `server/routers/classes.py` 또는 `state.py` | 수정(경량) | `GET /api/classes/status` — `banks/*.npy` 스캔해 클래스별 `{classId, trained:bool, mtime}` 반환(로드시 초기 상태). |
| `frontend/src/hmi/signalReducer.js` | 수정 | `trained: {}` 상태 + `case 'class_trained'` → `{ trained: {...state.trained, [classId]: {ready, n_patches, ts}} }`. |
| `frontend/src/hmi/signalStore.js` | 수정 | `loadTrained()` — `/api/classes/status` 호출해 초기 `trained` 채움(연결 시 1회). |
| `frontend/src/hmi/panels/*` | 수정 | 클래스 목록/선택 UI에 **학습 완료 배지**(✓ 준비됨 N패치 / ⌛ 미학습). 가동 버튼은 준비된 클래스만 허용(미학습이면 안내). |
| (옵션) 토스트/로그 | — | `class_trained` 수신 시 "○○ 학습 완료(검사 준비됨)" 메시지. |

### 신호 형식 (기존 패턴, 새 타입 1개)
```json
{ "type":"class_trained", "classId":"bottle", "n_patches": 12000, "ready": true, "ts": 1719... }
```
> `class_result`(판정/FAT)와 구분: `class_trained`는 **학습(뱅크 생성) 완료** 신호.

### 동작
```
class/train 완료(bank 저장)
  → class_trained 방송 → reducer trained[classId]=ready
  → UI: 클래스 배지 "✓ 준비됨", 가동 가능
초기 로드: GET /api/classes/status → 이미 학습된 클래스 배지 표시(banks/*.npy 기준)
```

### 바인딩 / 가드
- 소스: 백엔드 학습 워커 실제 완료(bank 파일 저장) 시점 — **실 이벤트만**(가짜 완료 금지).
- `class_trained`는 신규 ws 타입 1개(학습 라이프사이클용, 의도적). 추론/검사 경로 불변.

### 미션 브리프
```
[F2] classes.py: bank 저장 직후 broadcast class_trained{classId,n_patches,ready,ts}. GET /api/classes/status(banks 스캔).
     signalReducer: trained{} + case 'class_trained'. signalStore: loadTrained()(연결 시 1회).
     UI: 클래스 학습완료 배지(✓준비됨/⌛미학습), 미학습 클래스 가동 차단+안내. class_result(판정)과 구분.
[DONE] 학습 완료 시 클래스별 완료 신호 수신·배지 갱신, 초기 로드시 학습된 클래스 표시. 브라우저 확인.
```

---

## 우선순위 제안
- **F1 먼저**(시각 임팩트 큼, T1-A 자산 재사용으로 빠름) → **F2**(학습 운영 편의).
- 둘 다 헤드리스 검증 가능 부분: flowEngine record 보관/prune(F1), reducer trained 상태기계(F2).

## DO / DON'T
- ✅ 부품별 실 record 클릭 조회 · 학습 완료 실 신호 · 기존 PiP/decal/relief·T1-A 재사용.
- ⛔ 난수/최신값 대체 · 가짜 완료 신호 · verdict 변경 · 검사 경로용 새 ws(F2 학습 신호만 예외).
