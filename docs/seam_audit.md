# T2-A 시임 감사(Seam Audit) — 실제 코드 표면 인벤토리

> 작성 기준: 코드 실측(2026-07-01). 가정 없음. 검증된 것만 기재.
> T1-B 교훈: 문서 스펙에 있다고 구현이 있는 게 아니다.

---

## 0. 현황 요약

| 항목 | 실측 |
|---|---|
| 생산 경로 | **레거시 `app.py`(:8080)** `start_aria.sh`가 기동. B5 컷오버 미완료. |
| 신규 경로 | `server/app.py`(:8200) — 프론트 dev(Vite proxy)가 연결. 라우터 분리됨. |
| T2A 대상 | **`server/`(:8200)** — 이미 라우터 분리됨. TwinState·설정·컨텍스트 없음. |
| WS 채널 | `/ws/chat` **단 하나**. `/ws/floor`·`/ws/scan` 미존재. |
| 프로세스 | 단일 uvicorn. 3평면 분리 전(프로세스 토폴로지 변경 = S3). |

---

## 1. WS 채널 실측

| 경로 | 파일 | 용도 | 평면 |
|---|---|---|---|
| `/ws/chat` | `server/app.py:31` | 프론트 signalStore 단일 구독 | **게이트웨이** |

> `/ws/floor`, `/ws/scan` = **미존재**. 문서 스펙에서 가정 금지.

---

## 2. HTTP 엔드포인트 (server/ 기준)

| 경로 | 파일:라인 | 평면 |
|---|---|---|
| `GET /api/health` | `server/app.py:25` | 게이트웨이 |
| `GET /api/state` | `server/routers/state.py:26` | 트윈 상태 |
| `GET /api/hardware` | `server/routers/state.py:32` | 트윈 상태 |
| `GET /api/agents/status` | `server/routers/state.py:41` | 트윈 상태 |
| `POST /api/action` | `server/routers/state.py:47` | 게이트웨이(제어) |
| `POST /api/inspector/start` | `server/routers/inspector.py:112` | 검사 노드 |
| `POST /api/inspector/stop` | `server/routers/inspector.py:226` | 검사 노드 |
| `POST /api/inspector/start_lanes` | `server/routers/inspector.py:243` | 검사 노드 |
| `POST /api/inspector/stop_lanes` | `server/routers/inspector.py:330` | 검사 노드 |
| `POST /api/inspector/set_latency` | `server/routers/inspector.py:336` | 검사 노드 |
| `GET /api/inspector/state` | `server/routers/inspector.py:348` | 트윈 상태 |
| `GET /api/inspector/history` | `server/routers/inspector.py:363` | 트윈 상태 |
| `GET /api/inspector/health_history` | `server/routers/inspector.py:371` | 트윈 상태 |
| `POST /api/analyze_path` | `server/routers/analyze.py:16` | 검사 노드 |
| `POST /api/analyze` | `server/routers/analyze.py:39` | 검사 노드 |
| `POST /api/class/train` | `server/routers/classes.py:20` | 검사 노드 |
| `GET /api/classes/status` | `server/routers/classes.py:54` | 트윈 상태 |
| `POST /api/class/validate` | `server/routers/classes.py:66` | 검사 노드 |
| `GET /api/mvtec/scan` | `server/routers/classes.py:88` | 검사 노드 |
| `GET /api/class/samples` | `server/routers/classes.py:100` | 검사 노드 |
| `GET /api/image` | `server/routers/classes.py:124` | 트윈 상태 |
| `GET /api/result/{filename}` | `server/routers/classes.py:133` | 트윈 상태 |
| `POST /api/dataset/intake` | `server/routers/dataset.py:17` | 검사 노드 |
| `POST /sim/dataset` | `server/routers/sim.py:19` | 검사 노드 |
| `POST /sim/train` | `server/routers/sim.py:32` | 검사 노드 |
| `POST /sim/validate` | `server/routers/sim.py:68` | 검사 노드 |

---

## 3. 전역 상태 (server/ 내) — 읽기/쓰기 지점

| 변수 | 파일:라인 | 읽기 | 쓰기 | 평면 |
|---|---|---|---|---|
| `inspector._run` | `inspector.py:16` | start/stop/state | start/stop/trigger_loop | 검사 노드 |
| `inspector._lanes` | `inspector.py:17` | start_lanes/stop_lanes | start_lanes/stop_lanes/lane_worker | 검사 노드 |
| `inspector._infer_lock` | `inspector.py:18` | lane_worker | — | 검사 노드 |
| `state._agent` | `state.py:15` | get_state | action(emergency_stop/resume) | 트윈 상태 |

**교차 의존**:
- `state.py:47` `POST /api/action`이 `inspector._run`을 직접 조작(emergency_stop) → **평면 경계 위반**.
  이것이 S2에서 제거할 의존. `action` → TwinState를 통해 인스펙터에 신호.

---

## 4. 하드코딩 (S1에서 외부화 대상)

| 값 | 파일:라인 | 의미 | config 키 |
|---|---|---|---|
| `tau=0.5` | inspector.py:122, 251; analyze.py:21, 40 | 이상 임계치 기본값 | `inference.tau_default` |
| `queue_capacity=4` | inspector.py:285 (lanes) | 백프레셔 큐 깊이 | `inference.queue_depth` |
| `n_workers=1` | inspector.py:285 | 추론 워커 수 | `inference.n_workers` |
| `line_hz=6.0` | inspector.py:250 (lanes) | 레인 투입 속도 | `inference.lane_hz` |
| `line_hz=20.0` | inspector.py:125 (single) | 단일 투입 속도 | `inference.single_hz` |
| `hz=5.0` | inspector.py:169 (single pump) | 상태 펌프 주기 | `inference.state_pump_hz` |
| `hz=4.0` | inspector.py:288 (lane pump) | 레인 펌프 주기 | `inference.lane_pump_hz` |
| `conf=0.25` | inspector.py:75, 140 | YOLO 신뢰도 임계 | `inference.yolo_conf` |
| `interval=5.0` | inspector.py:43 (pdm_fusion) | PdM 융합 주기 | `pdm.fusion_interval_s` |
| `threshold=0.5` | state.py:15 | _agent 초기 tau | `inference.tau_default` |

> **레거시 `app.py`의 `THRESHOLD=15.0`** = CCIFPS 시대 유물. `server/`에는 존재하지 않음. S1 범위 밖.

---

## 5. 백그라운드 루프

| 루프 | 파일 | 기동 시점 | 평면 |
|---|---|---|---|
| `_trigger_loop` (Thread) | inspector.py:174 | POST /start | 검사 노드 |
| `lane_worker×N` (Thread) | inspector.py:263 | POST /start_lanes | 검사 노드 |
| state_pump | twin_bridge.py | pipe.start() | 검사 노드→트윈 상태 feed |
| pdm_fusion 서비스 | pdm_fusion.py | _ensure_fusion() | 트윈 상태 인접 |
| event_bus | event_bus.py | startup_event | 공유 인프라 |

---

## 6. 외부 의존

| 의존 | 상태 | 주의 |
|---|---|---|
| `AutonomousAgent`/`MCPClient` | `app.py`(레거시)에만 존재. `server/`에 없음. | T2A 범위 밖 |
| `/video_feed`(MJPEG/camera) | `app.py`(레거시)에만 존재. `server/`에 없음. | T2A 범위 밖 |
| `event_bus` | `server/`에서 기동(startup 없음 — 라우터가 직접 호출) | S2에서 정리 |
| `hardware.monitor` | `state.py:32` GET /api/hardware | 트윈 상태 평면 |

---

## 7. 감사 결론 — S1 착수 조건

- [x] WS 채널 1:1 확인(`/ws/chat` 단일)
- [x] 전역 상태 4개 전수(`_run`, `_lanes`, `_infer_lock`, `_agent`)
- [x] 교차 의존 1건 식별(`state.py` → `inspector._run` 직접 조작)
- [x] 하드코딩 10건 목록화(S1 외부화 대상)
- [x] 레거시 `app.py`·`start_aria.sh` B5 컷오버 미완료 확인

**S1 착수 가능**: 프로세스 토폴로지 안 건드리고 `aria/core/config.py`·`aria/core/context.py` 신규 추가 후 inspector/analyze에서 import. 무회귀.
