# ARIA HMI 대규모 리팩토링 명세 (realvirtual-WEB 아키텍처 참고)

> 목표: 현재의 임시방편 UI(인라인 스타일 패널·단순 대시보드)를 **걷어내고**,
> realvirtual-WEB식 **슬롯 기반 플러그인 3D-HMI**로 재구축하며, **기존 모든 API를 단일 시그널 스토어로 재연결**한다.
>
> ⚠️ **법적 주의**: realvirtual-WEB은 **AGPL-3.0**. 코드를 복사/빌드하면 전체 프로젝트를 AGPL로 공개해야 한다.
> → **아키텍처 패턴만 참고**하고, 우리 코드는 **처음부터 깨끗이 재구현**한다. realvirtual 소스/에셋/브랜딩 미사용.

---

## 1. realvirtual-WEB에서 가져올 아키텍처 교훈
1. **슬롯 기반 플러그인 HMI** — 단일 거대 UI 금지. 레이아웃을 named slot으로 나누고, 컴포넌트/플러그인을 슬롯에 끼움.
2. **Viewer 코어 + Signal Store + Event Bus** — 3D/데이터 코어가 상태를 노출, UI는 구독만. (`viewer.signalStore`, `viewer.on(...)`)
3. **Scene as Data** — 씬이 단일 진실 소스(realvirtual=GLB+rv_extras / 우리=`factory_scene.json`).
4. **운영 모드** — Standalone(mock/synthetic) ↔ Live(WebSocket). 우리 synthetic/실데이터와 매핑.
5. **표준 HMI 위젯 + ECharts** — KPI 카드·알람 패널·계층 브라우저·카메라 프리셋·차트 오버레이·탭 설정.

---

## 2. 타깃 아키텍처

```
                ┌──────────────── ARIAViewer (core) ────────────────┐
factory_scene → │ scene(Three.js/R3F) · lines/stations · selection   │
   /ws/floor  → │ ── SignalStore (zustand) ── event bus ─────────────│
   /ws/scan   → │   lines[], scan{}, detectors{}, alarms[], mode     │
                └───────────────┬───────────────────────────────────┘
                                │ (UI는 store 구독만)
        ┌───────────────────────┼────────────────────────────────────┐
        ▼            ▼          ▼            ▼            ▼             ▼
     topbar      kpi_bar   left_panel    viewport    right_panel   bottom_panel
   (상태/모드)  (KPI카드) (계층·검색)  (3D 씬)   (선택 컨텍스트) (알람·ECharts)
```
- **ARIAViewer**: `factory_scene.json` 로드 → 3D 씬 구성, `viewer.select(id)`, 이벤트(`selection-changed`,`frame`,`mode`).
- **SignalStore**: 모든 API를 여기로 모음 → UI는 store만 읽음(= "모든 API 재연결"의 단일 지점).
- 3D 씬은 **기존 FactoryFloor/SimulationView를 viewport 슬롯 콘텐츠로 재사용**(3D는 버리지 않음, UI 껍데기만 교체).

---

## 3. UI 슬롯 택소노미 (레이아웃 계약)
| slot | 내용 |
|---|---|
| `topbar` | 타이틀, 연결 상태, **모드 토글(Standalone/Live)**, 전역 KPI(OEE·결함률·온도) |
| `kpi_bar` | KPI 카드: Yield, Throughput, Tact-time, Queue/Drop |
| `left_panel` | **계층 브라우저**(Plant→Line/Cell→Station 트리 + 검색 + 타입 필터) |
| `viewport` | 3D 씬(FactoryFloor / Station relief) + 카메라 프리셋 |
| `right_panel` | 선택 컨텍스트: anomaly **heatmap**, YOLO **bbox**, detector 결과, 문서/이력 |
| `bottom_panel` | **알람/메시지 패널** + **ECharts 트렌드**(결함률·tact·anomaly score) |
| `command/button_panel` | 액션: 스캔 시작, 플랜트 전환, calibrate, train |
| `settings_drawer` | 탭: Scene / Visual / Detector(PatchCore·YOLO) / Interfaces(WS·MQTT·OPC UA) / AI |

> 플러그인 패턴: `registerPanel(slot, component)` / `viewer.use(plugin)`. 슬롯만 알면 어디든 끼움.

---

## 4. 컴포넌트 목록 (MUI 7 + ECharts 5)
- `AppShell`(MUI Grid/AppBar/Drawer) — 슬롯 레이아웃 컨테이너.
- `KpiCard`, `StatusBadge`, `ModeToggle`.
- `HierarchyTree`(MUI TreeView + 검색/필터), `CameraPresets`.
- `Viewport`(기존 3D 마운트), `HeatmapView`, `BBoxOverlay`, `DetectorResult`.
- `AlarmPanel`(MUI DataGrid), `TrendChart`(ECharts: line/bar), `GaugeChart`(queue/drop).
- `SettingsDrawer`(MUI Tabs).
- `ActionBar`(스캔/전환/calibrate/train 버튼 → API 호출).

---

## 5. API 재연결 맵 (전부 → SignalStore → 슬롯)
| API/소스 | SignalStore 키 | 표출 슬롯 |
|---|---|---|
| `/ws/floor`(floor_init/tick) | `store.lines`, `store.oee` | kpi_bar, left_panel, viewport LED, bottom 트렌드 |
| `/ws/scan`(observe→act) | `store.scan` | viewport relief, right_panel heatmap |
| `POST /api/floor/start` | action | button_panel |
| `POST /api/floor/select?line=` | `store.selection` | left_panel/viewport 클릭 |
| `POST /api/scan/demo` | action | button_panel |
| `/api/analyze`(PatchCore) | `store.detectors.patchcore` | right_panel |
| YOLO detector 결과 | `store.detectors.yolo` | right_panel BBoxOverlay |
| `/api/class/train`·`/validate` | action+status | settings/Training |
| `factory_scene.json` | `viewer.scene` | viewport, left_panel 트리 |
| (옵션) MQTT/OPC UA | `store.telemetry` | Interfaces 탭 |

> 규칙: **UI 컴포넌트는 fetch/ws를 직접 호출하지 않는다.** 모든 연결은 `signalStore`(+ `apiClient`)를 통해서만.

---

## 6. 마이그레이션 (삭제 / 유지 / 신규)
**DELETE(전면 제거)**: 인라인 스타일 HUD/패널 일체, 단순 Dashboard, 흩어진 div 오버레이, 임시 탭 로직.
**KEEP(유지·재사용)**: `apiClient`, 백엔드 전체, **3D 씬 빌더**(FactoryFloor/SimulationView/relief), 데이터 계약(`/ws/floor`·`/ws/scan`·`factory_scene.json`).
**BUILD(신규)**: `ARIAViewer` 코어, `signalStore`(zustand), `AppShell`+슬롯, MUI 컴포넌트, ECharts 패널, HierarchyTree, SettingsDrawer, 플러그인 등록기.

---

## 7. 기술 스택
- React 18 유지(+R3F 8) 또는 19로 업(+R3F 9) — 택1. **UI: MUI 7, 차트: ECharts 5, 상태: zustand.**
- 3D: 기존 Three.js/R3F 그대로 viewport에 마운트.
- TypeScript 권장(점진 마이그레이션 가능).

---

## 8. 단계 + 수용기준(런타임)
- **M1 Shell** — AppShell + 빈 슬롯 + ModeToggle. 게이트: 슬롯 레이아웃 렌더.
- **M2 Store** — signalStore가 `/ws/floor`·`/ws/scan` 구독 → 상태 채움. 게이트: store에 실시간 값.
- **M3 Slots** — kpi_bar·left_panel(트리)·viewport·right_panel·bottom(ECharts) 연결. 게이트: 라인 클릭→viewport·right_panel 동기.
- **M4 Actions** — button_panel/settings가 모든 API 호출(scan/floor/train/calibrate). 게이트: UI에서 전 기능 구동.
- **M5 Polish** — 알람 패널·카메라 프리셋·detector 오버레이(heatmap/bbox). 게이트: NG 시 알람+heatmap+bbox 동시.
- 검증은 빌드가 아니라 **런타임**: 구 UI 제거 + 새 슬롯 렌더 + 전 API가 store 경유로 반영 + Standalone/Live 토글 동작.

---

## 9. Claude Code 미션 브리프 (그대로 전달)
```
목표: ARIA 프론트엔드 UI를 realvirtual-WEB 아키텍처(슬롯 기반 플러그인 HMI + viewer/signalStore)를
참고해 전면 리팩토링하라. 단, realvirtual-WEB은 AGPL이니 코드 복사 금지 — 패턴만 보고 깨끗이 재구현.

[삭제] 현재 인라인 스타일 패널/HUD/단순 Dashboard 등 임시 UI 전부 제거.
[유지] apiClient, 백엔드, 3D 씬 빌더(FactoryFloor/SimulationView/relief), 데이터계약(/ws/floor,/ws/scan,factory_scene.json).
[신규]
 1) ARIAViewer 코어: factory_scene.json 로드→3D 씬, select(id), 이벤트버스.
 2) signalStore(zustand): /ws/floor·/ws/scan 구독 + apiClient 액션을 한 곳에 모음.
    ★ UI 컴포넌트는 fetch/ws 직접 호출 금지 — 전부 signalStore 경유.
 3) AppShell(MUI7) 슬롯 레이아웃: topbar/kpi_bar/left_panel/viewport/right_panel/bottom_panel/settings_drawer/button_panel.
 4) 컴포넌트: KpiCard, HierarchyTree(트리+검색), Viewport(기존3D 마운트), HeatmapView, BBoxOverlay,
    AlarmPanel, TrendChart/GaugeChart(ECharts5), SettingsDrawer(Scene/Visual/Detector/Interfaces/AI), ActionBar.
 5) 모드 토글 Standalone(synthetic) ↔ Live(/ws).
[API 재연결 맵] /ws/floor→lines/oee, /ws/scan→scan/heatmap, /api/scan/demo·/api/floor/start·select→액션,
   /api/analyze→patchcore, yolo→bbox, /api/class/train·validate→Training. 전부 signalStore로.
[스택] React+MUI7+ECharts5+zustand, 3D는 기존 Three.js/R3F 재사용. (TS 권장)
[수용기준] 구 UI 제거 + 슬롯 렌더 + 전 API가 store 경유 반영 + 라인클릭→viewport·right동기 +
   NG시 알람+heatmap+bbox 동시 + Standalone/Live 토글. (빌드 아닌 런타임으로 증명)
진행순서: M1 Shell → M2 Store → M3 Slots → M4 Actions → M5 Polish.
```

## 10. DO / DON'T
- ✅ realvirtual **패턴**(슬롯·signalStore·모드) 재구현. 3D 씬·API·백엔드 재사용.
- ⛔ realvirtual **코드/에셋/브랜딩 복사 금지(AGPL)**. UI 컴포넌트의 직접 fetch/ws 금지(store 경유). 3D 로직 재작성 금지.
