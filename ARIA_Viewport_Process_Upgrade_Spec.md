# ARIA Viewport 고도화 명세 — 공정 충실 3D 검사 라인 (realvirtual 참고)

> **두 이미지 정리**
> - Image 1 (현재 HMI): 슬롯·signalStore·KPI·알람·ECharts·액션 → **유지**. 바꾸지 않는다.
> - Image 2 (realvirtual): **뷰포트 3D 품질 목표**(실장비·박스 흐름·연결 레이아웃).
> - "더 공정스럽게" = realvirtual의 일반 물류보다 **검사 공정에 충실**: 인입→비전부스→판정→OK/NG 물리분기→분류함,
>   그 분기를 **실제 추론 verdict로 구동**. (= 우리만의 차별점)
>
> ⚠️ **AGPL**: realvirtual 코드/GLB/브랜딩 사용 금지. 룩만 참고, 장비 프리팹은 직접(경량 절차적) 제작.

대상: 기존 HMI **viewport 슬롯의 씬 빌더만 교체**. HMI 셸·signalStore·슬롯·API 매핑은 그대로.

---

## 1. 목표 / 비목표
**목표**: (1) 장비 컴포넌트 라이브러리(롤러 컨베이어·곡선·부스·diverter·분류함·신호탑), (2) **연결된 공정 네트워크**(인입→검사→분기→분류), (3) **verdict 구동 물리 분기**(NG=푸셔→NG함, 신호탑 적색), (4) 경량 리얼리즘.
**비목표**: realvirtual 코드/에셋 복제, 헤비 GLB, 물리엔진(중력/충돌 솔버), HMI 셸 재작성, 유령 엔드포인트 재도입.

---

## 2. 핵심 설계 로직 (5)
### 2.1 Equipment Component Library (프리팹 시스템)
- 모듈형 산업 부품을 **파라메트릭 프리팹 + 포트(in/out) + 라이브 신호 바인딩**으로 정의.
- 포트 규약으로 부품을 이어 붙여 라인을 구성(realvirtual의 컴포넌트 라이브러리 개념을 우리식으로).

### 2.2 Scene as Connected Network (factory_scene.json 확장)
- 기존 "병렬 레인" → **장비 인스턴스 배열 + 연결(port→port)**. 자재가 토폴로지를 따라 흐른다.
- 데이터만 바꾸면 라인 토폴로지(직선/곡선/합류/분기)가 바뀐다.

### 2.3 Material Flow Engine
- `InfeedSource`에서 부품 spawn → 세그먼트 속도로 이동 → `VisionBooth`에서 dwell(촬영) → `Diverter`가 verdict로 경로 선택 → `SortBin` 누적. **토폴로지 경로 추종**(직선 레인 아님).

### 2.4 공정 충실 검사 로직 (★ 더 공정스럽게)
- `VisionBooth` = 실제 추론 지점: 부품이 멈춰 카메라+링/돔 라이트 아래 촬영 → `inspector_result`(verdict/score/bbox).
- `Diverter`(푸셔/에어블로) = **물리적 OK/NG 분기**: verdict=NG면 부품을 NG 레인으로 밀어냄.
- `StackLight`(andon 신호탑) = 부스 상태(녹=run / 황=inspecting / 적=NG)로 점등 → 즉시 "공장" 인지.

### 2.5 경량 리얼리즘
- 롤러는 **InstancedMesh**(컨베이어당/전역 1 draw call 지향), 프레임·다리·가드·신호탑은 공유 지오메트리.
- 환경 토글: **planner(밝은 체커보드)** ↔ **control-room(현 다크)**. soft shadow 1개. 그리드 바닥.
- LOD: 선택된 부스만 정밀(relief/heatmap), 나머지는 경량.

---

## 3. 프리팹 카탈로그
| prefab | 지오메트리(경량) | 파라미터 | 라이브 신호 |
|---|---|---|---|
| `InfeedSource` | 호퍼+가드 | material(MVTec), rate | — |
| `RollerConveyor` | 프레임+**instanced 롤러**+다리 | length,width,speed | run/stop |
| `CurveConveyor`/`Turntable` | 디스크/곡선 프레임 | angle | — |
| `Merge`/`ChainTransfer` | 합류 프레임 | — | — |
| `VisionBooth` | 아치+area camera+**돔/링 라이트**+dwell | category | inspector_state, inspector_result |
| `Diverter`/`Pusher` | 푸셔 암/블로 노즐 | routes(OK/NG) | inspector_result.verdict |
| `SortBin` | 적재함+카운터 | kind(OK/NG) | 누적 count |
| `StackLight`(andon) | 3단 신호탑(녹/황/적) | — | 부스 state/verdict |
| `Storage`/`OutfeedSink` | 적재 플랫폼 | — | — |
| `SupportLeg`/`SideGuard` | 다리/가드(디테일) | — | — |

---

## 4. scene_json 확장 예시 (연결 네트워크)
```jsonc
{
 "factory": { "id":"aria-qc-line", "environment":{"tone":"planner|control_room","floor":"checker_grid","shadows":true},
  "equipment": [
   {"id":"src1","type":"InfeedSource","material":"metal_nut","pos":[0,0,0],"ports":{"out":"p1"}},
   {"id":"c1","type":"RollerConveyor","length":6,"speed":0.06,"pos":[2,0,0],"ports":{"in":"p1","out":"p2"}},
   {"id":"booth1","type":"VisionBooth","category":"metal_nut","pos":[9,0,0],
     "bind":{"state":"inspector_state","result":"inspector_result"},"ports":{"in":"p2","out":"p3"}},
   {"id":"st1","type":"StackLight","attach":"booth1","bind":{"state":"inspector_state","verdict":"inspector_result.verdict"}},
   {"id":"div1","type":"Diverter","pos":[12,0,0],"bind":{"route":"inspector_result.verdict"},"ports":{"in":"p3","ok":"p4","ng":"p5"}},
   {"id":"binOK","type":"SortBin","kind":"OK","pos":[15,0,1.5],"ports":{"in":"p4"}},
   {"id":"binNG","type":"SortBin","kind":"NG","pos":[15,0,-1.5],"ports":{"in":"p5"}}
  ],
  "connections": [["src1.out","c1.in"],["c1.out","booth1.in"],["booth1.out","div1.in"],
                  ["div1.ok","binOK.in"],["div1.ng","binNG.in"]]
 }
}
```

---

## 5. 라이브 바인딩 맵 (★ 실제 /ws/chat 타입에만 — 유령 엔드포인트 금지)
| 장비/표출 | 실제 소스(signalStore selector) |
|---|---|
| VisionBooth 상태/촬영 | `inspector_state` |
| Diverter 경로, StackLight, NG 분기 | `inspector_result.verdict / score / defect_class / bbox` |
| SortBin OK/NG 카운트 | `inspector_result` 누적 / `class_result` |
| right_panel heatmap/bbox | `inspector_result` |
| KPI(yield/tact/throughput) | `inspector_state` 파생(현행 매핑 유지) |
> 직전 턴에서 Claude Code가 재매핑한 실제 타입 그대로 사용. 새 ws/엔드포인트 만들지 않음.

---

## 6. 마이그레이션
**유지**: HMI 셸·슬롯·signalStore·apiClient·API 매핑·KPI/알람/ECharts.
**교체**: viewport 씬 빌더(추상 레인 → 장비 프리팹 기반 연결 네트워크).
**연동**: 장비 라이브 바인딩은 §5 selector만 구독(UI 직접 fetch 금지 규칙 유지).
**트리**: HierarchyTree는 equipment 토폴로지(Source→Conveyor→Booth→Diverter→Bin)로 채움.

---

## 7. 단계 + 런타임 게이트
- **V1 프리팹+직선라인** — Source→RollerConveyor→VisionBooth→Diverter→OK/NG Bin + StackLight 1줄 렌더. 게이트: "QC 라인"으로 보임.
- **V2 연결 네트워크** — scene_json의 equipment+connections로 토폴로지(곡선/합류) 데이터 주도 생성. 게이트: JSON만 바꿔 레이아웃 변경.
- **V3 Flow+verdict 분기** — 부품 흐름 + `inspector_result`→Diverter 물리 분기 + StackLight. 게이트: **NG 부품이 실제로 NG함으로 가고 신호탑 적색**(브라우저 확인).
- **V4 환경 폴리시** — 조명/바닥/다리/가드/shadow + planner↔control-room 토글. 게이트: realvirtual급 룩.
- **V5 부스 클로즈업** — 선택 부스 → relief/heatmap(기존 재사용). 게이트: 드릴다운 검사.
- 데이터 동기는 헤드리스로, **시각 게이트(V3·V4·V5)는 본인 브라우저에서 직접 확인** 후 done.

---

## 8. Claude Code 미션 브리프 (그대로 전달)
```
목표: HMI의 viewport 3D 씬만 고도화하라. HMI 셸/signalStore/슬롯/API매핑은 건드리지 마.
지금의 추상 레인을 "공정 충실 검사 라인"으로 교체: 인입→롤러컨베이어→비전부스→Diverter(OK/NG 물리분기)
→분류함 + 신호탑(andon). 분기는 실제 inspector_result.verdict 로 구동.
realvirtual 룩 참고하되 AGPL이니 코드/GLB/브랜딩 복사 금지 — 장비 프리팹은 경량 절차적으로 직접 제작.

[BUILD]
1) 장비 프리팹 라이브러리: InfeedSource, RollerConveyor(롤러는 InstancedMesh), Curve/Turntable, VisionBooth(area cam+돔라이트+dwell), Diverter/Pusher, SortBin(OK/NG 카운터), StackLight(3단), Storage. 각 프리팹=파라미터+포트(in/out)+라이브신호.
2) scene_json 확장: equipment[]+connections[](port→port) 연결 네트워크. 데이터로 토폴로지 결정.
3) Material flow: Source spawn→세그먼트 이동→Booth dwell(촬영)→Diverter가 verdict로 OK/NG 경로→Bin 누적.
4) 라이브 바인딩(실제 타입만): booth←inspector_state, diverter/stacklight/NG분기←inspector_result.verdict/score/bbox, bin count←inspector_result/class_result. UI 직접 fetch 금지(signalStore selector 경유).
5) 환경: planner(밝은 체커보드)↔control_room 토글, soft shadow, 다리/가드 디테일. 경량 유지(instancing/공유지오/LOD).

[DON'T] HMI 셸/signalStore 재작성 금지. 새 ws/엔드포인트 금지(기존 /ws/chat 타입 사용). 물리엔진 금지. realvirtual 코드/에셋 금지.
[DONE WHEN] V3: NG 부품이 물리적으로 NG함으로 분기+신호탑 적색 / V4: realvirtual급 룩 / 전부 브라우저 런타임으로 확인. (빌드 아님)
진행순서: V1 직선라인 → V2 네트워크 → V3 verdict분기 → V4 환경 → V5 부스 클로즈업.
```

## 9. DO / DON'T
- ✅ 장비 프리팹+연결 네트워크+verdict 물리분기+신호탑. 경량(instancing). 실제 /ws/chat 타입 바인딩.
- ⛔ realvirtual 코드/GLB/브랜딩 복제(AGPL). 물리엔진. HMI 셸/signalStore 재작성. 유령 엔드포인트.
