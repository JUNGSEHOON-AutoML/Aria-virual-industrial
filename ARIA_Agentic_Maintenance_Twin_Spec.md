# ARIA — Agentic 유지보수 트윈 구현 명세 (구현 가능 범위)

> 한 줄: 기존 ARIA 에이전트 레이어(`/ws/chat`의 agent_status·thought·tool_*)에 **유지보수 툴 + 3D 신체(아바타)
> + VLM 진단 + 에피소드 로깅**을 붙여, "에이전트가 가상에서 해법을 *시연·권고*하고 사람이 *승인*하는" 트윈을 만든다.
>
> **핵심 안전 설계 — Simulate-then-Approve**: 에이전트는 가상 트윈에서 해법을 시연/권고. **실 시스템 액션은 운영자 승인 후 실행.**
>
> 가드레일: ⛔ RL 학습·온디바이스 LoRA·실 로봇/장비 물리 제어·물리엔진·AGPL/Unity 복제 — 제외. verdict(anomaly score) 로직 불변. 실제 `/ws/chat` 타입만.

## OODA / 범위 구분
| 요소 | 구현 | 비고 |
|---|---|---|
| 상태 스토어(자산+에이전트) | ✅ | signalStore 확장 |
| Observe→Think→Act 루프 | ✅ | **기존 LLM 에이전트 재사용** |
| MCP 유지보수 툴 | ✅ | get_status/move/repair/notify/diagnose |
| VLM 진단(이미지→권고) | ✅ | API 호출(Claude vision) |
| 아바타 이동/수리 애니메이션 | ✅ | R3F(경량 프록시 우선) |
| 에피소드 로깅 | ✅ | SQLite/JSON |
| RL 에이전트 학습 | ⏸ | Omniverse/Isaac — 제외 |
| 온디바이스 LoRA | ⏸ | 향후 트랙 |
| 실 로봇/장비 물리 제어 | ⏸ | 안전·하드웨어 — 제외(승인 후 API 액션만) |

---

## 1. 아키텍처
```
/ws/chat 이벤트(ALARM/inspector_result NG/diagnostic_result)
        │ Observe
        ▼
   signalStore(assets health + agent state)  ◀── 상태 단일 소스
        │ Think (기존 LLM 에이전트 + 유지보수 system prompt + MCP 툴)
        ▼
   Tool 호출 ── 가상 액션(move/anim) ──▶ R3F 아바타 즉시 실행
            └─ 실 액션(recalibrate/restart) ──▶ ★notify_human(승인) ──▶ /api/inspector|action
        │ 결과
        ▼
   log_episode(event, snapshot, action, result, time) ──▶ 로컬 DB(평가/개선)
```

---

## 2. State 확장 (signalStore)
```js
assets: { camera_1:{status:'ERROR',code:'CALIBRATION_FAIL'}, motor_3:{status:'OK',temp:40}, ... }
agent:  { position, task:'IDLE|MOVING|DIAGNOSING|REPAIRING', target, lastEpisode }
approvals: [ {id, action, asset, status:'pending|approved|rejected'} ]
```
소스: assets ← inspector_state/diagnostic_result, agent/approvals ← 에이전트 루프.

---

## 3. Agent Loop (Observe→Think→Act) — 기존 에이전트 재사용
- **Observe**: `/ws/chat` 이벤트 수신 → 관련 asset_status 수집 + (비전 결함이면) image_b64+heatmap.
- **Think**: 기존 LLM(function-calling)에 유지보수 system prompt + 아래 MCP 툴셋 제공 → 행동 결정(thought/tool_use 메시지 그대로 활용).
- **Act**: 가상 액션은 즉시, **실 액션은 승인 게이트** 경유. 종료 시 `log_episode`.

---

## 4. MCP / Tool 스키마 (+ 실제 매핑 + 승인 게이트)
| tool | 입력 | 동작 | 실/가상 |
|---|---|---|---|
| `get_asset_status` | asset_id | signalStore 조회 | 가상(읽기) |
| `vlm_diagnose` | image_b64, heatmap | VLM→{defect, location, recommended_action} | 가상(API) |
| `move_agent` | agent_id, target_asset | 아바타 이동 애니메이션 | 가상 |
| `run_repair_sim` | asset_id, action | 트윈에서 수리 *시연*(애니메이션) | 가상 |
| `request_real_action` | asset_id, action(recalibrate/restart) | **notify_human→승인 후** `/api/inspector|action` | ★실(승인필수) |
| `notify_human` | message, severity | 승인 요청/알림 UI | — |
| `log_episode` | {...} | 로컬 DB 기록 | — |
> 규칙: **실 시스템을 바꾸는 건 `request_real_action` 하나뿐이고, 항상 운영자 승인**을 거친다. 나머지는 가상·읽기.

---

## 5. VLM 진단
- 입력: NG `inspector_result.image_b64` + heatmap(min_val). 
- 호출: Claude vision API → 구조화 출력 `{defect_type, location, severity, recommended_action, confidence}`.
- 용도: 에이전트 Think 단계의 근거 + 운영자에게 "무엇이/어떻게/무엇을 할지" 설명.
- ⚠️ anomaly score 해석 불변(낮을수록 정상). VLM은 *설명/권고*, 판정은 PatchCore τ가 결정.

---

## 6. 3D Embodiment (R3F)
- `WorkerAgent`: `useGLTF('/models/worker.glb')` + `useAnimations`(Walk/Repair). task에 따라 재생.
- **경량 프록시 우선**: 리깅 캐릭터 자산이 없으면 **드론/마커 아바타**가 대상 자산으로 이동(lerp) + "수리" 파티클/렌치 이펙트. 리깅 GLB는 나중에 교체.
- move: targetPosition으로 lerp + 경로. repair_sim: 대상 옆에서 수리 이펙트 + 자산 상태 색 변화(ERROR→OK).

---

## 7. MLOps 피드백 (현실 범위)
- **에피소드 로깅**: {event, observation 스냅샷, 선택 action, 승인여부, 결과, 소요시간} → 로컬 DB(SQLite/TS-DB).
- **평가/개선**: 성공률·MTTR·자주 나는 에러 패턴 분석 → system prompt/tool 정책 개선(오프라인).
- **LoRA 파인튜닝은 별도 트랙**: 데이터는 여기서 쌓되, 실제 가중치 튜닝은 데모 범위 밖(향후).

---

## 8. 단계 + 런타임 게이트
- **A1 상태+이벤트** — assets/agent 스토어 + `/ws/chat` 이벤트 트리거. 게이트: NG/ALARM 시 루프 기동.
- **A2 Think+툴** — LLM이 유지보수 툴 선택(thought/tool_use). 게이트: 에러→적절 tool 호출 로그.
- **A3 아바타 시연** — move_agent + run_repair_sim 애니메이션. 게이트: 아바타가 대상으로 이동·수리 시연.
- **A4 승인 게이트** — request_real_action → 운영자 승인 → `/api` 호출. 게이트: 승인 없이는 실행 안 됨.
- **A5 VLM+로깅** — VLM 진단 표출 + 에피소드 DB 기록. 게이트: 진단/로그 확인.
- 시각·동작 게이트는 본인 브라우저 확인(빌드 아님).

---

## 9. Claude Code 미션 브리프 (그대로 전달)
```
목표: 기존 ARIA 에이전트(/ws/chat agent_status/thought/tool_*)에 유지보수 에이전트 능력을 추가.
핵심 안전: Simulate-then-Approve — 에이전트는 가상에서 시연/권고, 실 시스템 액션은 운영자 승인 후만.

[A] signalStore 확장: assets{status/code/metric}, agent{position,task,target}, approvals[].
[B] Agent loop: /ws/chat 이벤트(NG/ALARM/diagnostic_result)→Observe(asset+image/heatmap)→
    Think(기존 LLM function-calling + 유지보수 system prompt + 툴셋)→Act.
[C] 툴: get_asset_status, vlm_diagnose(image+heatmap→권고, Claude vision API), move_agent,
    run_repair_sim(가상 시연), request_real_action(★notify_human 승인→/api/inspector|action), notify_human, log_episode.
    실 시스템 변경은 request_real_action 하나뿐 + 항상 승인.
[D] R3F WorkerAgent: gltf+anim(Walk/Repair), 자산 없으면 드론/마커 프록시+이펙트. task로 move/repair 재생.
[E] MLOps: 에피소드 로깅(SQLite/JSON: event,snapshot,action,approval,result,time). LoRA는 제외(향후).
[DON'T] RL 학습·온디바이스 LoRA·실 로봇 물리제어·물리엔진·AGPL/Unity 복제. verdict 로직 변경. 새 ws 엔드포인트.
        승인 없는 실 액션 자동 실행 금지.
[DONE] A1~A5 런타임: NG→루프→아바타 시연→승인 게이트(미승인시 미실행)→VLM 진단/로깅. (빌드 아님)
```

## 10. DO / DON'T
- ✅ 기존 에이전트 재사용 · MCP 유지보수 툴 · 가상 시연 · **승인 게이트** · 경량 아바타 · 에피소드 로깅.
- ⛔ RL/LoRA/실 로봇 물리제어/물리엔진/AGPL·Unity 복제 · verdict 로직 변경 · 승인 없는 실 액션.
