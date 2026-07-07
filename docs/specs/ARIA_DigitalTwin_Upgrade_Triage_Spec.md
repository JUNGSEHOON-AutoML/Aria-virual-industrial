# ARIA 디지털 트윈 고도화 — 트리아지 빌드 명세 (Virtual Factory Builder/DMOA 대비)

> 레포 대조 결과 트리아지. **WebRTC 클라우드 렌더링은 건너뛴다**(경량 Three.js는 이미 브라우저/모바일 직접 구동 — 포토리얼 Unity로 갈 때만 의미).
> 지금 할 고가치·온스택·차별 기능 3종: **① 3D 리플레이 블랙박스 ② 가상-현실 편차→병목 진단 ③ 객체 디제틱 팝업.**
> 전제: `factory_scene.json`(scene-as-data) 부재 → 토대로 먼저. **진행 중 T1-B를 밀어내지 않게** 별도/후속 트랙.

## 0. 트리아지
| 문서 항목 | 분류 | 처리 |
|---|---|---|
| 3D 에셋 라이브러리 | 있음 | `scene/prefabs/`+`flowEngine` 재사용 |
| IoT/PLC→3D 매핑 | 있음 | `twin_bridge`(OPC UA/MQTT)→signalStore |
| OEE/KPI 대시보드 | 있음 | `KpiBar`+reducer |
| 객체 클릭→정보 | 있음(강화) | `selectContext` → **③ 디제틱 팝업** |
| **WebRTC 클라우드 렌더링** | **건너뜀** | 경량 Three.js엔 불필요 |
| 드래그앤드롭 GUI 에디터 | 보류(큰 트랙) | 먼저 scene-as-data |
| 공장 간 연합(federation) | 보류 | 단일 트윈엔 시기상조 |
| 파라미터 what-if 최적화 | 보류(중) | 편차 진단 후 |
| **3D 리플레이 블랙박스** | **지금 ①** | DB+signalStore |
| **가상-현실 편차→병목** | **지금 ②** | async_pipeline 큐/tact |

---

## 1. ① 3D 리플레이 블랙박스 (차별 핵심)
**원리**: 씬이 이미 signalStore 상태에서 렌더되므로 — **데이터 스트림만 기록 → 리플레이 모드에서 되먹임 → 3D 자동 재구성.** 지오메트리/모션 별도 저장 불필요.
- **Recorder**: signalStore `ingest`를 탭 → 타임스탬프 프레임(라인 메트릭·inspector_result·alarm·agent 이벤트)을 **링버퍼**(최근 N분, 메모리) + 필요시 `core/database`(sqlite)에 영속.
- **Replay 모드**: 라이브 WS 대신 기록을 store에 재주입. **타임라인 스크러버 + play/pause/속도 + "이슈로 점프"**(NG/alarm 타임스탬프=마커). 기존 씬이 그대로 과거를 재생.
- **종료**: 라이브 복귀. 리플레이 중엔 실 액션/승인 비활성(읽기 전용).
- 재사용: signalStore, `core/database`. 신규: `twinRecorder.js`(기록) + `ReplayBar`(UI) + reducer `replay` 플래그.

## 2. ② 가상-현실 편차 → 병목 진단
- **sim 베이스라인**: 라인/스테이션별 기대 throughput·tact·queue(공칭 파라미터 또는 병렬 이상 tick).
- **Comparator**: 실 큐/tact가 베이스라인을 임계 이상 초과(예: real queue > base×1.5) → 해당 스테이션 **적색 박스/StackLight + "BOTTLENECK" 라벨**.
- 재사용: `async_pipeline`(queue/tact), floor 메트릭, signalStore. 신규: `deviationModel`(기대치) + comparator selector.
- ⚠️ 초기엔 단순 기대-비율 모델로 충분(풀 물리 sim 불필요).

## 3. ③ 객체 디제틱 팝업
- 3D에서 로봇/제품/스테이션 클릭(raycast) → **그 객체 옆 떠 있는 팝업**(가장자리 패널 아님)에 라이브 데이터(state·tact·temp·last verdict·score) 추적 표시.
- 재사용: `selectContext`+raycast. 디제틱(공간 내부) 배치로 "공장 현장감"(앞 비주얼 트리아지와 일관).

---

## 4. 토대 / 가드레일
- **토대**: `factory_scene.json`(scene-as-data) 포팅 — 데이터 주도 에셋 배치(드래그앤드롭/편차 모델의 기반).
- 단일 signalStore selector만(직접 fetch/ws 금지). 실제 `/ws/chat` 타입만. verdict(anomaly score) 로직 불변.
- **건너뜀**: WebRTC 클라우드 렌더링. **보류**: 드래그앤드롭 에디터·federation·what-if(별도 트랙).
- 재작성 금지(기존 씬/HMI 확장). perf: 리플레이는 데이터 재생(경량), 매프레임 무거운 연산 금지.
- **T1-B 먼저/병행**, 이 트랙이 밀어내지 않게.

---

## 5. Claude Code 미션 브리프 (그대로 전달)
```
목표: 디지털 트윈에 3종 추가 — ①3D 리플레이 블랙박스 ②가상-현실 편차 병목진단 ③객체 디제틱 팝업.
기존 씬/단일 signalStore/core.database/async_pipeline 재사용, 재작성 금지. WebRTC 클라우드 렌더링은 하지 마(경량 Three.js 불필요).
진행 중 T1-B를 밀어내지 않게(후속/병행).

[전제] factory_scene.json(scene-as-data) 포팅 — sceneModel 하드코딩 폴백 대체, 데이터 주도 에셋 배치.

[①리플레이] twinRecorder.js: signalStore.ingest 탭→타임스탬프 프레임(라인메트릭/inspector_result/alarm/agent) 링버퍼(최근 N분)+선택 sqlite 영속.
  replay 모드: 라이브 대신 기록 재주입 → 기존 씬이 과거 재생. ReplayBar(스크럽/play/pause/속도/이슈 점프 마커=NG·alarm ts). 리플레이 중 실액션·승인 비활성. reducer에 replay 플래그.
[②편차] deviationModel: 라인/스테이션 기대 throughput·tact·queue(공칭). comparator: real이 기대×임계 초과→스테이션 적색박스/StackLight+BOTTLENECK 라벨. async_pipeline 큐/tact 재사용. 초기 단순 기대-비율 모델.
[③팝업] 객체 raycast 클릭→그 객체 옆 디제틱 팝업(공간 내부)에 라이브 데이터(state/tact/temp/last verdict/score). selectContext 재사용.

[DON'T] WebRTC 클라우드 렌더링·드래그앤드롭 에디터·federation·what-if(별도 트랙). 새 ws/엔드포인트, 직접 fetch, verdict 로직 변경, 씬 재작성, 매프레임 무거운 연산.
[DONE] 브라우저 런타임: 리플레이가 과거 NG 시점을 3D로 재생·스크럽 / 편차 시 스테이션 적색+BOTTLENECK / 객체 클릭 디제틱 팝업. (빌드 아님)
진행순서: 전제(scene-as-data) → ① → ② → ③.
```

## 6. "어떻게 전달할까" 요약
- 문서 통째 ✗ → **위 미션 브리프**만. WebRTC는 명시적으로 "하지 마".
- 차별 핵심은 **①3D 리플레이**(데이터만 기록→되먹임=3D 자동재생, 가장 싸고 인상적).
- 드래그앤드롭 에디터·federation은 원할 때 **별도 트랙**으로 따로 요청. T1-B 먼저.
