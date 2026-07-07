# ARIA 설계 방법론 — 학습하는 로봇팔을 가상 공장에 배치하고 학습을 모니터링하기

> 목표: `factory.jsx`의 **장식용 로봇팔(`RobotArm`)** 을 xlerobot처럼 **실제로 학습하는 듀얼암**으로 바꾸고,
> 그 학습 과정을 ARIA 가상 공장 안에서 **실시간 모니터링**한다.
> 이 문서는 코드 구현이 아니라 **"환경을 어떻게 설계·구성하는가"의 방법론**이다. (참고: [xlerobot-learning-guide](https://github.com/dinnerandcoffee/xlerobot-learning-guide), [mobile_robot_Simulation](https://github.com/ggh-png/mobile_robot_Simulation))

---

## 0. 핵심 통찰 — ARIA는 이미 학습 루프의 골격을 갖고 있다

두 가지 사실을 먼저 직시한다.

1. **현재 로봇팔은 가짜다.** `frontend/src/sim/factory.jsx`의 `RobotArm`(360–392줄)은
   `Math.sin()` 으로 관절을 흔드는 **순수 애니메이션**이다. 물리·기구학·제어·학습이 전혀 없다.
   `virtual_industrial_factory_scale_spec.md` §7도 명시: *"작업자/로봇팔은 분위기 연출(idle/sweep) — 실제 작업·물류·충돌 아님(후속)."*
   씬의 `LearningCore`(527줄)가 학습처럼 보이지만, 실제 학습은 **이상탐지 메모리뱅크(CCIFPS)** 이지 로봇 정책 학습이 아니다.

2. **그러나 학습 루프의 골격은 이미 있다.** ARIA의 `generate → train → validate → repeat` 무한 루프
   (`phase2_autonomous_loop_spec.md`)는 **로봇 학습 루프와 구조가 1:1로 같다.** 우리는 새 아키텍처를
   만들 필요가 없다 — **루프의 "대상"을 이상탐지에서 로봇 조작 정책으로 갈아끼우면** 된다.

### 0-1. 패러다임 매핑 (이게 이 문서의 출발점)

| 단계 | xlerobot (로봇 조작 학습) | ARIA 현재 (이상탐지) | ARIA 코드 근거 |
|------|---------------------------|----------------------|----------------|
| 시뮬 씬 | MuJoCo / Isaac 3D 월드 | Three.js 가상 공장 | `frontend/src/sim/factory.jsx` |
| 씬 변주 | reset 시 도메인 랜덤화 | `sampleSceneParams()` | `frontend/src/sim/randomization.js` |
| 데이터 수집 | VR 텔레오퍼레이션 시연 → 에피소드 | 합성 결함 주입 → manifest | `aria/simulation/dataset.py` |
| 학습 | 모방학습(ACT/Diffusion) | 메모리뱅크 구축 | `app.py:/api/sim/train` → `build_bank` |
| 검증 | 정책 롤아웃 성공률 | FAT escape율 판정 | `app.py:/api/sim/validate` → `run_validation` |
| 반복 | 데이터 플라이휠 | `factoryLoop()` 무한 순환 | `phase2_autonomous_loop_spec.md` §3-D |
| 모니터링 | 학습 곡선/롤아웃 뷰 | WS `training`/`agent_status` 이벤트 + `LearningCore` | `app.py` `publish`/`emit_agent`, `factory.jsx:527` |

> **결론:** ARIA는 "자율 학습 공장"의 배관(루프·데이터셋·검증 게이트·WebSocket 모니터링)을
> 이미 깔아놨다. 빠진 건 **물리·기구학·로봇 정책** 세 가지뿐이다.

---

## 1. 학습 로봇 환경 설계 방법론 (핵심)

xlerobot/LeRobot/MuJoCo 계열이 공유하는 환경 설계의 정수는 **"Gym 스타일 환경(Environment) 추상"** 이다.
"학습하는 로봇"을 만든다는 것은 곧 아래 9개 구성요소를 정의하는 일이다. 각 항목에 **ARIA에 이미 있는 것 / 새로 만들 것**을 표시한다.

### ① 씬 정의 (Scene / World)
- **무엇:** 월드(바닥·조명·테이블), 로봇(링크·관절), 작업 대상물(부품), 카메라.
- **방법:** MuJoCo는 `MJCF`(XML), ROS/Isaac은 `URDF`로 기술. xlerobot 가이드 §3.6 "URDF/MJCF 모델 이해"가 이 부분.
- **ARIA 현황:** Three.js는 **시각화 전용**이라 물리 표현이 없다. → **새로 `MJCF` 씬 필요.**
  단, 레이아웃(컨베이어 z, 라인 배치, 검사대 z≈0)은 `factory.jsx`에서 그대로 차용한다.

### ② 관측 공간 (Observation Space)
- **무엇:** 정책이 매 스텝 "보는" 것. 보통 ① 카메라 RGB(들) ② 관절 각도/속도(proprioception) ③ 그리퍼 상태.
- **ARIA 현황:** 카메라/이미지 파이프라인은 있음(`/video_feed`, `vision_router`). 관절 상태는 새 물리엔진에서 나온다.

### ③ 행동 공간 (Action Space)
- **무엇:** 정책이 내보내는 명령. 듀얼암이면 보통 `[좌7관절 + 좌그리퍼, 우7관절 + 우그리퍼]` 또는
  엔드이펙터 델타(`Δx,Δy,Δz,Δrot,gripper`).
- **ARIA 현황:** 없음. → **새로 정의** (SO-100/101 기준 관절 수에 맞춤).

### ④ 리셋 + 도메인 랜덤화 (Reset / Domain Randomization)
- **무엇:** 매 에피소드 시작 시 부품 위치·자세·조명·텍스처를 무작위화 → 학습된 정책이 현실로 전이(sim2real)되게 함.
- **★ ARIA가 이미 갖고 있다.** `randomization.js`의 `sampleSceneParams()`(부품 x/z/회전, ambient/key/색온도)와
  `sim2_domain_randomization_spec.md` §0 *"랜덤화는 seam이다 … 같은 함수를 N번 호출"* 가 정확히 이 개념이다.
  → **이 seam을 MuJoCo 리셋에 그대로 이식**한다. (방법론적으로 이미 정답을 갖고 있다는 뜻.)

### ⑤ 보상 vs 시연 (Reward / Demonstration)
- **두 갈래:**
  - **모방학습(IL):** 보상 함수 불필요. 사람이 텔레오퍼레이션으로 "성공 시연"을 녹화 → 정책이 따라 배움. **xlerobot이 택한 길**(VR Quest3 → 데이터 수집 → IL). **듀얼암 조작에 권장.**
  - **강화학습(RL):** 보상 함수 설계 필요(예: 집기 성공 +1). ManiSkill이 이 용도.
- **ARIA 권장:** **IL 우선**(보상 설계 회피, 시연 데이터로 시작). RL은 후속.

### ⑥ 스텝 루프 (env.step)
- **무엇:** `obs, reward, done = env.step(action)` 표준 인터페이스. 물리 한 틱 진행.
- **ARIA 현황:** 없음 → MuJoCo가 제공. 이걸 Python 클래스로 감싼다.

### ⑦ 에피소드 녹화 (Episode Recording)
- **무엇:** 텔레오퍼레이션 중 `(obs, action)` 시퀀스를 에피소드 단위로 저장. LeRobot 데이터셋 포맷이 사실상 표준.
- **★ ARIA 패턴 재사용.** `dataset.py:save_sim_dataset()`가 이미 **manifest.json**으로 데이터를 묶는다(§31 "6A 포맷과 동일 → 학습이 그대로 소비"). → **같은 manifest 패턴을 에피소드 녹화로 확장**.

### ⑧ 학습 (Training)
- **무엇:** 수집된 에피소드로 정책 학습. IL이면 ACT(Action Chunking Transformer) / Diffusion Policy가 대표.
- **★ ARIA 배선 재사용.** `app.py:/api/sim/train`이 백그라운드 스레드 + `publish(make_training_event(...))`로
  학습 진행 이벤트를 쏜다. → **`build_bank` 자리를 `train_policy`로 교체**하고 같은 이벤트 배관을 쓴다.

### ⑨ 평가 게이트 + 모니터링 (Evaluation Gate / Monitoring)
- **무엇:** 학습된 정책을 시뮬에서 롤아웃 → 성공률 측정 → 합격/불합격 판정.
- **★ ARIA가 이미 갖고 있다.** `/api/sim/validate`의 **FAT 판정**(`run_validation`, escape율 게이트,
  `virtual_fat_acceptance_gate_spec.md`)이 그대로 "정책 성공률 게이트"로 치환된다.
  모니터링도 이미 완비 — WS `training`/`agent_status` 이벤트 + `StatusBoard`/`LearningCore` 3D 표시.

---

## 2. ARIA 보유 자산 vs 갭 (요약)

| 환경 구성요소 | ARIA 보유? | 근거 / 해야 할 일 |
|----------------|:---:|------|
| ① 씬 정의 | △ | Three.js 레이아웃 有(시각화). **MJCF 물리 씬 신규** |
| ② 관측 공간 | △ | 이미지 파이프라인 有. 관절상태는 물리엔진에서 |
| ③ 행동 공간 | ✕ | **신규 정의** (듀얼암 관절/그리퍼) |
| ④ 리셋·도메인 랜덤화 | ✓ | `sampleSceneParams()` seam **이식만** |
| ⑤ 보상/시연 | △ | **IL 시연 수집 경로 신규** (보상 불필요) |
| ⑥ 스텝 루프 | ✕ | **MuJoCo 래퍼 신규** |
| ⑦ 에피소드 녹화 | △ | `manifest` 패턴 **확장** |
| ⑧ 학습 | ◑ | 이벤트 배관 有. `train_policy` **신규**, `/api/sim/train` 재사용 |
| ⑨ 평가·모니터링 | ✓ | FAT 게이트 + WS + 3D **거의 그대로** |

→ **신규 핵심 = ①③⑤⑥⑧ 다섯 개. 나머지는 ARIA 자산 재사용.**

---

## 3. 제안 아키텍처 — "물리 백엔드(진실) + Three.js(모니터)" 이원화

가장 중요한 설계 결정: **Three.js를 물리엔진으로 바꾸지 않는다.**
대신 **MuJoCo를 "진실 소스(ground truth)"로 두고, Three.js는 그 상태를 받아 그리는 "모니터 뷰"로 유지**한다.
이미 ARIA는 WebSocket으로 상태를 프론트에 흘리고 있으므로(`manager.broadcast`), 이 패턴을 그대로 쓴다.

```
┌─────────────────────────── 백엔드 (Python, 진실) ──────────────────────────┐
│  aria/robot/                                                               │
│   ├─ env/        MuJoCo 환경 (MJCF 씬 + step/reset + 도메인 랜덤화)         │
│   ├─ teleop/     텔레오퍼레이션 입력 → 행동 (키보드/패드/VR, xlerobot식)    │
│   ├─ recorder/   에피소드 (obs,action) 녹화 → manifest (dataset.py 패턴)    │
│   ├─ policy/     IL 학습/추론 (ACT·Diffusion), train_policy()              │
│   └─ rollout/    학습 정책 시뮬 롤아웃 → 성공률 (validate.py 패턴)          │
│                                                                            │
│  app.py 엔드포인트 (기존 sim 엔드포인트와 형제로)                            │
│   POST /api/robot/collect  텔레오퍼레이션 에피소드 수집 시작                 │
│   POST /api/robot/train    정책 학습 (← /api/sim/train 배관 재사용)         │
│   POST /api/robot/eval     롤아웃 성공률 (← /api/sim/validate 패턴)         │
│   WS    상태 스트림: joint_state / training / agent_status (기존 채널)       │
│                                                                            │
│  aria/mcp/servers/robot_control_mcp.py  ← 에이전트가 "도구"로 로봇 호출      │
└────────────────────────────────────────────────────────────────────────────┘
                              │ WebSocket: 관절각·에피소드·학습이벤트
                              ▼
┌──────────────────── 프론트 (Three.js, 모니터 뷰) ─────────────────────────┐
│  factory.jsx: RobotArm 을 "수신한 관절각으로 포즈" 하도록 교체              │
│   (Math.sin 애니메이션 → props.jointState 바인딩)                          │
│  StatusBoard / LearningCore: 학습 진행·성공률을 그대로 표시 (이미 존재)      │
└────────────────────────────────────────────────────────────────────────────┘
```

### 3-1. 왜 MuJoCo인가 (Isaac/Gazebo 대비)
- **MuJoCo**: 파이썬 네이티브, 경량, 설치 단순 → **ARIA의 FastAPI/Python 스택에 그대로 임포트**. xlerobot의 1차 엔진(§3.2–3.3)이며 LeRobot 생태계 표준. **← 권장.**
- **Isaac Sim**: GPU 사진급 렌더·대규모 병렬에 강하나 무겁고 NVIDIA 종속. 스케일업 필요 시 후속.
- **Gazebo (mobile_robot_Simulation)**: ROS1/2 의존이 강해 ARIA에 끌어오면 **rosbridge** 같은 통신 계층이 추가로 필요. **이동(모바일 베이스) 단계에서만** 검토.

### 3-2. 듀얼암이 곧 "모바일 매니퓰레이터"로 가는 길
xlerobot 자체가 **모바일 베이스 + 듀얼암**이다. 그래서 순서는:
1. **듀얼암 조작(고정 베이스)** 부터 — 위 아키텍처. (당신이 선택한 1순위)
2. 이후 **이동**이 필요하면 — mobile_robot_Simulation의 SLAM/AMCL/move_base 스택을
   `rosbridge` 또는 `mobile_base_mcp`로 ARIA에 브릿지. (베이스의 `Δx,Δθ`를 행동 공간에 추가)

---

## 4. 데이터/제어 흐름 (한 사이클)

```
[리셋] env.reset() → sampleSceneParams() 이식분으로 부품 자세·조명 랜덤화   (④ 재사용)
   ↓
[수집] 텔레오퍼레이션으로 "집어서 검사대에 올리기" 시연 N회                  (⑤ IL)
   ↓  recorder가 (obs, action) 시퀀스를 에피소드로 저장 → manifest          (⑦ dataset.py 패턴)
[학습] train_policy(manifest) → ACT/Diffusion 학습                          (⑧ /api/sim/train 배관)
   ↓  publish(make_training_event(...)) 로 진행 이벤트 스트림 (그대로)
[평가] rollout: 학습 정책으로 시뮬 롤아웃 → 집기 성공률                       (⑨ validate.py 패턴)
   ↓  성공률 < 기준 → FAIL → 데이터 더 수집 / 기준 ≥ → PASS                  (FAT 게이트 치환)
[모니터] WS 이벤트 → factory.jsx: 팔이 학습된 동작으로 실제 움직이고,
         StatusBoard에 성공률·사이클, LearningCore가 학습 중 점멸           (이미 존재)
   ↓
[반복] factoryLoop() 가 위를 무한 순환 (cycle++)                            (phase2 루프 재사용)
```

> 핵심: **굵게 표시된 "재사용/패턴"이 전부 ARIA에 이미 있다.** 신규 작성은 `aria/robot/`의
> env·teleop·policy·rollout 네 모듈과, `factory.jsx`의 `RobotArm` 포즈 바인딩뿐이다.

---

## 5. 단계별 로드맵 (Slice — 기존 spec 관례에 맞춤)

각 Slice는 **독립 실행 가능 + 회귀 가드(기존 이상탐지 파이프라인 무변경)** 를 지킨다.

- **R-1 물리 씬:** `aria/robot/env/` — SO-101 듀얼암 MJCF 씬 + `reset()/step()`.
  수용: 파이썬에서 `env.reset(); env.step(랜덤행동)` 가 관절 상태를 돌려준다(헤드리스 OK).
- **R-2 모니터 브릿지:** WS `joint_state` 채널 + `factory.jsx:RobotArm`을 수신 관절각으로 포즈.
  수용: 백엔드가 관절각을 흘리면 3D 팔이 **그대로** 따라 움직인다(Math.sin 제거).
- **R-3 도메인 랜덤화 이식:** `sampleSceneParams()` 로직을 `env.reset()`의 부품/조명 랜덤화로 포팅.
  수용: 리셋마다 부품 자세·조명이 명세 범위(`RANGES`) 안에서 변동.
- **R-4 텔레오퍼레이션 + 녹화:** `aria/robot/teleop/` + `recorder/` → 에피소드 manifest.
  수용: 키보드/패드로 집기 시연 → `manifest.json`(에피소드 N개, `source:"teleop"`) 생성.
- **R-5 정책 학습:** `aria/robot/policy/train_policy()` + `/api/robot/train`(`/api/sim/train` 복제).
  수용: 수집 데이터로 학습 → WS `training` 이벤트가 `StatusBoard`/`LearningCore`에 표시.
- **R-6 롤아웃 평가 게이트:** `aria/robot/rollout/` + `/api/robot/eval`(`validate.py` 패턴).
  수용: 학습 정책 롤아웃 성공률 → PASS/FAIL 판정이 `StatusBoard`에 표시.
- **R-7 자율 순환:** `factoryLoop()` 를 로봇 루프(`collect→train→eval→repeat`)로 확장.
  수용: "▶ 자동 순환" 시 팔이 점점 더 잘 집고, 성공률이 사이클마다 갱신.
- **R-8 (후속) 이동:** rosbridge/`mobile_base_mcp`로 모바일 베이스 추가 → 모바일 매니퓰레이터.

---

## 6. 모듈/파일 매핑 (구체)

| 신규/변경 | 경로 | 역할 | 차용 패턴 |
|-----------|------|------|-----------|
| 신규 | `aria/robot/env/factory_env.py` | MJCF 씬 + reset/step + 랜덤화 | `randomization.js` seam |
| 신규 | `aria/robot/teleop/teleop.py` | 입력→행동 (kbd/pad/VR) | xlerobot §3 제어 |
| 신규 | `aria/robot/recorder/recorder.py` | 에피소드 (obs,action)→manifest | `aria/simulation/dataset.py` |
| 신규 | `aria/robot/policy/policy.py` | IL 학습/추론 (ACT/Diffusion) | `feature_bank.build_bank` 자리 |
| 신규 | `aria/robot/rollout/rollout.py` | 정책 롤아웃 성공률 | `aria/simulation/validation/validate.py` |
| 신규 | `aria/mcp/servers/robot_control_mcp.py` | 에이전트용 로봇 도구 | 기존 `*_mcp.py` |
| 변경 | `app.py` | `/api/robot/{collect,train,eval}` | `/api/sim/*` 형제 |
| 변경 | `frontend/src/sim/factory.jsx` | `RobotArm` 관절각 수신 포즈 | 327·360줄 교체 |

---

## 7. 주의 / 원칙

- **이상탐지 파이프라인 무변경.** 로봇 학습은 `aria/robot/` + `/api/robot/*` 로 **격리 추가**.
  기존 `/api/sim/*`·CCIFPS·FAT는 손대지 않는다(회귀 가드).
- **Three.js는 모니터, MuJoCo가 진실.** 물리는 백엔드에서만. 프론트는 상태를 받아 그릴 뿐
  (캡처 무결성·`factoryGroupRef` 가드 원칙 유지).
- **도메인 랜덤화 seam은 순수 함수로.** `sim2_domain_randomization_spec.md` §7 원칙 그대로 —
  reset이 N번 호출해 다양성을 만든다(sim2real 전이의 핵심).
- **IL 우선, 보상 설계 회피.** 듀얼암은 시연 데이터로 시작. RL/보상은 후속.
- **이동은 마지막.** 듀얼암(고정 베이스) 검증 후 mobile_robot 스택을 브릿지.
- **MJCF 모델 출처:** SO-100/101 공식 MJCF/URDF를 가져와 ARIA 공장 레이아웃(컨베이어·검사대 z≈0)에 배치.

---

## 8. 참고 자료 매핑

- **xlerobot-learning-guide** → 우리가 차용하는 것: 시뮬 우선 방법론(§3 MuJoCo), 텔레오퍼레이션→시연 데이터→IL 플라이휠(§8), URDF/MJCF 이해(§3.6), 듀얼암 좌표/기구학(§Part3). **= 본 문서 §1·§3의 근간.**
- **mobile_robot_Simulation** → 우리가 차용하는 것: 모바일 베이스 자율주행 스택(SLAM/AMCL/move_base)과 ROS 노드 분해 방식. **= 본 문서 R-8(이동 단계)에서만.**
- **ARIA 내부** → `phase2_autonomous_loop_spec.md`(루프), `sim2_domain_randomization_spec.md`(랜덤화), `virtual_fat_acceptance_gate_spec.md`(평가 게이트), `sim3_capture_to_manifest_spec.md`/`dataset.py`(데이터 패턴).

---

## 9. MJCF 씬 구성 상세 (R-1 구현 가이드)

> 실제 코드: `aria/robot/env/` (구현됨). 이 절은 "왜 이렇게 구성하는가".

### 9-1. MJCF의 4개 블록
MuJoCo 씬(`*.xml`)은 4개 블록으로 기술한다.

| 블록 | 역할 | ARIA 골격(`dual_arm_factory.xml`)에서 |
|------|------|----------------------------------------|
| `<option>` | 물리 설정 | `timestep=0.002`, `gravity`, `integrator=implicitfast` |
| `<default>` | 공통 기본값 | 관절 `damping/armature`, 모터 `ctrlrange/gear` |
| `<asset>` | 재질·텍스처·메시 | 재질 5종(바닥/검사대/팔/그리퍼/부품) |
| `<worldbody>` | 물체 트리(링크·관절) | 바닥 + 검사대 + 부품(free) + 좌/우 팔 |
| `<actuator>` | 구동기 | 팔당 4모터(3힌지+1그리퍼) = 8 |

### 9-2. 핵심 개념 3개
- **body 트리 = 기구학 체인.** 부모 body에 대해 자식 body가 `joint`로 연결된다.
  팔: `base → link1(hinge z) → link2(hinge y) → link3(hinge y) → grip(slide)`.
- **freejoint = "물리에 맡기는 물체".** 부품(`part`)은 `<freejoint>`라 6-DOF로 자유낙하·충돌.
  qpos 7개(위치 3 + 쿼터니언 4) → reset에서 이 7개를 랜덤화해 매 에피소드 다른 초기조건.
- **actuator = 행동 공간의 정의.** `<actuator>`의 모터 개수(`model.nu`)가 곧 `action_dim`.
  `ctrlrange`가 행동 클립 범위. ARIA 골격은 `nu=8`.

### 9-3. 공식 SO-101 모델로 교체하는 법
골격은 API 증명용 최소 모델이다. 실제 학습은 공식 모델로:
```python
FactoryEnv(model_path="path/to/so101/scene.xml")
```
- SO-100/101 공식 MJCF/URDF를 받아 `assets/`에 두고, 컨베이어·검사대(z≈0)를 `<worldbody>`에 합친다.
- `get_joint_state()`/`_actuated_joint_qpos_adr()`는 actuator를 자동 순회하므로 **관절 수가 바뀌어도 코드 수정 불필요**(이름만 factory.jsx 모니터와 맞추면 됨).
- xlerobot 가이드 §3.6(URDF/MJCF 이해)이 이 교체 작업의 직접 참고서.

### 9-4. 부품 자세 랜덤화의 sim2real 의미
`reset()`이 `sample_scene_params()`로 부품 x·y·yaw·tilt·조명을 흔든다. 정책이
"부품이 정확히 한 자리"에만 의존하지 않게 만들어, 실제 컨베이어의 위치 편차에 강건해진다.
→ `randomization.js`(프론트)와 `randomization.py`(백엔드)가 **동일 RANGES**를 공유(seam 일치).

---

## 10. IL(모방학습) 학습 상세 (R-5 설계 가이드)

> 듀얼암 조작은 보상 설계가 어렵다 → xlerobot처럼 **시연 데이터로 배우는 IL**을 1순위로.

### 10-1. 왜 RL이 아니라 IL인가
- **RL:** 보상 함수(집기 성공=+1 등)를 손수 설계 + 수백만 스텝 탐색. 듀얼암 협응엔 보상 설계가 난해.
- **IL:** 사람이 "성공 시연"을 N회 보여주면 정책이 `obs → action` 매핑을 지도학습으로 모사.
  보상 불필요, 데이터 수십~수백 에피소드로 시작 가능. **← ARIA 1순위.**

### 10-2. 대표 알고리즘 2개
| 알고리즘 | 핵심 | 적합 |
|----------|------|------|
| **ACT** (Action Chunking Transformer) | 미래 행동 청크(k스텝)를 한 번에 예측 → 떨림↓ | 정밀 조작(ALOHA·SO-101 표준) |
| **Diffusion Policy** | 행동을 디퓨전으로 생성 → 다봉(multimodal) 시연 처리 | 경로가 여러 갈래인 작업 |

> 둘 다 LeRobot에 구현되어 있어 가져다 쓰기 쉽다. ARIA는 ACT부터 권장(SO-101 레퍼런스).

### 10-3. 데이터 → 학습 → 평가 인터페이스 (ARIA 배관 재사용)
```
[수집] teleop → recorder: 에피소드 = [(obs_t, action_t), ...] × N
         → manifest.json  (dataset.py 패턴: {"episodes":[...], "source":"teleop"})
[학습] /api/robot/train  ← /api/sim/train 복제
         worker(): policy = train_il(manifest)          # ACT/Diffusion
                   publish(make_training_event(run_id, step, total, "running", loss))  # 그대로
                   save(policy);  publish(... "done")
         → StatusBoard/LearningCore가 손도 안 대고 학습 진행 표시
[평가] /api/robot/eval  ← /api/sim/validate 패턴
         rollout: for ep in range(K): obs=env.reset(); 정책으로 done까지 → 성공?
         성공률 = 성공/K  →  PASS/FAIL (FAT escape율 게이트 자리)
```

### 10-4. 관측/행동 규약 (정책 입출력)
- **관측(정책 입력):** `FactoryEnv._observe()`의 `vector`(구동관절각 + 부품포즈) ⊕ 카메라 RGB(후속).
  IL 표준은 카메라 이미지를 주로 쓰므로, R-5에서 `mujoco.Renderer`로 오프스크린 RGB를 obs에 추가.
- **행동(정책 출력):** `env.action_dim`(=nu) 차원 벡터. ACT면 k스텝 청크 → 순차 적용.
- **정규화:** 수집 데이터로 action mean/std 계산해 정규화(IL 안정화의 기본).

### 10-5. 모니터링이 곧 "학습을 보는 화면"
당신이 요청한 *"학습을 모니터링하는 시뮬레이션"* 의 실체:
1. **학습 중** — `LearningCore`가 보라색으로 빠르게 점멸(`trainState.status==='running'`, factory.jsx:529).
2. **성능 추이** — `StatusBoard`에 사이클·성공률(FAT verdict 자리)을 사이클마다 갱신.
3. **정책 행동** — R-2 브릿지로 팔이 **학습된 동작**으로 실제 움직임(Math.sin 아님).
   사이클이 돌수록 집기가 매끄러워지는 것을 3D로 눈으로 확인 → "학습이 일어나는 공장".

---

## 11. 구현 현황 (이 문서 작성 시점)

| 항목 | 상태 | 산출물 |
|------|:---:|--------|
| 설계 방법론 문서 | ✅ | 본 문서 |
| **R-1 물리 환경** | ✅ 골격 | `aria/robot/env/` (`factory_env.py`·`randomization.py`·`assets/dual_arm_factory.xml`), `aria/robot/README.md` |
| URL 단일화(8080) | ✅ | `start_aria.sh` (Vite 5173 제거, FastAPI가 dist 서빙) |
| R-2 모니터 브릿지 | ⬜ | WS `joint_state` + `factory.jsx` 포즈 바인딩 |
| R-4 텔레오퍼레이션/녹화 | ⬜ | `aria/robot/teleop/`·`recorder/` |
| R-5 IL 학습 | ⬜ | `aria/robot/policy/` + `/api/robot/train` |
| R-6 롤아웃 평가 | ⬜ | `aria/robot/rollout/` + `/api/robot/eval` |
| R-7 자율 순환 | ⬜ | `factoryLoop()` 로봇 루프 확장 |

**R-1 검증:** `python -m aria.robot.env.factory_env`(mujoco 설치 시) — `nu=8`, 관측 벡터·관절상태 출력.
mujoco 미설치 시에도 패키지 임포트 + 랜덤화 seam은 정상 동작(검증 완료).
설치: py3.9+ `pip install mujoco`, 현재 patchcore(py3.8)는 `pip install mujoco==2.3.7`.
