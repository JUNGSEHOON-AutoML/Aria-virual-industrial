# S3b 감사(Seam Audit) — 생산자 이관 대상 · 복원 필드 · 헬스 실측

> 작성 기준: 코드 실측 (2026-07-01). 가정 없음. 검증된 것만 기재.
> T1-B·S0 교훈 적용: 스펙에 있다고 구현이 있는 게 아니다.

---

## 0. 현황 요약

| 항목 | 실측 |
|---|---|
| 진입점 | `start_aria.sh` → `server.app:app --port 8200` (단일, S3a 완료) |
| 상태 소유 | `aria/planes/twin_state.py` — `_run`·`_lanes`·`_agent` |
| 추론 워커 | `AsyncPipeline._worker` × n_workers 개 `threading.Thread` (daemon, in-process) |
| 취득 루프 | `_trigger_loop`·`lane_worker` 스레드 (daemon, in-process) |
| 텔레메트리 버스 | `TwinBridge + WsFloorSink` → `broadcast_threadsafe(loop, msg)` 인라인 콜백 |
| 시계열 | `aria/core/metrics_ts.db` (SQLite, P-producer가 직접 write 중) |
| `event_bus` | `aria/orchestration/event_bus.py` — **현재 server/ 코드에서 사용 안 됨**. asyncio 큐 구조만 존재. |
| IPC 현재 | **없음** — 모든 것이 단일 프로세스 내 스레드 콜백 |

---

## 1. P-producer 이관 대상 (실측)

### 1-1. 모델/뱅크 로딩 — 이관 필수

| 객체 | 로딩 시점 | 파일 | 실측 위치 |
|---|---|---|---|
| `PatchCoreDetector.__init__` | `POST /start` 또는 `lane_worker` 기동 시 | `banks/{category}.npy` → `np.load(bank)` | `aria/inspection/detectors.py:71` |
| `YoloDetector.__init__` | 동일 | `models/yolo/{category}.pt` → `YOLO(weights)` | `aria/inspection/detectors.py:104` |
| `CombinedDetector` | 위 두 개 조합 | — | `server/routers/inspector.py:74–77` |

> **P-producer 이관 시 경로 계약**: `BANKS_DIR`, `MODELS_DIR`는 현재 `server/config.py`에서 `ROOT/banks`, `ROOT/models`로 고정. P-producer가 다른 CWD에서 뜨면 경로 어긋남 → **S3b-1 골든 착수 전 환경 동일성 대조 필수**.

### 1-2. 추론·취득 스레드 — 이관 필수

| 구성요소 | 스레드/루틴 | 이관 이유 |
|---|---|---|
| `AsyncPipeline._worker()` × n_workers | daemon Thread | GPU·타임아웃·OOM의 주 사망 원인 |
| `MockDriver.grab()` | `_worker` 내 동기 호출 | 취득 계통 |
| `_trigger_loop` (단일레인) | daemon Thread | inspector.py 내부에서 시작 |
| `lane_worker` × lane_count (멀티레인) | daemon Thread | 동일 |
| `TwinBridge.start_state_pump` 스레드 | daemon Thread | 추론 스냅샷 펌프 |

### 1-3. 현재 P-producer → SQLite 직접 쓰기 — **S3b-1에서 격리 필요**

`_trigger_loop` / `lane_worker` 내 `timeseries.record()` + `_feed_health()` 호출이 **P-producer 스레드에서 직접 `metrics_ts.db`에 write**.

```
P-producer: timeseries.record(snap) → sqlite3.connect(TS_PATH).execute(INSERT)
```

프로세스 분리 후 두 프로세스가 동일 SQLite 파일에 접근하면 WAL 모드 없으면 충돌 위험.
→ S3b-1 설계: P-producer는 DB 직접 write 대신 **IPC push** → P-core가 받아서 write.

### 1-4. pdm_fusion NG 피드 — 이관 경계 주의

```python
_note_ng_if() → get_fusion().note_ng()  # P-producer 스레드에서 P-core 인접 싱글톤 직접 호출
```

`pdm_fusion`은 `recent_health()`(시계열)를 읽으므로 P-core 인접. P-producer가 직접 호출하는 구조를 **IPC 이벤트**(inspector_ng)로 교체해야 함.

---

## 2. P-core에 남을 것 (실측)

| 구성요소 | 근거 |
|---|---|
| `TwinState` (`aria/planes/twin_state.py`) | 이미 분리됨, 상태 단일 소유 |
| `timeseries` write (record 쪽) | IPC 수신 후 P-core가 기록 |
| `timeseries` read (recent, history) | 상태 재구성·history 서빙 |
| `pdm_fusion` 서비스 | `recent_health()` 읽기 — P-core 인접 |
| `manager.broadcast` / WS `/ws/chat` | 게이트웨이 역할, P-core 내 |
| `/api/*` 라우터 (inspector 제어 포함) | 제어 명령 수신 후 IPC로 P-producer에 전달 |
| `event_bus` (asyncio 큐) | S3b-1 IPC 어댑터로 활용 예정 |

---

## 3. TwinState 필드 복원 가능 / 휘발 분류

### `_run` (단일레인 실행 상태)

| 필드 | 분류 | 재기동 시 처리 |
|---|---|---|
| `running: bool` | 휘발 | **안전측 = False** (실행 중이 아님) |
| `pipe: AsyncPipeline` | 휘발 | None (스레드 객체) |
| `bridge: TwinBridge` | 휘발 | None |
| `mode: str` | 휘발 | stale 표기 |
| `category: str` | 휘발 | stale 표기 |
| `holder: dict` | 휘발 | — |
| `max_parts: int` | 휘발 | — |
| `trigger_thread: Thread` | 휘발 | None |

### `_lanes` (멀티레인 상태)

| 필드 | 분류 | 재기동 시 처리 |
|---|---|---|
| `running: bool` | 휘발 | **안전측 = False** |
| `threads: list` | 휘발 | [] |
| `rotation: list` | 휘발 | stale — 재시작 전까지 빈 레인 |
| `lane_count: int` | 휘발 | 0 |
| `mode: str` | 휘발 | stale |

### `_agent` (에이전트/게이트웨이 상태)

| 필드 | 분류 | 재기동 시 처리 |
|---|---|---|
| `status: str` | 시작값 복원 | "idle" (기본값) |
| `is_running: bool` | 복원 | True (정상 재기동) |
| `last_action: str\|None` | 휘발 수용 | None |
| `score: float` | 휘발 | 0.0 (P-producer 재연결 시 갱신) |
| `threshold: float` | config 복원 | `_cfg.tau_default` |

### 시계열에서 복원 가능한 집계

| 복원 대상 | 소스 | API |
|---|---|---|
| OEE · yield · quality · availability | `metrics_ts` | `timeseries.recent()` |
| 자산 건전성·RUL 입력 | `asset_health_ts` | `timeseries.recent_health()` |
| 활성 예지 가설 (쿨다운 포함) | `pdm_episode` | `timeseries.recent_episodes()` |
| 레인별 n_ok/n_ng/n_skipped | `metrics_ts` | `timeseries.recent(lane=N)` |

> **복원 불가** (재기동 시 stale로 시작):
> - 실행 중이던 파이프라인 내 미처리 프레임 (큐 내용)
> - 현재 검사 category/mode (P-producer 재연결 전까지 unknown)
> - 순간 추론 latency p95 (누적 후 재계산 필요)

---

## 4. `/api/health` 실측 및 S3b 요구사항

### 현재 구현
```python
@app.get("/api/health")
async def health():
    return {"ok": True, "service": "aria-api", "port": 8200,
            "routers": ["inspector", "sim", "class", "dataset", "analyze", "state"]}
```

**문제**: P-core의 존재만 확인. P-producer 생존 여부 · 마지막 inference tick · 시계열 DB 접근 여부 전혀 반영 안 됨.

### S3b 신설 healthcheck 계획

| 헬스 항목 | P-core 측정 | P-producer 측정 |
|---|---|---|
| liveness | 응답 자체 | 마지막 inference tick `< stale_threshold_s` |
| TwinState | `is_running()` 또는 `lanes_running()` | — |
| timeseries DB | `recent()` 결과 0 이상 | — |
| 연결 상태 | IPC 연결 ping | P-core IPC 소켓 응답 |

→ S3b-1에서 P-producer에 `/internal/health` (포트 8201 등) 신설.
→ P-core `/api/health`에 `producer_connected: bool`, `producer_last_seen_s: float` 추가.

---

## 5. event_bus 현재 상태 — IPC 어댑터 기반으로 활용 가능

`aria/orchestration/event_bus.py` (106줄):
- asyncio 기반 싱글톤, `subscribe(topic, handler)` + `publish(topic, data)` 패턴.
- **현재 `server/` 어디에서도 직접 사용되지 않음** (sim.py의 `publish`는 WS 직접 broadcast).
- 프로세스 간 전송은 구현 없음 — **asyncio 큐는 프로세스 내부 전용**.
- S3b-1에서 IPC 어댑터 경계로 활용: `event_bus.publish("inspector_result", data)` → HTTP POST to P-core.

---

## 6. SQLite 공유 경로 (두 프로세스 접근 위험)

| DB 파일 | 경로 | P-producer 접근 | P-core 접근 |
|---|---|---|---|
| `metrics_ts.db` | `aria/core/metrics_ts.db` | **write** (record, record_health) | **read** (recent, recent_health) |
| `argus_core.db` | `aria/core/argus_core.db` | — | read/write (분석 이력) |

**SQLite WAL 모드**: `sqlite3.connect` 시 `PRAGMA journal_mode=WAL` 미설정 → 두 프로세스 동시 write 충돌 가능.
→ S3b-1 결정: P-producer → IPC push → P-core가 단독 write (읽기 경합 없음).

---

## 7. 골든 환경 동일성 기준 (S3b-1 착수 전 대조)

| 항목 | 현재(단일 프로세스) | S3b-1(분리 후) 확인 포인트 |
|---|---|---|
| `BANKS_DIR` | `ROOT/banks` (`server/config.py`) | P-producer가 동일 경로를 볼 것 |
| `MODELS_DIR` | `ROOT/models` | 동일 |
| `TS_PATH` | `aria/core/metrics_ts.db` | P-core만 write, 경로 동일 |
| `ARIA_TAU` | 없음 (기본 0.5) | 양 프로세스 동일 env 필요 |
| `CWD` | `/userHome/userhome4/sehoon/ARIArefactored` | P-producer 기동 시 동일 CWD 보장 |
| Python | `miniconda3/envs/patchcore` | 양 프로세스 동일 인터프리터 |

---

## 8. 감사 결론 — S3b-1 착수 조건

- [x] P-producer 이관 대상 확인 (모델 로딩·추론 스레드·취득 루프·TwinBridge 펌프)
- [x] P-producer → SQLite 직접 write 문제 실측 (IPC로 교체 결정)
- [x] pdm_fusion NG 피드 경계 실측 (IPC 이벤트로 교체 필요)
- [x] TwinState 필드 복원/휘발 전수 분류
- [x] `/api/health` 한계 확인 (P-producer 미반영)
- [x] `event_bus` 현황 (사용 안 됨, IPC 어댑터 후보)
- [x] SQLite 공유 경로 위험 확인 (P-core 단독 write 결정)
- [x] 골든 환경 동일성 기준 수립

**S3b-1 착수 가능**: 아래 설계 결정 확정 후.
1. IPC 전송 기본 구현: P-producer → HTTP POST `/internal/ingest` (P-core) — Redis/NATS 없이.
2. P-producer 포트: `8201` (P-core: `8200`).
3. SQLite: P-core 단독 write (P-producer write 제거).
4. event_bus: IPC 어댑터 래퍼로 재활용.
