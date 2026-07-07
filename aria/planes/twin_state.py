"""TwinState — 트윈 상태 단일 진실원 (T2-A S2).

책임:
  - inspector._run · inspector._lanes · state._agent 세 전역을 여기서 소유.
  - 외부는 TwinState 인스턴스를 통해서만 읽기/쓰기 (reach-in 금지).
  - inspector._infer_lock 은 검사 평면 내부 관심사 → 승격 안 함.

평면 계약:
  - 검사 노드(inspector.py)는 start_run() / stop_run() / update_run() 로 상태 기록.
  - 게이트웨이(state.py)는 emergency_stop() 으로 제어 명령 전달.
  - 두 라우터 모두 get_*() 으로 상태 조회.

스레드 안전:
  - 내부 lock 하나로 보호. 외부는 lock을 알 필요 없음.
"""
from __future__ import annotations
import threading
from typing import Any


class TwinState:
    """세 전역(_run · _lanes · _agent)의 단일 소유자."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # ── 검사 노드 단일 레인 ─────────────────────────────────────
        self._run: dict = {"running": False}

        # ── 검사 노드 멀티레인 ──────────────────────────────────────
        self._lanes: dict = {}
        # 레인 세대 토큰 — stop→start 레이스에서 구 워커 스레드가 새 가동
        # 플래그를 보고 부활(중첩)하는 것을 막는다. start_lanes마다 증가.
        self._lanes_epoch: int = 0

        # ── 에이전트/게이트웨이 상태 ────────────────────────────────
        from aria.core.config import inference as _cfg
        self._agent: dict = {
            "status": "idle",
            "is_running": True,
            "last_action": None,
            "score": 0.0,
            "threshold": _cfg.tau_default,
        }

    # ── _run 접근자 ────────────────────────────────────────────────

    def get_run(self) -> dict:
        with self._lock:
            return dict(self._run)

    def start_run(self, pipe: Any, bridge: Any, mode: str, category: str, holder: dict) -> None:
        with self._lock:
            self._run.update({
                "running": True,
                "pipe": pipe,
                "bridge": bridge,
                "mode": mode,
                "category": category,
                "holder": holder,
            })

    def stop_run(self) -> tuple[Any, Any]:
        """실행 중단. (pipe, bridge) 반환 — 호출자가 .stop()."""
        with self._lock:
            pipe = self._run.get("pipe")
            bridge = self._run.get("bridge")
            self._run["running"] = False
            return pipe, bridge

    def update_run(self, **kwargs: Any) -> None:
        with self._lock:
            self._run.update(kwargs)

    def is_running(self) -> bool:
        with self._lock:
            return bool(self._run.get("running"))

    # ── _lanes 접근자 ──────────────────────────────────────────────

    def get_lanes(self) -> dict:
        with self._lock:
            return dict(self._lanes)

    def lanes_running(self) -> bool:
        with self._lock:
            return bool(self._lanes.get("running"))

    def lanes_epoch(self) -> int:
        with self._lock:
            return self._lanes_epoch

    def start_lanes(self, lane_count: int, rotation: list, mode: str) -> dict:
        with self._lock:
            self._lanes_epoch += 1
            self._lanes.clear()
            self._lanes.update({
                "running": True,
                "threads": [],
                "rotation": rotation,
                "lane_count": lane_count,
                "mode": mode,
                "epoch": self._lanes_epoch,
            })
            return self._lanes   # caller appends threads

    def stop_lanes(self) -> None:
        with self._lock:
            self._lanes["running"] = False

    def append_lane_thread(self, th: Any) -> None:
        with self._lock:
            self._lanes.setdefault("threads", []).append(th)

    # ── _agent 접근자 ──────────────────────────────────────────────

    def get_agent(self) -> dict:
        with self._lock:
            return dict(self._agent)

    def update_agent(self, **kwargs: Any) -> None:
        with self._lock:
            self._agent.update(kwargs)

    # ── 재기동 복원 ────────────────────────────────────────────────

    def restore(self) -> dict:
        """P-core 재기동 시 호출 — 안전측 상태 명시 + 복원 가능 필드 재적용.

        _run·_lanes: 안전측 = False (실행 중 가정 금지 — 물리 라인 무단 재기동 방지).
        _agent.threshold: config 복원 (env 오버라이드 반영).
        OEE·건전성·예지: timeseries에서 복원 — 이 메서드 밖 (pdm_fusion.restore_from_timeseries).
        """
        from aria.core.config import inference as _cfg
        with self._lock:
            self._run["running"] = False
            self._lanes["running"] = False
            self._agent["threshold"] = _cfg.tau_default
            self._agent["status"] = "idle"
            self._agent["is_running"] = True
        return {
            "run_running": False,
            "lanes_running": False,
            "agent_threshold": _cfg.tau_default,
            "note": "안전측 복원 — OEE/건전성은 timeseries, 쿨다운은 pdm_fusion.restore",
        }

    # ── 복합 제어: emergency_stop ──────────────────────────────────

    def emergency_stop(self) -> dict:
        """게이트웨이 /api/action emergency_stop 전용.
        _agent 갱신 + 검사 노드에 정지 신호(reach-in 대신 인터페이스 경유).
        """
        with self._lock:
            self._agent.update({"is_running": False, "status": "stopped"})
            # 검사 노드 정지: TwinState가 소유하는 _run 상태를 직접 변경
            # (state.py → inspector._run reach-in 제거의 핵심)
            pipe = self._run.get("pipe")
            bridge = self._run.get("bridge")
            was_running = self._run.get("running", False)
            self._run["running"] = False
        # lock 밖에서 실제 정지(블로킹 가능)
        if was_running:
            try:
                if pipe:
                    pipe.stop()
                if bridge:
                    bridge.stop()
            except Exception:
                pass
        return {"stopped_lane": was_running}


# 모듈 싱글톤 — inspector.py · state.py 양쪽이 이걸 import
_twin: TwinState = TwinState()


def get_twin() -> TwinState:
    return _twin
