# T2-A · S3b 빌드 명세 — 물리 프로세스 격리 + 복원 + stale 정직성

> 한 줄: S2에서 **논리 3평면**은 갈렸고 S3a에서 레거시(:8080)를 은퇴했다. S3b는 **잘 죽는 생산자(카메라·추론)를
> 나머지(상태+게이트웨이)에서 물리적으로 격리**하고, 재기동 시 시계열에서 상태를 복원하며, 소스가 끊기면 값을
> 지어내지 않고 **last-known + 경과시간**을 표시한다. 이게 "24시간 생존"의 실체이자 HIL 경계의 전제.
>
> ⛔ 가드레일: **동작 보존** — verdict·수율/OEE·HOLD·PdM·UI **무회귀**(골든 diff 0) · 새 WS 타입/페이로드 변경 없음 ·
> 상태 소유자는 여전히 TwinState 하나 · 전송은 **인터페이스 뒤**(이번 기본=내부 HTTP/WS, Redis/NATS는 선택) ·
> **값 위조 금지**(끊기면 stale 표기) · 각 단계 독립 롤백 · 검증 안 된 것 가정 금지.

---

## 0. 현황 (S3a 완료 기준 · 확인 vs 검증필요)

**확인됨**
| 요소 | 현황 |
|---|---|
| 진입점 | `start_aria.sh` → `server.app:app --port 8200` (유일) |
| 상태 소유 | `aria/planes/twin_state.py` — `_run`·`_lanes`·`_agent` 단일 소유자, `emergency_stop()` 내부화 |
| 추론 락 | `_infer_lock` = 검사 평면 내부(승격 안 함) |
| 시계열 | `metrics_ts`·`asset_health_ts` + `record`/`recent`(재시작 복원 가능·②) |
| 골든 | `tests/golden_trace.py` + `golden.json`(3회 재현성) |
| 슈퍼비전 | `docker-compose.yml` :8200 · healthcheck `/api/health` |
| WS | `/ws/chat` 단 하나(S0 실측) |

**검증필요 (S3b-0에서 실측)**
- 카메라/`patchcore_engine`/memory_bank 로딩이 실제로 어느 코루틴/스레드에 사는지(생산자 프로세스로 이관 대상).
- TwinState `current state`의 필드 중 **시계열로 재구성 가능** vs **휘발(ephemeral)** 구분.
- `/api/health`가 프로세스별로 의미 있는 liveness를 주는지(아니면 서비스별 헬스 신설).

---

## 1. 물리 경계 결정 — 2프로세스(생산자 격리)

> **논리 3평면(S2 완료) ≠ 물리 3프로세스.** 신뢰성이 정당화하는 물리 경계는 하나뿐이다.

| 프로세스 | 포함 | 이유 |
|---|---|---|
| **P-producer** `inspection_node` | 카메라·PatchCore·판정·백프레셔·τ·memory_bank | **가장 잘 죽는/멈추는** 부분(하드웨어·GPU·타임아웃)을 격리 |
| **P-core** `twin_state + gateway` | 상태 단일 소유·시계열·history 서빙·WS 팬아웃·`/api/action`·`pdm_fusion` | 죽으면 어차피 서빙 불가 — 쪼갤 신뢰성 이득 없음 |

- 3프로세스(게이트웨이 별도)는 **UI 티어 독립 스케일이 필요할 때의 선택**. S3b 기본 아님.
- memory_bank·모델 로딩은 **P-producer로 이동** → 골든 환경 동일성(§9-1)에서 경로 대조 필수.

---

## 2. 전송 인터페이스 (event_bus 뒤 IPC)

- `event_bus`를 **프로세스 간 어댑터** 뒤로: 기본 구현은 **이미 있는 전송(내부 HTTP/WS)** — P-producer가 `inspector_result`·telemetry를 P-core의 내부 수신 엔드포인트로 push.
- Redis/NATS/ZeroMQ는 **선택 어댑터**(가정 금지, 이번 범위 밖).
- **페이로드 계약 불변**: 인프로세스 때와 동일 스키마 → 골든 무회귀 성립 조건.
- 연결 유실 대비 **로컬 버퍼(store-and-forward)** 를 P-producer에 두어, P-core 재기동 중에도 결과 유실 없이 재전송.

---

## 3. 복원 — TwinState 재기동 시 현재 상태 재구성

재기동 시 P-core는 **시계열 + 이벤트 로그**로 current state를 다시 세운다.
| 상태 | 복원 소스 | 비고 |
|---|---|---|
| lane OK/NG/HOLD 카운트·OEE 창 | `metrics_ts` recent() | ②의 복원 재사용 |
| 자산 건전성·RUL 입력 | `asset_health_ts` recent() | T1-C 특징 재계산 |
| 활성 예지 가설 | 최근 `pdm_episode` | 쿨다운 상태 포함 |
| 진행 중 `_run`/`_lanes` 토글 | 마지막 기록 상태 or 안전 기본(정지) | **휘발 시 안전측으로** |
- 재구성 불가한 순간값은 **stale로 시작**(가짜 초기화 금지).

---

## 4. stale 정직성

- TwinState가 **소스별 `last_update_ts`** 유지. `now - last_update > config.stale_threshold_s`(S1 config)면 `stale=true`.
- 게이트웨이/`signalStore` → UI에 **"last-known · N초 경과" 배지**. 값은 마지막값을 회색/디밍 표기, **절대 재생성·보간 금지**.
- 새 WS 타입 없이 기존 상태 페이로드에 `stale`·`age_s` 필드만 부가(계약 확장, 비파괴).

---

## 5. 크래시 격리

- **P-producer kill → P-core 생존**: history·WS·UI 계속 응답, 해당 레인/자산 stale 배지, **캐스케이드·예외 전파 없음**.
- **P-producer restart → resume**: 로컬 버퍼 재전송, stale 해제, 카운트 이어감(중복 없이).
- P-core 크래시는 슈퍼바이저 재기동 + §3 복원으로 커버(단, 그동안 UI 다운은 감수 — 신뢰성 경계상 수용).

---

## 6. 슈퍼비전

- `docker-compose.yml`: P-producer·P-core를 별도 서비스로, `restart: unless-stopped` + **서비스별 healthcheck**.
- 베어메탈 대비 `supervisord`/systemd 유닛도 병기(선택).
- healthcheck는 프로세스별 liveness(P-producer=취득 루프 tick, P-core=state read) — 공용 `/api/health` 재사용 여부는 S3b-0에서 결정.

---

## 7. 파일 산출물
| 파일 | 신규/수정 | 내용 |
|---|---|---|
| `docs/s3b_audit.md` | **신규** | S3b-0: 생산자 이관 대상·복원 가능/휘발 필드·헬스 실측. |
| `aria/planes/inspection_node.py` | 수정 | 독립 프로세스 진입점 + 카메라/모델/memory_bank 로딩 이관 + 로컬 버퍼. |
| `aria/planes/twin_state.py` | 수정 | 내부 수신 엔드포인트 + `last_update_ts`·stale + 재기동 복원(recent()). |
| `aria/orchestration/event_bus.py` | 수정 | IPC 어댑터 경계(기본 HTTP/WS). 페이로드 계약 불변. |
| `server/app.py` | 수정(경량) | 상태 페이로드에 `stale`·`age_s` 부가(비파괴). |
| `hmi/scene/*`·`signalStore.js` | 수정 | stale 배지 표기(값 디밍·경과시간). 무회귀. |
| `docker-compose.yml`·`start_aria.sh` | 수정 | 2서비스 기동·restart 정책·per-service health. |
| `tests/golden_trace.py` | 수정 | 프로세스 분리 모드에서도 동일 고정입력 리플레이 지원. |

---

## 8. 안전 / 거버넌스
- **무회귀 최우선**: 분리 전/후 골든 diff 0이 착수 완료 조건.
- stale는 **표기**일 뿐 값 생성 아님. 계약은 확장만(파괴 금지).
- 각 단계 독립 롤백(2프로세스→1프로세스 복귀 가능하게 유지).

---

## 9. 검증 게이트 (§8-5/6/7 실현)
1. **골든 무회귀 + 환경 동일성**: 분리 모드 고정입력 → `diff==0`. **먼저** 골든 캡처 환경과 P-producer 환경의 config·memory_bank·CWD 동일성 대조(diff나면 판정 아닌 환경부터 의심).
2. **크래시 격리**: P-producer kill → P-core 200 응답·UI stale·예외 전파 0.
3. **resume**: P-producer restart → 버퍼 재전송·카운트 이어감·중복 0.
4. **복원**: P-core 재기동 → §3 표대로 재구성; 휘발 필드 stale로 시작(가짜 초기화 0).
5. **stale 정직성**: 소스 끊김 시 배지+경과시간, 값 재생성/보간 0.
6. **결정성**: 동일 입력 → 동일 verdict/OEE/PdM(난수 0).

---

## 10. 단계 + 런타임 게이트
- **S3b-0 감사** — `s3b_audit.md`(이관 대상·복원 필드·헬스). 게이트: 코드 1:1.
- **S3b-1 격리** — 생산자 프로세스 분리 + IPC + 로컬 버퍼. 게이트: 골든 diff 0 + 환경 동일성.
- **S3b-2 복원** — recent()/이벤트로 재구성. 게이트: 재기동 후 상태 복원·휘발 안전측.
- **S3b-3 stale** — last_update·배지. 게이트: 끊김 시 stale·값 위조 0.
- **S3b-4 슈퍼비전/격리** — compose restart·health. 게이트: kill→생존→resume.

---

## 11. 다음 트랙 연결
- **24h 라이프사이클**: 드리프트 모니터·롤링 FAT를 `pdm_fusion`과 동일하게 P-core 인접 out-of-process 서비스로 슬롯인. `context.py`(S1)·`health_features`(T1-C) 재사용.
- **HIL 경계**: §2 IPC 어댑터를 **OPC UA/MQTT로 교체**하고 P-producer 자리에 HIL/물리 시뮬을 꽂으면 실배포 동형 트윈.

---

## 12. Claude Code 미션 브리프 (그대로 전달)
```
목표: 생산자(카메라·추론) 프로세스를 상태+게이트웨이에서 물리 격리 + 시계열 복원 + stale 정직성 + 크래시 격리/슈퍼비전.
경계: 물리 2프로세스(P-producer | P-core). 3프로세스는 선택(UI 스케일 필요 시).
불변: verdict·OEE·HOLD·PdM·UI 무회귀(골든 diff 0) · 새 WS 타입 없음 · 상태 소유자 TwinState 하나 · 값 위조 금지.
선행: S3b-0 감사(생산자 이관 대상·복원 가능/휘발 필드·헬스 실측). 가정 금지.
순서: S3b-0 → S3b-1 격리(골든+환경동일성) → S3b-2 복원 → S3b-3 stale → S3b-4 슈퍼비전.
전송: event_bus 뒤 IPC, 기본 내부 HTTP/WS + 로컬 버퍼. OPC UA/MQTT는 HIL 트랙 교체.
검증: §9 게이트 6종.
```
