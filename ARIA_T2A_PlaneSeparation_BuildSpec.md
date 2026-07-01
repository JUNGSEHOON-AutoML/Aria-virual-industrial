# T2-A 빌드 명세 — 평면 분리(3-split) + 설정 외부화 + SKU/시프트 컨텍스트

> 한 줄: `app.py`가 **추론 파이프라인·전역 상태·WS 스트리밍·제어·UI 서빙**을 한 프로세스에 융합해 둔 것을
> **검사 노드 / 트윈 상태 서비스 / 게이트웨이** 3평면으로 가른다. 동시에 `THRESHOLD=15.0` 등 하드코딩을 코드 밖으로 빼고
> **SKU·시프트 컨텍스트**를 세워, 이후 24h 라이프사이클과 HIL 경계의 공통 전제를 만든다.
>
> ⛔ 가드레일(리팩터): **동작 보존(behavior-preserving)** — verdict·수율/OEE·PdM·UI **무회귀** · **새 WS 타입 없음**(전송 계약 유지) ·
> 하드코딩 제거(설정은 env/yaml) · **전역 dict/Lock 제거**(TwinState 단일 진실원) · **각 스테이지 독립 배포·게이트**(빅뱅 금지) ·
> 프로세스 간 전송은 **인터페이스 뒤**(이번엔 로컬 버스, OPC UA/MQTT/NATS는 HIL 트랙) · **검증 안 된 엔드포인트/WS 존재 가정 금지**(Stage 0 감사 선행).

---

## 0. 실제 현황 (보고 기준 · 확인됨 vs 검증필요)

> ⚠️ T1-B 교훈: 문서 스펙에 있다고 구현이 있는 게 아니다. **확인된 것만 재사용 대상**으로 두고, 나머지는 Stage 0에서 실측한다.

**확인됨 (읽은 `app.py` + 완료 보고 기준)**
| 요소 | 현황 |
|---|---|
| 프로세스 | 단일 FastAPI(`uvicorn app:app`) |
| 전역 상태 | `agent_state`(dict)+`state_lock`(threading.Lock), `latest_stats`, `agent_status_cache` |
| 하드코딩 | `THRESHOLD=15.0`, `MEMORY_BANK_PATH` 해석, `CORS_ORIGINS`, 스냅샷 간격 ~2s |
| 엔드포인트 | `/video_feed`(MJPEG), `/api/state`, `/api/action`, `GET /api/inspector/history`, `/health_history` |
| 마운트 | `/static`, `/uploads`, `/assets`, `frontend/dist` |
| DB | `aria/core/database.py`(analysis_history·agent_memory) + `timeseries`(metrics_ts·asset_health_ts) |
| 시계열/PdM | `record`/`recent`·`record_health`/`recent_health`, `asset_proxy.py`(결정론), `health_features`·`rul_estimator`·`pdm_fusion`(독립 서비스) |
| 이벤트 버스 | `aria/orchestration/event_bus.py` |

**검증필요 (Stage 0에서 실측 — 가정 금지)**
- WS 채널 실제 목록/사용처(`/ws/chat`·`/ws/scan`·`/ws/floor` 존재·활성 여부).
- `AutonomousAgent`/`MCPClient`가 전역 상태를 만지는 지점.
- 카메라/`patchcore_engine` 호출 경로(현재 `/video_feed` 루프 안인지, 별도 러너인지).
- `pdm_fusion`이 실제로 소비하는 입력(보고: `recent()` + 주입식 publish/NG feed).

---

## 1. 목표 3-plane 계약

| 평면 | 책임 | 소유 | 노출 |
|---|---|---|---|
| **검사 노드** `inspection_node` | 취득→추론(PatchCore)→판정→`inspector_result`·telemetry 생산 | 카메라·모델·τ·큐/백프레셔 | (전송) `inspector_result`, `metrics/health` |
| **트윈 상태** `twin_state` | 이벤트 리듀스 → **현재+이력 단일 진실원**; 시계열 소유; 읽기 서빙; `pdm_fusion` 인접 | metrics_ts·asset_health_ts·current state | `GET history`·`health_history`·state read |
| **게이트웨이** `gateway` | 정적 서빙·WS 팬아웃·`/api/action`(제어·승인) 포워딩 | 세션·소켓 | UI·WS·action |

> 규칙: **상태는 오직 `twin_state`가 소유**한다. 게이트웨이·검사 노드는 상태를 *만들지* 않고 전송·조회만 한다.
> `agent_state`/`state_lock`/`latest_stats` 전역 뮤터블은 제거되고 그 자리를 `twin_state`가 대신한다.

---

## 2. Stage 0 — 시임 감사 (seam audit · 리팩터 선행)

코드 손대기 전에 **실제 표면을 인벤토리**한다(가정 금지). 산출: `docs/seam_audit.md`.
- 전 엔드포인트·WS 채널·백그라운드 루프(취득/추론/스냅샷) 목록화.
- 전역 상태 **읽기/쓰기 지점** 전수 grep(`agent_state`·`state_lock`·`latest_stats`·`agent_status_cache`).
- 각 지점을 3평면 중 하나로 라벨링(검사/상태/게이트웨이).
- **게이트**: 감사 문서가 실제 코드와 1:1 대응(누락 0). 이후 스테이지는 이 문서만 근거로 진행.

---

## 3. Stage 1 — 설정 외부화 + ProductionContext (독립·저위험)

**설정 모듈** `aria/core/config.py`(신규): env→yaml→기본값 우선순위. `THRESHOLD`·포트·CORS·스냅샷 간격·백프레셔 큐깊이·카테고리별 τ(calibrator)를 여기로.
```
config.threshold(category, ctx)   # 하드코딩 15.0 제거
config.snapshot_interval_s        # ~2s
config.backpressure.queue_depth
```
**컨텍스트** `aria/core/context.py`(신규): `ProductionContext{sku, shift, tau_by_category, takt, recipe}`. τ·takt를 **SKU·시프트로 스코프**.
- 게이트: `grep THRESHOLD`·매직넘버 0건; env로 τ 바꾸면 즉시 반영; SKU 전환 시 스코프 τ 적용.
- **왜 먼저**: 프로세스 토폴로지 안 건드리고 landable. 24h 라이프사이클·HIL의 공통 전제.

---

## 4. Stage 2 — 인프로세스 경계화 (전역 제거 → 단일 진실원)

프로세스는 아직 하나. **경계만 인터페이스 뒤로**, 공유 뮤터블 제거.
- `twin_state`를 **단일 상태 소유자**로 세우고 `agent_state`/`state_lock`/`latest_stats` 전역을 그 리드/라이트로 대체.
- 검사 산출은 `inspection_node`가 이벤트로 `twin_state`에 **feed**(직접 dict 조작 금지).
- 게이트웨이 엔드포인트·WS는 `twin_state` **조회**로만 응답(전송 계약·페이로드 불변).
- 게이트: 전역 상태 grep 0건; **골든 트레이스 무회귀**(§8-1); UI 동일.

---

## 5. Stage 3 — 프로세스 분리 + 슈퍼비전/복원

세 평면을 **별도 기동**. 전송은 인터페이스 뒤(이번엔 로컬 버스; OPC UA/MQTT/NATS는 HIL 트랙에서 교체).
- `event_bus`를 인프로세스 큐 → **프로세스 간 전송 인터페이스**로 승격(어댑터 경계만; 구현은 로컬).
- **슈퍼비전**: `docker-compose`/`supervisord`/systemd로 3서비스 감시·자동 재기동, health/liveness.
- **복원**: `twin_state` 재기동 시 이벤트 로그/시계열에서 현재 상태 재구성(②의 복원 성질 재사용).
- **staleness 정직성**: 소스 끊기면 트윈은 "마지막값 + 경과시간" 표시, **값 지어내지 않음**.
- 게이트: 검사 노드 크래시에도 게이트웨이/트윈 생존; 재기동 후 상태 복원; UI에 stale 배지.

---

## 6. 파일 산출물

### 백엔드
| 파일 | 신규/수정 | 내용 |
|---|---|---|
| `docs/seam_audit.md` | **신규** | Stage 0 인벤토리(근거 문서). |
| `aria/core/config.py` | **신규** | env/yaml 설정·τ·간격·백프레셔. 하드코딩 제거. |
| `aria/core/context.py` | **신규** | `ProductionContext`(SKU/시프트 스코프 τ·takt·recipe). |
| `aria/planes/inspection_node.py` | **신규** | 취득+PatchCore+판정 → `inspector_result`/telemetry 생산(현 video/추론 루프 이관). |
| `aria/planes/twin_state.py` | **신규** | 이벤트 리듀스 → 현재+이력 단일 진실원; 시계열 소유; history 서빙; `pdm_fusion` 인접. |
| `app.py` | 수정(얇게) | **게이트웨이만**: 정적·WS 팬아웃·`/api/action` 포워딩. 전역 dict/Lock 삭제. |
| `aria/orchestration/event_bus.py` | 수정 | 인프로세스 큐 → 프로세스 간 전송 인터페이스(어댑터 경계). |
| `docker-compose.yml`·`start_aria*.sh` | 수정 | 3서비스 기동·슈퍼비전·health. |
| `aria/core/database.py` | 유지 | analysis_history·agent_memory·timeseries 그대로. |

### 프론트 (동작 보존 · 최소 변경)
| 파일 | 신규/수정 | 내용 |
|---|---|---|
| `apiClient.js` | 수정(경량) | base URL 설정화(게이트웨이 단일 진입). 계약·시그니처 불변. |
| `signalStore.js` | 확인 | 게이트웨이 경유로 동일 상태 수신(무회귀). |

---

## 7. 안전 / 거버넌스 (동작 보존)
- **무회귀 최우선**: verdict·수율/OEE·HOLD·PdM·UI가 분리 전후 동일해야 착수 완료로 인정.
- 새 WS 타입/페이로드 변경 금지(전송 계약 유지). 프론트는 엔드포인트 base만 설정화.
- 설정은 코드 밖. 상태는 `twin_state`만 소유(전역 뮤터블 부활 금지).
- 각 스테이지는 **독립적으로 롤백 가능**해야 한다(빅뱅·되돌릴 수 없는 변경 금지).

---

## 8. 검증 게이트 (본인 확인)
1. **골든 트레이스 무회귀**: 고정 입력 세트 → 분리 전/후 동일 verdict·OEE·PdM 출력(diff 0).
2. **설정 외부화**: `grep -R "15.0\|THRESHOLD ="` 0건; env로 τ 변경 시 반영.
3. **컨텍스트**: SKU/시프트 전환 시 스코프 τ·takt 적용.
4. **단일 진실원**: `agent_state`/`state_lock`/`latest_stats` grep 0건; 모든 상태 `twin_state` 경유.
5. **프로세스 분리**: inspection_node·twin_state·gateway 개별 기동; 한 프로세스 종료에도 나머지 생존.
6. **복원**: twin_state 재기동 → 이벤트/시계열에서 현재 상태 재구성.
7. **staleness**: 검사 노드 정지 시 UI가 last-known+경과 표시(값 위조 없음).

---

## 9. 단계 + 런타임 게이트
- **S0 감사** — `seam_audit.md`. 게이트: 코드 1:1 대응.
- **S1 설정/컨텍스트** — config.py·context.py. 게이트: 하드코딩 0·τ env반영·SKU스코프.
- **S2 경계화** — twin_state 단일 진실원, 전역 제거. 게이트: grep 0·골든 무회귀.
- **S3 분리** — 3프로세스·슈퍼비전·복원. 게이트: 개별 기동·크래시 격리·재기동 복원·stale 배지.

---

## 10. 다음 트랙 연결
- **24h 라이프사이클**: `context.py`의 SKU/시프트 스코프 + `health_features`(T1-C)를 그대로 써서 시프트별 τ·드리프트 감시·롤링 FAT.
- **HIL 경계**: Stage 3의 **전송 인터페이스에 OPC UA/MQTT 어댑터를 꽂으면** 자산만 가상인 실배포 동형 트윈(평면이 갈렸으므로 경계가 깨끗함).

---

## 11. Claude Code 미션 브리프 (그대로 전달)
```
목표: app.py를 검사 노드 / 트윈 상태 / 게이트웨이 3평면으로 분리 + 설정 외부화 + SKU/시프트 컨텍스트.
불변(동작 보존): verdict·수율/OEE·HOLD·PdM·UI 무회귀 · 새 WS 타입 없음 · 전역 dict/Lock 제거(twin_state 단일 진실원) · 하드코딩 제거.
선행: Stage 0 시임 감사(seam_audit.md) — 문서 스펙 아닌 실제 코드 표면만 근거. 검증 안 된 엔드포인트/WS 가정 금지.
순서: S0 감사 → S1 설정/컨텍스트 → S2 경계화(전역 제거·골든 무회귀) → S3 프로세스 분리(슈퍼비전·복원·stale).
전송: 프로세스 간은 인터페이스 뒤(이번엔 로컬 버스). OPC UA/MQTT는 HIL 트랙에서 어댑터로 교체.
검증: §8 게이트 7종 + 골든 트레이스 diff 0.
```
