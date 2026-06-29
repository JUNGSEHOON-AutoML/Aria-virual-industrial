# 스토어 통합 — signalStore 단일화 (twinStore 흡수)

## 문제
- `signalStore.js`와 `twinStore.js`가 **각자 `new WebSocket`** 을 열어 WS 연결이 2개.
  둘 다 주석에 "단일 WS 지점"이라 적혀 모순. (+ 구 컴포넌트 SwarmChat/InspectorPanel/SimulationView도 자체 WS)
- 신 슬롯 계열(AppShell·panels/*·scene/*)=signalStore, 구 셸 계열(HmiShell·KpiBar·ViewportPanel·ChartPanel·MessagePanel·SettingsDrawer·InspectorContext)=twinStore 로 분기.

## 해결 (이 패키지)
**signalStore = 단일 스토어·단일 WS·단일 ingest.** twinStore는 그 위의 **얇은 어댑터**로 강등 → 2번째 WS 제거.
단일 `ingest`가 (1) reducer 구조화 상태 + (2) raw 타입 팬아웃(구 twinStore API)을 **동시에** 구동.

## 적용 (3파일)
| 파일 | 위치 | 동작 |
|---|---|---|
| `signalFanout.js` | `frontend/src/hmi/signalFanout.js` | **신규**(순수 팬아웃, Node 검증 가능) |
| `signalStore.js` | `frontend/src/hmi/signalStore.js` | **교체**(+raw 팬아웃/send/status 호환 export) |
| `twinStore.js` | `frontend/src/hmi/twinStore.js` | **교체**(자체 WS 제거 → signalStore 위임) |

> **컴포넌트는 한 줄도 안 고쳐도 됩니다.** twinStore의 기존 export(subscribe/getLatest/subscribeStatus/getStatus/sendCmd/ensureConnected)가 시그니처 그대로 유지되어 구 셸 계열이 그대로 동작합니다.

## 검증
- **헤드리스(빌드 아님)**: `node test_store_merge.mjs` → **16/16 PASS**.
  단일 ingest가 reducer 상태(kpi/scan/detectors/alarms/lines/agents/messages/selector)와
  raw 팬아웃(subscribeType/getLatestType/'*'/해제)을 동시에 올바로 구동함을 증명.
- **브라우저 확인(본인)**: ① DevTools Network·WS 탭에 **연결 1개만**, ② 구 셸(HmiShell 계열) 정상,
  ③ 신 슬롯(AppShell) 정상, ④ live 모드 메트릭/알람 갱신.

## 후속(선택, 별도 PR)
1. 구 셸 계열을 signalStore selector로 점진 이전 → twinStore 어댑터 제거.
2. 구 컴포넌트(SwarmChat/InspectorPanel/SimulationView)의 자체 WS도 signalStore로 통합(또는 레거시 삭제).
3. 스토어가 하나가 되면 아바타 embodiment 등 신규 기능은 이 단일 스토어 위에만 바인딩.
