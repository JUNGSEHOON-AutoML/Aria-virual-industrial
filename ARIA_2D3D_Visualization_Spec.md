# ARIA — 2D↔3D 검사 시각화 구현 명세 (PiP · 스캔 전환 · Decal 역투영)

> 범위: **검사 트윈의 시각화/인터랙션 3종**(Vision PiP · 클릭 스캔 전환 · Decal 역투영)에 집중.
> - 합성 데이터 생성은 **기존 `ARIA_3D2D_Pipeline_Implementation_Spec`** 참조(중복 안 함).
> - **가상 시운전(PLC+충돌)·인체공학(아바타)은 물리엔진 필요 → 별도 트랙**(이 명세 제외).
> 기존 ARIA(viewport·signalStore·patchcore_engine) 위에 얹는다. 재작성 아님.

## OODA
- Observe: 2D를 "구석에 띄우기"는 시늉. 3D 표면 위치/스캔감/원본 동시성이 필요.
- Orient: PiP(원본+heatmap) + 클릭 스캔 전환(몰입) + Decal(불량을 표면에 정확히) = 셋이 한 흐름.
- Decide: 클릭 → 스캔 셰이더 → heatmap decal + PiP 동시 표출.
- Act: 아래 A·B·C.

---

## A. Vision Camera PiP 패널 (가상↔현실 연결감)
- 씬의 `vision_node`(검사 부스 카메라)를 **클릭(raycast)** → 측면/모달 패널 슬라이드 오픈.
- 패널 내용: **현재 2D 검사 원본** + **anomaly heatmap 오버레이**(toggle: 원본 / heatmap / overlay).
  - 라이브 스트림 URL이 있으면 스트리밍, 없으면 `inspector_result.image_b64`(마지막 검사 이미지).
  - heatmap = `patchcore_engine` min_val 업샘플 → 적색 컬러맵 alpha 합성.
- 헤더: PART ID · SCORE · τ · verdict(색). (점수는 anomaly score=낮을수록 정상 — 로직 불변.)

---

## B. 클릭 → 스캔 전환 (raycast + 와이어프레임/홀로 + 스캔라인 셰이더)
- 부품 **클릭(raycast)** → 선택.
- 전환 효과:
  1. 선택 부품에 **와이어프레임/홀로그램 오버레이**(material.wireframe 클론 또는 holo emissive).
  2. **스캔라인 셰이더**: `onBeforeCompile`로 월드Y varying 주입 →
     `float d=abs(vWorldY-uScanY); float glow=smoothstep(0.06,0.0,d); col+=glow*scanColor;`
     `uScanY`를 bbox.min.y→max.y 로 ~1s 애니메이션(위→아래 스캔선).
  3. 스캔 완료 → C의 heatmap decal 표출 + A의 PiP 오픈(동시).
- 경량: 셰이더 1개 + 와이어프레임 오버레이. 물리/리메시 없음.

---

## C. Decal 역투영 (2D 결함 → 3D 표면 스티커)
- 목적: "X:150,Y:200 불량" 같은 2D 좌표를 **3D 표면의 정확한 위치**에 적색 스티커로.
- **sim 경로(캘리브 불필요)**: 결함 픽셀의 NDC → `raycaster.setFromCamera(ndc, boothCamera)` → 부품 교점(point+normal) →
  `DecalGeometry(mesh, point, orientation(normal), size)` 로 **적색 emissive decal** 부착(map=heatmap 크롭).
- **전체 heatmap 드레이프**가 필요하면: projective texture(부스 카메라 프러스텀 셰이더) 또는
  유의 픽셀 raycast→표면 UV→동적 CanvasTexture 페인트.
- **실카메라 경로**: 내부 K + 외부[R|t] 캘리브로 (u,v)→월드 역변환 후 동일.
- 결과: 부품 표면 불량 위치에 붉은 decal/heatmap → 3D 어디에 불량인지 즉시 파악.

---

## D. 통합 흐름
```
부품/카메라 클릭(raycast)
  ├─ 카메라면 → A: PiP 패널(원본+heatmap)
  └─ 부품이면 → B: 와이어프레임+스캔라인 sweep(~1s)
                 → C: 역투영 decal(표면 불량 위치) + A: PiP 동시 오픈
ESC → 원복(decal/홀로 제거, 패널 닫기)
```

---

## E. 데이터 바인딩 (실제 타입만 — 유령 엔드포인트 금지)
| 표출 | 소스 |
|---|---|
| 2D 원본·heatmap·score·verdict·part_id | `inspector_result` / `/api/analyze`(min_val) |
| decal 위치 | heatmap peak / mask centroid → 부스 카메라 raycast(sim) |
| 선택/스캔 트리거 | viewport raycast(클라이언트) |
> 캘리브: sim=raycast(공짜), real=K·[R|t](실카메라 연결 시만). 새 ws/엔드포인트 만들지 않음.

---

## F. 기업 활용 맥락 (이해 확인 + 범위 구분)
| 활용 | 우리 처리 |
|---|---|
| 합성 데이터 무한 생성 | ✅ 기존 `ARIA_3D2D_Pipeline_Implementation_Spec`(M1) |
| 2D→3D 시각화/스캔 | ✅ **이 명세(A·B·C)** |
| 가상 시운전(PLC+충돌) | ⏸ 별도 트랙 — 물리엔진/PLC 필요(현 범위 밖) |
| 인체공학(아바타 동선) | ⏸ 별도 트랙 |

---

## G. 단계 + 런타임 게이트
- **S1 PiP** — vision_node 클릭 → 원본+heatmap 패널. 게이트: 클릭 시 2D 결과 표출.
- **S2 스캔 전환** — 부품 클릭 → 와이어프레임+스캔라인 sweep. 게이트: 스캔선이 위→아래로 지나감.
- **S3 Decal 역투영** — 스캔 후 표면 불량 위치에 적색 decal. 게이트: **decal이 ground_truth/heatmap 위치와 일치**.
- **S4 통합** — 클릭→스캔→decal+PiP 동시, ESC 원복. 게이트: 한 동작으로 전체 흐름.
- 시각 게이트는 본인 브라우저 확인(빌드 아님).

---

## H. Claude Code 미션 브리프 (그대로 전달)
```
목표: 검사 트윈 viewport에 2D↔3D 시각화 3종 추가. viewport/signalStore/patchcore 재사용, 재작성 금지.
범위: PiP·스캔전환·Decal 역투영만. 가상시운전(PLC/충돌)·인체공학은 제외(별도 트랙, 물리엔진 금지).

[A] Vision PiP: vision_node 클릭(raycast)→측면 패널. 2D 원본(inspector_result.image_b64 또는 스트림)
    + anomaly heatmap(min_val 업샘플 적색 오버레이) 토글. 헤더에 part_id/score/τ/verdict.
[B] 클릭 스캔 전환: 부품 raycast 선택→와이어프레임/홀로 오버레이 + 스캔라인 셰이더(onBeforeCompile,
    uScanY를 bbox y범위로 ~1s 애니메이션, 위→아래 발광선). 완료 후 C·A 트리거.
[C] Decal 역투영: heatmap peak/mask centroid 픽셀→부스 카메라 raycast→부품 교점(point,normal)→
    DecalGeometry 적색 emissive decal(map=heatmap). 전체 드레이프는 projective texture 옵션.
    sim=raycast(캘리브 불필요), real=K·[R|t]는 실카메라 시만.
[흐름] 클릭→(카메라:PiP)/(부품:스캔→decal+PiP), ESC 원복.
[바인딩] 실제 inspector_result·/api/analyze만. 새 ws 금지. verdict는 anomaly score(낮을수록 정상) 로직 불변.
[DONE] S1~S4 브라우저 런타임: PiP 표출·스캔선 sweep·decal이 불량 위치와 일치·통합 흐름. (빌드 아님)
```

## I. DO / DON'T
- ✅ PiP·스캔셰이더·Decal 역투영. viewport/patchcore 재사용. 실제 엔드포인트.
- ⛔ 물리엔진/PLC 가상시운전·아바타(별도 트랙), verdict 로직 변경, 새 엔드포인트,
   AGPL/Unity 코드 복사, 로봇 기구학 이탈.
