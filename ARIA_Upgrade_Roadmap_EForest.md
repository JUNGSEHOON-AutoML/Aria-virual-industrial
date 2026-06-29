# ARIA 고도화 로드맵 — E-FOREST/SRS 대비 (레포 기준)

> 결론: 이 SRS의 소프트웨어/AI/트윈 부분은 **이미 상당수 레포에 존재**한다. 고도화 = 새로 짓기가 아니라
> **(0) 토대 정리 → (1) 스택에 맞는 고가치 기능 연결**. 하드웨어 의존부는 시뮬/개념으로만.
>
> ⚠️ **스택 경고**: SRS의 "C# HALCON WPF로 작성" 지시 **따르지 말 것** — Python(PatchCore)+React/Three.js 시스템을
> 통째로 버리게 된다. **PatchCore = HALCON-AD의 오픈 등가물.** 스택 유지.

---

## 1. SRS ↔ 레포 현황 (이미 있는 것 / 갭)
| SRS 요구 | 레포 현황 | 갭 |
|---|---|---|
| F-01/06 비동기 grab+추론, <100ms | `aria/inspection/async_pipeline.py`(비병목) | tact 예산·트리거 동기 지표 노출 |
| F-05/06 정상만 학습+추론 | `aria/perception/cmdiad_inference.py`(PatchCore)+`threshold_calibrator` | 신제품 학습 HMI 버튼 흐름 |
| F-07 후처리(형태학·blob) | min_val 맵 존재 | blob→면적/중심 추출 정형화 |
| **F-08 2D(u,v)→3D(x,y,z) 변환** | VisionBooth+raycast 경로(부분) | **캘리브 변환 정형화 + decal/레이저 투영** |
| I-01 PLC(OPC UA/Modbus/TCP) | `aria/inspection/twin_bridge.py`(OPC UA/MQTT) | Modbus 어댑터(필요시) |
| I-02 합성데이터/트윈 연동 | `aria/simulation/{defects,dataset}.py`+`sim/randomization.js` | 가상시운전 대시보드(Zero-Trial) |
| **I-03 연속불량→SLM 예지보전** | 에이전트/VLM(`agents/vision_agent`)+`event_bus`+`core/database` | **결함 패턴 집계→가설 진단** |
| 자기개선/MLOps | `aria/learning/self_improvement_loop.py`,`model_scout` | 에피소드→평가 연결 |
| 다품종 혼류 | `products/`(dowel·foam·cable_gland·potato)+MVTec, `product_registry` | 셀 전환 시각화 |
| MPR 빈피킹/듀얼암 RL | `aria/robot/env`(MuJoCo, 격리 R&D) | 별도 트랙 유지 |
| 3D 스캐너 정렬·안전센서·SPOT | — | **하드웨어 — 범위 밖(개념/시뮬만)** |

→ 즉 **F-08, I-03, 가상시운전, tact SLA**가 "온스택 고가치 갭"이고 나머지는 대부분 있음.

---

## 2. Tier 0 — 토대 정리 (먼저, 싸게)
- ✅ **store 통합**(signalStore 단일화) — 직전에 완료(헤드리스 16/16).
- **HMI 셸 이중화 해소**: 구 셸(HmiShell 계열)↔신 슬롯(AppShell)을 AppShell로 단일화.
- **scene-as-data 포팅**: `factory_scene.json` 부재 → `sceneModel.js` 하드코딩 폴백. 선언적 씬으로 이전(다품종 셀 전환의 토대).

## 3. Tier 1 — 온스택 고가치 고도화 (핵심 4)

### T1-A. 2D→3D 좌표 변환 + 레이저/Decal 투영 (F-08) ★E-FOREST 시그니처
- heatmap peak (u,v) → (sim) VisionBooth 카메라 raycast / (real) 캘리브 K·[R|t] → 표면 (x,y,z).
- 트윈에 **레이저 마커/Decal**로 결함 위치 투사(현대차 '불량 지시 레이저 프로젝션'의 트윈판).
- 산출: `coordinate_transform`(u,v→xyz) + 기존 decal 역투영 명세 적용. **난수 금지, 데이터 유도.**

### T1-B. SLM식 예지보전 (I-03 / 제3파급) ★데이터 융합
- `event_bus`에 흐르는 `inspector_result`를 **시간·위치로 집계** → "동일 위치 N회 연속 NG" 패턴 감지
  → 에이전트가 **가설 진단**("해당 셀 로봇 관절 마모 의심", 신뢰도 표기, 확인 요망) 생성 → `database` 기록 + 승인 게이트.
- 재사용: `agents/vision_agent`(VLM 멀티모달), `orchestration/event_bus`, `core/database`. **원인 단정 금지(가설+신뢰도).**

### T1-C. 가상시운전/Sim-as-Data (Zero-Trial)
- `simulation/defects`+`randomization.js`를 **합성데이터 대시보드**로(조명·카메라·결함 무작위화→2D+자동 mask)
  → 신제품 CAD만으로 PatchCore 사전학습 → 물리 라인 전 검사 가중치 확보(제1파급 Zero-Trial).
- 산출: 기존 `ARIA_3D2D_Pipeline_Implementation_Spec`(M1) 구현.

### T1-D. Cycle-time SLA + PLC/OPC UA 하드닝 (F-02/NFR)
- `async_pipeline`에 **tact 예산(<100ms) + 트리거→ack 지표** 노출, `twin_bridge`로 OPC UA/MQTT 송출 강화.
- 통신 단절 시 로컬 버퍼→복구 시 batch upload(Fail-Safe, SPOT 이중화 원칙).

## 4. Tier 2 — 하드웨어 개념의 트윈 시각화(실물 아님)
- **다품종 AGV 셀 전환**: 제품별 라인 흐름·즉시배포(unsupervised) 시각화(트윈 데모).
- **MPR 듀얼암 빈피킹**: `aria/robot/env`(MuJoCo) **격리 R&D**로 유지 — 검사 파이프라인과 분리.
- **안전센서 퓨전 / SPOT PHM**: 개념 대시보드만(실 RGB/IR/열화상·로봇개는 하드웨어, 범위 밖).

## 5. Tier 3 — 하지 말 것
- ⛔ **C#/HALCON/WPF 전환**(스택 폐기). ⛔ 실 3D 스캐너/PLC/로봇개 하드웨어 통합. ⛔ 실 로봇 물리제어.
  ⛔ verdict(anomaly score) 로직 변경. ⛔ 새 ws/MCP 추론서버(기존 단일 경로 유지).

---

## 6. 권장 우선순위 (한 줄)
**Tier 0(셸 통합·scene-as-data) → T1-A(2D→3D 투영) → T1-B(예지보전) → T1-C(Zero-Trial) → T1-D(SLA).**
A는 E-FOREST의 가장 상징적 기능이자 이미 부분 구현(가장 빠른 임팩트), B는 데이터 융합으로 "검사기→두뇌" 격상,
C는 신제품 즉시 대응, D는 현장 신뢰성. 하드웨어부(Tier 2/3)는 시각화/격리로만.

> 각 항목은 원하면 레포 파일 기준 **빌드 명세 + Claude Code 미션 브리프**로 상세화 가능.
