"""도메인 랜덤화 seam (백엔드 포트).

프론트 `frontend/src/sim/randomization.js`의 `RANGES`/`sampleSceneParams()`를
파이썬으로 이식한 것. 같은 철학(sim2_domain_randomization_spec.md §0):
"랜덤화는 seam이다 — 같은 함수를 N번 호출해 다양한 프레임/에피소드를 만든다."

순수 함수 유지(부수효과 없음). FactoryEnv.reset()이 매 에피소드 호출해
부품 자세·조명을 변주 → 학습된 정책의 sim2real 전이를 돕는다.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

# 프론트 randomization.js와 동일 범위 (단위: m, rad). part.y는 JS의 z축에 대응.
RANGES = {
    "part": {
        "x": (-0.15, 0.15),
        "y": (-0.15, 0.15),
        "yaw": (0.0, 2 * math.pi),
        "tilt": (-0.12, 0.12),
    },
    "light": {
        "ambient": (0.20, 0.60),
        "key": (0.60, 1.60),
    },
}


def sample_scene_params(rng: Optional[np.random.Generator] = None) -> dict:
    """씬 1회 샘플. reset()이 N번 호출 → N개 다양한 초기조건."""
    r = rng or np.random.default_rng()

    def u(lohi):
        lo, hi = lohi
        return float(lo + r.random() * (hi - lo))

    return {
        "part": {
            "x": u(RANGES["part"]["x"]),
            "y": u(RANGES["part"]["y"]),
            "yaw": u(RANGES["part"]["yaw"]),
            "tiltx": u(RANGES["part"]["tilt"]),
            "tilty": u(RANGES["part"]["tilt"]),
        },
        "light": {
            "ambient": u(RANGES["light"]["ambient"]),
            "key": u(RANGES["light"]["key"]),
        },
    }


def yaw_tilt_to_quat(yaw: float, tiltx: float = 0.0, tilty: float = 0.0) -> np.ndarray:
    """오일러(z-yaw, x-tilt, y-tilt) → MuJoCo 쿼터니언 [w, x, y, z]."""
    cz, sz = math.cos(yaw / 2), math.sin(yaw / 2)
    cx, sx = math.cos(tiltx / 2), math.sin(tiltx / 2)
    cy, sy = math.cos(tilty / 2), math.sin(tilty / 2)
    # q = qz * qy * qx  (intrinsic z-y-x)
    w = cz * cy * cx + sz * sy * sx
    x = cz * cy * sx - sz * sy * cx
    y = cz * sy * cx + sz * cy * sx
    z = sz * cy * cx - cz * sy * sx
    q = np.array([w, x, y, z], dtype=np.float64)
    return q / (np.linalg.norm(q) + 1e-12)
