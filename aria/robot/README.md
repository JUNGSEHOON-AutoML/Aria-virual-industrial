# aria/robot — 학습하는 로봇팔 서브시스템

설계 방법론: [`docs/specs/robot_arm_learning_env_methodology.md`](../../docs/specs/robot_arm_learning_env_methodology.md)

> 이상탐지 파이프라인과 **격리된 추가 모듈**입니다. 기존 `/api/sim/*`·CCIFPS·FAT는 건드리지 않습니다.

## 현재 단계 — R-1: 물리 환경

```
aria/robot/
└── env/
    ├── factory_env.py        # FactoryEnv: MuJoCo reset/step/관측/행동 (진실 소스)
    ├── randomization.py      # 도메인 랜덤화 seam (sim/randomization.js 백엔드 포트)
    └── assets/
        └── dual_arm_factory.xml  # 최소 듀얼암 MJCF (SO-101 공식 모델로 교체 가능)
```

## 설치

MuJoCo는 선택 의존성입니다(미설치 시 패키지 임포트는 정상, 인스턴스화 시에만 요구).

```bash
# Python 3.9+ (권장)
pip install mujoco

# Python 3.8 (현재 patchcore 환경) — 3.8 지원 마지막 버전
pip install mujoco==2.3.7
```

## 스모크 테스트

```bash
# mujoco 설치 후
python -m aria.robot.env.factory_env
# → nu(action_dim)=8, obs.vector shape, joint 목록, 10스텝 후 part_pose / joint_state 출력

# mujoco 없이도 동작 (랜덤화 seam — 순수 함수)
python -c "from aria.robot.env import sample_scene_params; print(sample_scene_params())"
```

## 인터페이스 (이후 단계가 올라탐)

```python
from aria.robot.env import FactoryEnv
env = FactoryEnv(seed=0)            # model_path=... 로 공식 SO-101 MJCF 교체
obs = env.reset()                   # 도메인 랜덤화 적용된 초기 관측
obs, reward, done, info = env.step(action)   # action: np.ndarray (env.action_dim,)
env.get_joint_state()              # {관절명: 각도} — Three.js 모니터 브릿지(R-2)용
```

## 다음 단계

- **R-2** WS `joint_state` 채널 + `factory.jsx:RobotArm` 포즈 바인딩 (Math.sin 제거)
- **R-3** 도메인 랜덤화는 R-1에 이미 포함(`reset()`)
- **R-4** `teleop/` + `recorder/` — 텔레오퍼레이션 시연 → 에피소드 manifest
- **R-5** `policy/` — IL(ACT/Diffusion) 학습, `/api/robot/train`
- **R-6** `rollout/` — 정책 롤아웃 성공률, `/api/robot/eval`
- **R-7** `factoryLoop()` 를 로봇 루프(collect→train→eval→repeat)로 확장
