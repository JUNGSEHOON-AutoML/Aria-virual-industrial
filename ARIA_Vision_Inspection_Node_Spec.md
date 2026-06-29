# ARIA Vision Inspection Node — Claude Code 설계 명세 (Digital-Twin 연동)

> **한 줄** — MVTec AD(PatchCore) 비전검사기를 *독립 프로그램*이 아니라, **상위 디지털 트윈/시뮬레이터에
> 텔레메트리로 연동되며 라인 병목을 만들지 않는 "지능형 검사 노드"** 로 설계한다.
>
> **재시작 아님** — 추론·이상맵·메트릭은 기존 ARIA(`patchcore_engine`, `/ws/scan`, `floor_runner`, scene-as-data)를
> 그대로 쓰고, 여기에 **(1) 비병목 비동기 파이프라인 (2) 상위 연동 브리지(OPC UA/MQTT)** 두 레이어만 더한다.

---

## 1. 맥락 정합 (참조 4건 → 우리 노드의 책임)
- Siemens(Tecnomatix)·DFX(S-prodis): 가상에서 **레이아웃·병목·Capa 사전검증**. → 검사 노드는 자기 **tact-time/병목 지표를 상위로 노출**해야 함.
- 유튜브 As-Is/To-Be(인탑스·원바이오젠): **리드타임·동선·재공 감소**. → 검사 공정이 라인 리드타임을 늘리면 안 됨(비병목 설계).
- UBC OCTOPUS: 현장 데이터 **실시간 연동 + 통합 모니터링 + AI 자율 의사결정**. → 노드는 **표준 프로토콜로 상태/결과를 실시간 송출**.

→ 책임 3가지: **① 병목 안 만들기 ② 상위 트윈과 실시간 연동 ③ 결과/상태 데이터의 표준화.**

---

## 2. 아키텍처 (모듈)
```
        ┌───────────── Vision Inspection Node (Python core) ─────────────┐
 PLC ──▶│ Trigger ─▶ [Acquisition thread] ─▶ Bounded Queue(Q) ─▶ [Inference workers] │
 (DI/   │   ack            (camera grab)        │ backpressure      (PatchCore.run)    │
 OPCUA) │                                       ▼                         │           │
        │                              Decision(τ, calibrator) ─▶ Result + Heatmap     │
        │                                       │                         │           │
        │   ┌── Telemetry Bus ──┐               ▼                         ▼           │
        │   │ OPC UA server     │◀──── state/result/tact/score ──── Result/IO          │
        │   │ MQTT publisher    │                                  (NG reject signal)   │
        │   └───────────────────┘                                                      │
        └──────────────┬─────────────────────────────────────────────┬────────────────┘
                       ▼                                               ▼
            상위 디지털 트윈/MES                                 ARIA HMI + /ws/floor
        (Siemens PlantSim / OCTOPUS)                       (scene-as-data 트윈, 우리 것)
```
> 같은 텔레메트리가 **외부 트윈(OPC UA/MQTT)** 과 **내부 데모 트윈(/ws/floor)** 양쪽으로 흐른다.

---

## 3. ★ 비병목 비동기 설계 (이 명세의 알맹이)
검사 속도가 라인 인입 속도를 못 따라가도 **라인을 멈추지 않도록** 분리·완충한다.

- **스레드/태스크 분리**: `Acquisition`(트리거→grab→enqueue)과 `Inference`(dequeue→run→decide)를 분리. 트리거 **ack는 grab 직후 즉시** 반환(추론 대기 금지).
- **Bounded Queue(Q)**: 깊이 Q(예: 4). 생산자=grab, 소비자=추론 워커(GPU 배치 가능).
- **Tact 예산 T_takt**: 추론 p95 latency < T_takt 유지가 목표. 측정값 `infer_latency`, `tact_time` 노출.
- **Backpressure 정책(필수 명시)**: 큐 만재 시 ①**drop-oldest** + `drop_count`++ + 해당 파트 `SKIPPED` 플래그(보수적으로 수동검사 라우팅), 또는 ②트윈 연동 시 **상위에 conveyor slow-down 신호**.
- **노출 지표**: `tact_time, infer_latency, queue_depth, drop_count, state(Idle/Run/Down)` → 상위가 병목을 인지·재조정(참조의 "병목 해소" 정합).
- **격리**: 추론 예외/타임아웃이 acquisition·telemetry 루프를 죽이지 않음(워커 격리 + 슈퍼바이저 재기동).

---

## 4. 검사 파이프라인 상태머신
```
IDLE ─(trigger)→ GRAB ─→ ENQUEUE ─(ack)→ IDLE      // acquisition (즉시 복귀)
QUEUE ─(worker)→ PREPROCESS → INFER(PatchCore.run) → DECIDE(score>τ?)
       → RESULT(DB저장 + heatmap) → IO(NG면 reject 신호) → TELEMETRY(publish)
오류: INFER timeout/err → worker restart, 파트=ERROR, telemetry 계속
```
- `τ`는 카테고리별 calibrator 값(이미지 판정). heatmap=PatchCore anomaly map(min_val).

---

## 5. 상위 연동 데이터 계약
### 5.1 OPC UA (서버를 노드에 둠 — MES/PlantSim이 browse/subscribe)
```
Object: Inspector/<id>
  State:String  LastResult:String(OK|NG|SKIPPED|ERROR)
  AnomalyScore:Double  Threshold:Double  PartId:String
  TactTime:Double(ms)  InferLatency:Double(ms)  QueueDepth:Int32  DropCount:Int32
  YieldRate:Double  HeatmapUrl:String
Methods: Trigger()  Reset()  SetThreshold(Double)
```
### 5.2 MQTT (경량 텔레메트리 → SaaS 트윈/대시보드)
```
PUB aria/inspector/<id>/result  {part_id,verdict,score,tau,tact_ms,latency_ms,ts}
PUB aria/inspector/<id>/state   {state,queue_depth,drop_count,yield,ts}
PUB aria/inspector/<id>/heatmap {url|b64} (retained)
SUB aria/inspector/<id>/cmd     {action:"trigger|reset|set_threshold", value?}
```
> SECS/GEM은 **반도체 라인일 때만** 어댑터 추가(기본 범위 밖).

---

## 6. 기술 스택 (정직한 권고)
- **추론 코어: Python** (PatchCore/torch와 정합). `patchcore_engine.run()` 재사용.
- **카메라**: GenICam/GigE Vision → `harvesters`(Python) 또는 벤더 SDK. `AcquisitionDriver` 인터페이스로 추상화(+ **MockDriver**로 카메라 없이 개발).
- **브리지**: OPC UA=`asyncua`(서버), MQTT=`paho-mqtt`/`asyncio-mqtt`.
- **HMI**: **웹(React, ARIA 대시보드 재사용)** 권장. .NET 비전 샵이면 C#/WPF HMI만 옵션.
- ⚠️ Gemini 종합의 "C#/Python/C++ 택1"은 **코어=Python 단일**로 고정. 언어 분산 금지(유지보수 비용).

---

## 7. ARIA 재사용 맵
| 기능 | 재사용 |
|---|---|
| 추론/이상맵 | `patchcore_engine.run()` → score + min_val(heatmap) |
| 임계값 τ | `threshold_calibrator` / `floor_thresholds.json` |
| 내부 트윈 메트릭 | `floor_runner` → `/ws/floor` |
| 3D 검사 시각화 | `/ws/scan` + relief 뷰어 |
| 공장 선언 | `factory_scene.json` (scene-as-data) |
| **신규** | `async_pipeline.py`(§3) + `twin_bridge.py`(OPC UA/MQTT, §5) |

---

## 8. HMI / 모니터링
실시간 양품률(Yield), tact-time 추세, **anomaly heatmap(불량 위치)**, NG 갤러리, 노드 상태(Idle/Run/Down), queue/drop 게이지. (작업자 즉시 판독)

## 9. 비기능 요구
- Tact SLA: 트리거→ack < 20ms(추론 부하 무관). 추론 p95 < T_takt.
- 가용성: 추론 워커 죽어도 노드 생존(슈퍼바이저). 텔레메트리 끊김 시 로컬 버퍼링.
- 로깅: 결과/이미지/heatmap + 메트릭 시계열(DB).

---

## 10. 수용 기준 (런타임 검증)
1. **비병목**: 추론 latency를 인위로 5× 늘려도 트리거 ack·다음 grab 지연 없음(drop_count만 증가).
2. **Backpressure**: 과부하 시 crash 없이 drop/SKIPPED 처리 + 텔레메트리 지속.
3. **연동**: OPC UA browse로 노드값 갱신 확인 + MQTT 구독자가 result/state 수신.
4. **추론**: 알려진 NG 이미지 score>τ + heatmap이 ground_truth 위치와 일치, OK는 pass.
5. **트윈 동시 송출**: 동일 텔레메트리가 `/ws/floor`(내부)와 MQTT(외부) 양쪽에 도달.

---

## 11. Claude Code 미션 브리프 (그대로 전달)
```
[MISSION] ARIA(PatchCore) 비전검사기를 '디지털트윈 연동 + 비병목 검사 노드'로 구현하라.
독립 프로그램이 아니라 기존 patchcore_engine.run()/threshold/heatmap 를 재사용하고,
두 레이어만 신설: (1) 비동기 비병목 파이프라인 (2) OPC UA/MQTT 텔레메트리 브리지.

[BUILD]
- async_pipeline.py: Acquisition(트리거→grab→enqueue, ack 즉시) / Inference 워커 분리 +
  Bounded Queue(Q=4) + backpressure(drop-oldest,+drop_count,SKIPPED) + tact/latency/queue/drop 지표.
  AcquisitionDriver 인터페이스 + MockDriver(카메라 없이 동작).
- decision: score>τ(calibrator) → OK/NG, heatmap=min_val.
- twin_bridge.py: asyncua 서버(§5.1 노드/메서드) + paho-mqtt 퍼블리셔(§5.2 토픽).
  동일 텔레메트리를 /ws/floor 로도 송출.
- result_io: DB 저장 + NG reject 신호(디지털 IO/OPC UA 메서드).
- HMI: 웹(React) — yield/tact/heatmap/NG갤러리/queue·drop 게이지.

[STACK] 코어=Python 단일. OPC UA=asyncua, MQTT=paho-mqtt. 언어 분산 금지.
[DON'T] 추론 알고리즘 재작성 금지(patchcore_engine 재사용). SECS/GEM 도입 금지(반도체 아님).
        동기 블로킹 파이프라인 금지(병목 유발).
[DONE WHEN] §10 수용기준 1~5 런타임 충족(특히 1: 비병목 증명).
```

---

## 12. Gemini 종합 대비 보정 요약
- 언어: C#/C++/Python 혼재 → **Python 코어 단일** + 얇은 브리지/HMI.
- 프로토콜: SECS/GEM(조건부) 제외, **OPC UA + MQTT** 기본.
- ②번(비동기)을 **명세의 1순위**로 격상 — tact 예산·backpressure·격리까지 구체화.
- "독립 검사기" → ARIA 재사용 + 내부/외부 트윈 **동시 연동**.
