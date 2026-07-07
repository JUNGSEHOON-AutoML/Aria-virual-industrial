# ARIA — 2D 추론 → 3D Decal 역투영 (교정 명세)

> 원문(난수 Mock + 전면 개편 + 새 MCP 추론 브릿지)의 결함을 교정한 버전.
> 핵심 원칙: **3D 결함 위치는 난수가 아니라 2D 히트맵에서 *유도*된다.** 실 파이프라인(`inspector_result`)에 바인딩하고 기존 씬을 **확장**한다(재작성 아님).

## 0. 원문 결함 → 교정 매핑
| # | 원문 | 교정 |
|---|---|---|
| 1 | `runInference()`가 임의의 3D 좌표(Math.random Vector3) 반환 | ❌ 난수 발명. ✅ **2D 히트맵 peak(u,v)→카메라 raycast→표면 point+normal** |
| 2 | "전부 Mock(Math.random)" | Mock은 **Standalone 폴백**만. **Live=실 `inspector_result`**(score/tau/verdict/bbox/heatmap) |
| 3 | "프론트→새 MCP 서버로 추론" | 추론은 **기존 백엔드 → 단일 `/ws/chat`** 유지. MCP는 에이전트 도구용 |
| 4 | VLM이 "마찰로 발생" 원인 단정 | VLM은 **관측(종류/위치/심각도) 서술 + 원인=가설+신뢰도**(확인 요망) |
| 5 | "그냥 기어/실린더로 교체" | **실제 제품 클래스**(MVTec + products/) 형상, 클래스별 2D→3D |
| 6 | "전면 개편" | 기존 `QCLine/VisionBooth/flowEngine` **확장**(버리지 말 것) |
| 7 | "Score 0.85" 방향 누락 | **anomaly score=낮을수록 정상, OK if score<τ** 명시(불변) |

---

## 1. 부품 형상 — 실제 제품 클래스 기반
- 임의 기어/실린더 금지. **클래스별**:
  - 표면 클래스(carpet/tile/leather/wood/grid) → 평면 + **displacement relief**(결함=높이).
  - 부품 클래스(bottle/capsule/metal_nut/screw… + products/ dowel·foam·cable_gland·potato) → 제품 프록시/메시(가능하면 depth 2.5D), 금속이면 `MeshStandardMaterial{metalness~0.8}`.
- 형상은 현재 검사 중인 **라인의 클래스**(`signalStore.classes`/선택)에서 결정.

## 2. 추론 소스 — Live(실) / Standalone(Mock) 동일 파이프라인
- **단일 경로**: 둘 다 `{ image, heatmap(2D), score, tau, verdict, bbox }` 형태를 산출 → **같은 역투영 코드**로 흐른다.
- **Live**: `inspector_result`(image_b64 + min_val 히트맵 + score/tau/verdict/bbox) 구독(단일 store).
  - heatmap이 메시지에 없으면 백엔드가 `patchcore_engine`의 min_val(28×28)을 함께 publish(소규모 추가).
- **Standalone Mock**: 합성 2D 히트맵(임의 2D 픽셀에 blob) + 이미지 생성. **단, verdict만 난수로 찍지 말고 2D 히트맵을 만들어** §3의 동일 raycast를 태운다(Mock도 매핑 파이프라인을 그대로 증명). placeholder임을 UI에 표기.

## 3. 2D → 3D 역투영 (Decal) — 난수 금지, 유도만
```
heatmap(2D) → argmax 픽셀 (u,v)            // 결함 위치는 데이터에서
   → VisionBooth 카메라의 NDC로 변환
   → raycaster.setFromCamera(ndc, boothCamera)
   → 부품 메시 intersect → { point, face.normal, uv }
   → DecalGeometry(mesh, point, orient(normal), size∝blob) + 적색 emissive(map=heatmap 크롭)
```
- bbox가 있으면 decal 크기/형태에 반영. 표면 클래스는 동일 (u,v)→UV로 relief+적색.
- **결과 일치 검증**: decal이 ground_truth/heatmap 위치와 같아야 함(난수면 불일치 → 즉시 발각).

## 4. VLM 분석 패널 (클릭 시 우측)
- 입력: 원본 이미지 + 히트맵 + (위치/크기/score/verdict).
- 출력 구조: `관측`(결함 종류·위치·심각도, 데이터 근거) / `추정 원인`(가설 + 신뢰도, "확인 요망" 명시) / `권장 조치`.
- ⚠️ 원인 단정 금지(환각). "마찰로 발생" 같은 단정 대신 "표면 스크래치 관측 — 추정 원인: 이송 마찰(신뢰도 0.4, 확인 요망)".
- Mock VLM이면 placeholder 라벨. 실제는 `vision_agent`/VLM이 실제 이미지 근거로 생성.
- score 표기는 **τ 대비**(낮을수록 정상) 게이지로(앞 Gemini-ideal 명세 일치).

---

## 5. 데이터 바인딩 / 재사용 (실제만)
| 표출 | 소스 |
|---|---|
| 이미지·히트맵·score·verdict·bbox | `inspector_result`(단일 signalStore, selectScan/selectDetectors) |
| decal 위치 | heatmap peak → VisionBooth 카메라 raycast(난수 아님) |
| VLM 리포트 | `vision_agent`/VLM(실) · Standalone은 placeholder |
| 부품 클래스 | `signalStore.classes` / 선택 컨텍스트 |
- 확장 대상(재작성 금지): `hmi/scene/QCLine.jsx`, `prefabs/VisionBooth.jsx`, `Diverter.jsx`, `flowEngine.js`, `RightPanel`.
- 새 ws/엔드포인트·새 MCP 추론서버 만들지 않음.

## 6. 수용 기준 (런타임)
1. **유도 검증**: decal 위치가 heatmap peak/ground_truth와 **일치**(난수면 불일치로 즉시 실패).
2. Live: 실 `inspector_result`로 부품·decal·VLM 갱신 / Standalone: Mock도 동일 raycast 경로.
3. 부품 형상이 **현재 클래스**에 맞음(임의 기어 아님).
4. VLM이 원인을 **가설+신뢰도**로 표기(단정 아님).
5. anomaly score=낮을수록 정상, OK if score<τ(불변).
- 시각 게이트는 본인 브라우저 확인(빌드 아님).

---

## 7. Claude Code 미션 브리프 (그대로 전달)
```
목표: 기존 QCLine/VisionBooth/flowEngine을 확장해 "2D 추론 결과를 3D 표면에 역투영"한다.
★난수 금지: 3D 결함 위치는 2D 히트맵 peak를 VisionBooth 카메라로 raycast해 유도한다(Math.random Vector3 금지).
재작성 금지 — 기존 씬/단일 signalStore/patchcore 재사용.

[1] 부품 형상: 임의 기어/실린더 대신 현재 라인 클래스(MVTec + products/ dowel·foam·cable_gland·potato)에 맞춤.
    표면=displacement relief, 부품=프록시/2.5D, 금속이면 MeshStandardMaterial metalness~0.8.
[2] 추론 소스: Live=실 inspector_result(image_b64+min_val heatmap+score/tau/verdict/bbox) 구독(단일 store).
    Standalone=Mock이지만 verdict만 난수 금지 — 합성 2D 히트맵을 만들어 [3]의 동일 raycast를 태움(placeholder 표기).
    heatmap이 메시지에 없으면 백엔드가 patchcore min_val을 함께 publish(소규모 추가).
[3] 역투영: heatmap argmax (u,v)→NDC→raycaster.setFromCamera(ndc, boothCamera)→메시 intersect(point,normal)
    →DecalGeometry 적색 emissive(map=heatmap 크롭, size∝blob/bbox). 표면 클래스는 (u,v)→UV로 relief+적색.
[4] VLM 패널(우측): 관측(종류/위치/심각도)+추정원인(가설+신뢰도,"확인 요망")+권장조치. 원인 단정 금지.
    실=vision_agent/VLM(이미지 근거), Standalone=placeholder 라벨. score는 τ대비(낮을수록 정상) 표기.
[바인딩] inspector_result만(단일 signalStore selectScan/selectDetectors). 새 ws/MCP 추론서버 금지.
[DONE] decal 위치가 heatmap/ground_truth와 일치(난수면 실패) · Live/Standalone 동일 경로 · 클래스별 형상
       · VLM 가설표기 · score<τ=OK. 브라우저 런타임으로 확인.
```

## 8. DO / DON'T
- ✅ 히트맵 peak→raycast 유도 decal · 실 inspector_result 바인딩 · 기존 씬 확장 · VLM 가설표기.
- ⛔ 난수 3D 좌표 · 전부 Mock · 새 MCP 추론 서버 · 전면 개편(QCLine 폐기) · VLM 원인 단정 · verdict 로직 변경.
