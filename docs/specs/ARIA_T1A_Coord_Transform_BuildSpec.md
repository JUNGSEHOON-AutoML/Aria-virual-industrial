# T1-A 빌드 명세 — 2D(u,v)→3D(x,y,z) 좌표 변환 + 레이저/Decal 투영 (F-08)

> E-FOREST 시그니처(불량 지시 레이저 프로젝션)의 트윈판. **새로 짓기 아님 — 이미 ~70% 구현됨.**
> 이 명세는 흩어진 raycast 로직을 **재사용 가능한 `coordinate_transform` 모듈로 정형화**하고,
> 실카메라 경로(K·[R|t])와 **레이저 마커 시각화**를 추가하는 "마감" 빌드다.
> ⛔ 난수 금지(데이터 유도) · verdict 로직 불변 · 새 ws/엔드포인트 없음 · 스택 유지(C#/HALCON 금지).

---

## 0. 현재 레포 상태 (이미 있는 것 / 갭)
| 요소 | 레포 현황 | 상태 |
|---|---|---|
| heatmap peak (u,v) 추출 | `aria/inspection/result_encode.py` `_heatmap_to_b64_and_peak` → `defect_xy=[nx,ny]` | ✅ 있음 |
| WS 전달 | `inspector_result.defect_xy`(+image_b64/heatmap_b64) → `signalReducer` `scan` | ✅ 있음 |
| sim raycast (u,v)→(x,y,z) | `hmi/scene/inspectVfx.js` `buildDecal` + `InspectionSpecimen.jsx` 부스 카메라 | ✅ 있음 |
| Decal 부착 | `buildDecal` → `DecalGeometry` 적색 emissive | ✅ 있음 |
| **변환 정형화(모듈)** | raycast가 컴포넌트에 흩어짐 | ❌ **갭** |
| **실카메라 K·[R|t] 경로** | sim(raycast)만 | ❌ **갭** |
| **레이저 마커 투영 시각화** | decal만(레이저 빔/십자선 없음) | ❌ **갭** |
| **F-07 blob→면적/중심** | min_val 맵 존재, 추출 미정형 | ❌ **갭(경량)** |

→ 빌드 범위 = **갭 4개**. 기존 decal/raycast는 재사용·리팩터링.

---

## 1. 산출물 (파일 단위)
| 파일 | 신규/수정 | 내용 |
|---|---|---|
| `frontend/src/hmi/scene/coordinateTransform.js` | **신규** | (u,v)→(x,y,z) 단일 진입점. sim=raycast / real=K·[R|t]. blob 중심·면적 추출. |
| `frontend/src/hmi/scene/inspectVfx.js` | 수정 | `buildDecal`이 `coordinateTransform` 사용하도록 리팩터(중복 raycast 제거). |
| `frontend/src/hmi/scene/LaserMarker.jsx` | **신규** | 표면 (x,y,z)에 레이저 빔(라인)+십자선+점멸 — 레이저 투영 시각화. |
| `frontend/src/hmi/scene/InspectionSpecimen.jsx` | 수정 | decal + LaserMarker 동시. 변환은 모듈 위임. |
| `aria/inspection/result_encode.py` | 수정(경량) | peak에 더해 **blob 면적·중심**(F-07) 추가: `defect_blob={cx,cy,area,bbox}`. |
| `frontend/src/hmi/panels/VisionPiP.jsx` | 수정 | 좌표 표기 "(u,v)=… → (x,y,z)=…" + blob 면적. |

> 새 ws 타입 없음. `inspector_result` 페이로드만 소폭 확장(기존 패턴, `defect_xy`처럼).

---

## 2. coordinateTransform 모듈 — 단일 진입점 (정형화)
```
project2Dto3D({ uv, mode, camera, mesh, calib }) -> { point:Vector3, normal:Vector3, ok:boolean }

mode='sim'  : raycaster.setFromCamera(ndc(uv), camera) → mesh intersect → {point, face.normal}
mode='real' : K·[R|t]로 (u,v)→광선 → mesh intersect (또는 평면 교차) → {point, normal}
              calib = { K:[fx,fy,cx,cy], Rt:[3x4], imgW, imgH }
```
- **공통 계약**: 입력 uv는 항상 정규 [0..1] (heatmap/이미지 좌표). 내부에서 NDC 변환.
- sim 경로 = 기존 `buildDecal` raycast를 그대로 추출(난수 0).
- real 경로 = 캘리브 있으면 사용, 없으면 sim 폴백 + UI에 "캘리브 미설정(sim 폴백)" 표기.
- **난수 금지 가드**: uv가 없으면 `ok:false` 반환(억지 좌표 생성 금지).

## 3. 레이저 마커 시각화 (E-FOREST 시그니처)
- `LaserMarker({ point, normal, color })`: 천장 투사기(가상)에서 point로 내려오는 **얇은 발광 라인** +
  표면에 **십자선/링** + 점멸. "불량 지시 레이저"의 트윈 표현.
- decal(영역)과 병행: decal=결함 패치, laser=지시 포인터.

## 4. F-07 blob 정형화 (경량, 백엔드)
- `result_encode.py`: heatmap 임계화 → 최대 연결성분의 **면적(px)·중심(cx,cy)·bbox** 산출(numpy만, OpenCV 선택).
- `inspector_result.defect_blob = { cx, cy, area, bbox }` 추가 → 프론트 decal 크기 ∝ area, laser는 중심.

---

## 5. 데이터 바인딩 (실제만)
| 표출 | 소스 |
|---|---|
| (u,v) peak·blob | `inspector_result.defect_xy` / `defect_blob` (실 WS) |
| (x,y,z) | `coordinateTransform`(sim=raycast / real=K·[R|t]) — 클라 계산 |
| decal·laser | 위 (x,y,z) — 난수 아님 |
> 캘리브: sim=공짜(raycast), real=K·[R|t](실카메라 연결 시만). 새 ws/엔드포인트 없음.

## 6. 수용 기준 (런타임, 브라우저)
1. **유도 검증**: decal·laser 위치가 heatmap peak/GT와 **일치**(난수면 불일치로 즉시 실패).
2. 변환이 `coordinateTransform` 단일 모듈 경유(컴포넌트 중복 raycast 제거).
3. sim/real 동일 인터페이스 — real 캘리브 없으면 sim 폴백 + 명시 라벨.
4. 레이저 마커가 결함 표면점을 가리킴(점멸/십자선).
5. blob 면적이 decal 크기에 반영. anomaly score<τ=OK 불변.
- 시각 게이트는 본인 브라우저 확인(빌드 아님).

---

## 7. Claude Code 미션 브리프 (그대로 전달)
```
목표: 흩어진 2D→3D raycast를 coordinateTransform 단일 모듈로 정형화 + 레이저 투영 시각화 + F-07 blob.
재사용: 기존 inspectVfx.buildDecal·InspectionSpecimen 부스 카메라·result_encode.defect_xy. 재작성 금지.
★난수 금지: (x,y,z)는 항상 (u,v) heatmap peak에서 유도. uv 없으면 ok:false(억지 좌표 금지).

[1] coordinateTransform.js: project2Dto3D({uv,mode,camera,mesh,calib})→{point,normal,ok}.
    sim=raycaster.setFromCamera(ndc(uv),camera)→intersect. real=K·[R|t]→광선→intersect, 없으면 sim 폴백.
[2] inspectVfx.buildDecal을 [1] 사용하도록 리팩터(중복 raycast 삭제).
[3] LaserMarker.jsx: point/normal에 발광 라인+십자선+점멸. InspectionSpecimen에서 decal과 동시 표출.
[4] result_encode.py: heatmap 임계화→최대 blob 면적·중심·bbox → inspector_result.defect_blob 추가(numpy).
    decal 크기 ∝ area, laser=중심. 새 ws 타입 없음(페이로드 확장만).
[5] VisionPiP: "(u,v)→(x,y,z)" 좌표 + blob 면적 표기. real 캘리브 없으면 "sim 폴백" 라벨.
[바인딩] inspector_result만(단일 signalStore). verdict 로직 불변. C#/HALCON 전환 금지.
[DONE] decal·laser가 heatmap/GT와 일치(난수면 실패) · 변환 단일모듈 경유 · sim/real 동일 IF · blob 반영. 브라우저 확인.
```

## 8. DO / DON'T
- ✅ 변환 정형화·레이저 투영·blob·기존 decal 재사용·실 inspector_result 바인딩.
- ⛔ 난수 3D 좌표 · verdict 변경 · 새 ws/MCP 추론서버 · C#/HALCON/WPF 전환 · 실 하드웨어/PLC 통합.
