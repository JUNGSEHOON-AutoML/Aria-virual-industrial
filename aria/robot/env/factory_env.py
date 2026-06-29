"""FactoryEnv — MuJoCo 듀얼암 검사공장 환경 (R-1 골격).

설계: docs/specs/robot_arm_learning_env_methodology.md §1, §3
- 이 환경이 "진실 소스(ground truth)". Three.js(factory.jsx)는 get_joint_state()를
  WebSocket으로 받아 그리는 *모니터 뷰* (물리는 여기서만).
- Gym 스타일 reset()/step() — 이후 R-4(텔레오퍼레이션/녹화), R-5(정책 학습),
  R-6(롤아웃 평가)가 이 인터페이스 위에 올라간다.
- reset()이 randomization.sample_scene_params()로 부품 자세·조명을 변주(④ 도메인 랜덤화).

mujoco 미설치 환경에서도 *패키지 임포트*는 깨지지 않는다(지연 임포트). 실제 인스턴스화
시점에만 mujoco를 요구한다.
    설치: py3.9+ → `pip install mujoco`,  py3.8 → `pip install mujoco==2.3.7`
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .randomization import sample_scene_params, yaw_tilt_to_quat

_ASSETS = Path(__file__).parent / "assets"
DEFAULT_MODEL = _ASSETS / "dual_arm_factory.xml"


class FactoryEnv:
    """듀얼암 검사공장 물리 환경.

    관측(observation): {"qpos", "qvel", "part_pose", "vector"}
    행동(action): np.ndarray shape (nu,) — 각 actuator ctrl. ctrlrange로 클립.
    보상(reward): R-1에선 0.0 (IL 우선 — 보상 설계 없음, §1-⑤).
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        seed: Optional[int] = None,
        max_steps: int = 400,
        substeps: int = 1,
    ):
        try:
            import mujoco  # noqa: WPS433 (지연 임포트 의도)
        except ImportError as e:  # pragma: no cover - 환경 의존
            raise ImportError(
                "mujoco 미설치. 설치: py3.9+ `pip install mujoco`, "
                "py3.8 `pip install mujoco==2.3.7`"
            ) from e

        self._mj = mujoco
        self.model_path = str(model_path or DEFAULT_MODEL)
        self.model = mujoco.MjModel.from_xml_path(self.model_path)
        self.data = mujoco.MjData(self.model)
        self.rng = np.random.default_rng(seed)
        self.max_steps = int(max_steps)
        self.substeps = max(1, int(substeps))
        self._step_count = 0

        # 부품 free joint의 qpos 시작 주소 (pos[3] + quat[4] = 7)
        self._part_qadr = self._part_qpos_adr("part_free")
        # 구동 관절(actuated) qpos 주소 — 모니터 브릿지용
        self._act_joint_qadr = self._actuated_joint_qpos_adr()
        # 천장 조명 id (없으면 None)
        self._light_id = self._safe_name2id(mujoco.mjtObj.mjOBJ_LIGHT, "ceiling")

        self.nu = int(self.model.nu)
        self.ctrl_range = self.model.actuator_ctrlrange.copy()  # (nu, 2)

    # ── 공개 API ────────────────────────────────────────────────────────────
    @property
    def action_dim(self) -> int:
        return self.nu

    def reset(self, randomize: bool = True) -> dict:
        self._mj.mj_resetData(self.model, self.data)
        if randomize:
            self._apply_domain_randomization()
        self._mj.mj_forward(self.model, self.data)
        self._step_count = 0
        return self._observe()

    def step(self, action):
        a = np.asarray(action, dtype=np.float64).reshape(-1)
        if a.shape[0] != self.nu:
            raise ValueError(f"action dim {a.shape[0]} != nu {self.nu}")
        # ctrlrange로 클립
        a = np.clip(a, self.ctrl_range[:, 0], self.ctrl_range[:, 1])
        self.data.ctrl[:] = a
        for _ in range(self.substeps):
            self._mj.mj_step(self.model, self.data)
        self._step_count += 1

        obs = self._observe()
        reward = 0.0  # R-1: IL 우선, 보상 없음
        done = self._step_count >= self.max_steps
        info = {"step": self._step_count}
        return obs, reward, done, info

    def get_joint_state(self) -> dict:
        """모니터 브릿지용 — 구동 관절명 → 현재 각도(rad)/변위(m).

        factory.jsx의 RobotArm이 WS로 이 dict를 받아 Math.sin 대신 실제 포즈를 그린다.
        """
        out = {}
        for name, adr in self._act_joint_qadr.items():
            out[name] = float(self.data.qpos[adr])
        return out

    def part_pose(self) -> np.ndarray:
        """부품 [x,y,z, qw,qx,qy,qz]."""
        adr = self._part_qadr
        return self.data.qpos[adr : adr + 7].copy()

    # ── 내부 ────────────────────────────────────────────────────────────────
    def _observe(self) -> dict:
        qpos = self.data.qpos.copy()
        qvel = self.data.qvel.copy()
        part = self.part_pose()
        act_q = np.array(
            [self.data.qpos[a] for a in self._act_joint_qadr.values()], dtype=np.float64
        )
        vector = np.concatenate([act_q, part]).astype(np.float32)
        return {"qpos": qpos, "qvel": qvel, "part_pose": part, "vector": vector}

    def _apply_domain_randomization(self):
        p = sample_scene_params(self.rng)
        # 부품 위치/자세 (검사대 위 z는 고정 0.50, x·y·yaw·tilt 변주)
        adr = self._part_qadr
        self.data.qpos[adr + 0] = p["part"]["x"]
        self.data.qpos[adr + 1] = p["part"]["y"]
        self.data.qpos[adr + 2] = 0.50
        quat = yaw_tilt_to_quat(p["part"]["yaw"], p["part"]["tiltx"], p["part"]["tilty"])
        self.data.qpos[adr + 3 : adr + 7] = quat
        # 조명(가능하면) — key 밝기를 diffuse에 반영
        if self._light_id is not None:
            key = p["light"]["key"]
            self.model.light_diffuse[self._light_id] = np.array(
                [key, key, key], dtype=np.float64
            ).clip(0, 1)

    def _part_qpos_adr(self, joint_name: str) -> int:
        jid = self._mj.mj_name2id(self.model, self._mj.mjtObj.mjOBJ_JOINT, joint_name)
        if jid < 0:
            raise ValueError(f"free joint '{joint_name}' 없음 — MJCF 확인")
        return int(self.model.jnt_qposadr[jid])

    def _actuated_joint_qpos_adr(self) -> dict:
        """actuator가 구동하는 관절들의 {name: qpos_adr}."""
        out = {}
        for aid in range(self.model.nu):
            jid = int(self.model.actuator_trnid[aid, 0])
            name = self._mj.mj_id2name(self.model, self._mj.mjtObj.mjOBJ_JOINT, jid)
            if name is not None:
                out[name] = int(self.model.jnt_qposadr[jid])
        return out

    def _safe_name2id(self, objtype, name: str):
        i = self._mj.mj_name2id(self.model, objtype, name)
        return int(i) if i >= 0 else None


def _smoke():
    """mujoco 설치 환경에서: 환경 생성 → reset → 랜덤 행동 몇 스텝 → 상태 출력."""
    env = FactoryEnv(seed=0, max_steps=50)
    obs = env.reset()
    print(f"[FactoryEnv] nu(action_dim)={env.action_dim}")
    print(f"[FactoryEnv] obs.vector shape={obs['vector'].shape}")
    print(f"[FactoryEnv] joints={list(env.get_joint_state().keys())}")
    for t in range(10):
        a = env.rng.uniform(-1, 1, size=env.action_dim)
        obs, r, done, info = env.step(a)
    js = env.get_joint_state()
    print(f"[FactoryEnv] after 10 steps · part_pose={env.part_pose().round(3)}")
    print(f"[FactoryEnv] joint_state={ {k: round(v,3) for k,v in js.items()} }")
    print("[FactoryEnv] smoke OK")


if __name__ == "__main__":
    _smoke()
