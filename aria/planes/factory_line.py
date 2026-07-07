"""FactoryLine — 현실적 공장 라인 거동 모델 (결정론 · LLM 없음).

컨베이어 속도·택트타임·처리량·가동시간·설비 상태를
① 실 검사 이벤트(inspector_result)와 ② 실측 텔레메트리(GPU 발열/부하)에서 파생한다.

계약 (IMPLEMENTATION_SPEC.md §3-2 "line"/"stats" 참고):
  line  = {conveyor_speed_mps, tact_time_s, transit_time_s,
           throughput_per_min, uptime_s, equipment_status}
  stats = {total, ok, ng, deferred, defect_rate, avg_score, avg_latency_ms,
           line_status, defect_target}

상태기계 (우선순위 내림차순 — 결정론):
  THERMAL_FAULT   GPU thermal == critical (실측)
  MODEL_TRAINING  학습 이벤트 running 또는 GPU load == training (실측)
  QA_ALERT        불량률 > defect_target (워밍업 3개 이후)
  RUNNING         최근 idle_after_s 내 검사 이벤트 존재
  IDLE            그 외

현실 거동 규칙:
  - 발열 감속(derating): hot → ×0.7, critical → ×0.35 컨베이어 감속.
  - tact_time_s = 부품 도착 간격 EMA(α=0.3) — 순간값 아닌 추세.
  - throughput_per_min = 최근 60s 슬라이딩 윈도 실측 집계.
  - 값은 마지막 실측 유지 — 0 리셋·보간 없음 (프로젝트 stale 규칙).
"""
from __future__ import annotations

import threading
import time
from collections import deque

# 발열 → 컨베이어 감속 계수 (결정론 derating)
_SPEED_FACTOR = {"cool": 1.0, "warm": 1.0, "hot": 0.7, "critical": 0.35}

_TACT_ALPHA = 0.3          # 택트 EMA 계수
_TACT_MIN_S = 0.05         # 비정상 간격 클램프(버스트 중복 방지)
_TACT_MAX_S = 30.0
_WINDOW_S = 60.0           # 처리량 슬라이딩 윈도
_WARMUP_PARTS = 3          # line_status WARMUP 구간
_IDLE_AFTER_S = 20.0       # 마지막 부품 후 이 시간 지나면 IDLE


class FactoryLine:
    """라인 1개의 거동 상태. 스레드 안전(내부 lock 하나)."""

    def __init__(self, base_speed_mps: float = 0.5, line_length_m: float = 4.0,
                 defect_target: float = 0.30, station: str = "AI-INSPECT-01"):
        self._lock = threading.Lock()
        self.base_speed_mps = float(base_speed_mps)
        self.line_length_m = float(line_length_m)
        self.defect_target = float(defect_target)
        self.station = station

        self._t0 = time.time()
        self._counts = {"total": 0, "ok": 0, "ng": 0, "deferred": 0}
        self._score_sum = 0.0
        self._score_n = 0
        self._lat_sum = 0.0
        self._lat_n = 0
        self._tact_s: float | None = None
        self._last_part_ts: float | None = None
        self._window: deque = deque()          # 최근 결과 ts (throughput)
        self._seen: set = set()                # part_id 중복 급전 방지
        self._telemetry: dict = {}             # 최신 summary (§3-3)
        self._training_evt = False             # 학습 이벤트(training WS) 기반 플래그

    # ── 급전 (검사 결과 / 학습 이벤트 / 텔레메트리) ─────────────────────

    def on_result(self, part_id=None, verdict=None, score=None,
                  latency_ms=None, ts=None) -> None:
        """검사 결과 1건 반영. OK/NG=검사완료, SKIPPED=보류. 그 외 무시."""
        if verdict not in ("OK", "NG", "SKIPPED"):
            return
        now = float(ts) if ts else time.time()
        with self._lock:
            if part_id:
                if part_id in self._seen:
                    return
                self._seen.add(part_id)
                if len(self._seen) > 512:
                    self._seen.clear()

            self._counts["total"] += 1
            if verdict == "OK":
                self._counts["ok"] += 1
            elif verdict == "NG":
                self._counts["ng"] += 1
            else:
                self._counts["deferred"] += 1

            if score is not None and score >= 0:
                self._score_sum += float(score)
                self._score_n += 1
            if latency_ms is not None:
                self._lat_sum += float(latency_ms)
                self._lat_n += 1

            # 택트 EMA — 도착 간격 추세
            if self._last_part_ts is not None:
                gap = min(max(now - self._last_part_ts, _TACT_MIN_S), _TACT_MAX_S)
                self._tact_s = gap if self._tact_s is None \
                    else (1 - _TACT_ALPHA) * self._tact_s + _TACT_ALPHA * gap
            self._last_part_ts = now

            # 처리량 윈도
            self._window.append(now)
            cutoff = now - _WINDOW_S
            while self._window and self._window[0] < cutoff:
                self._window.popleft()

    def notify_training(self, status) -> None:
        """WS 'training' 이벤트 상태 반영 (running → 학습 중)."""
        with self._lock:
            self._training_evt = status == "running"

    def set_telemetry(self, summary) -> None:
        """최신 텔레메트리 summary(§3-3) 주입. None이면 마지막 값 유지."""
        if not summary:
            return
        with self._lock:
            self._telemetry = dict(summary)

    # ── 파생 (순수 — lock 내부에서만 호출) ──────────────────────────────

    def _thermal(self) -> str:
        return self._telemetry.get("thermal", "cool")

    def _speed_mps(self) -> float:
        return round(self.base_speed_mps * _SPEED_FACTOR.get(self._thermal(), 1.0), 3)

    def _defect_rate(self):
        inspected = self._counts["ok"] + self._counts["ng"]
        return (self._counts["ng"] / inspected) if inspected else None

    def _line_status(self) -> str:
        inspected = self._counts["ok"] + self._counts["ng"]
        if inspected < _WARMUP_PARTS:
            return "WARMUP"
        rate = self._defect_rate() or 0.0
        return "ALERT" if rate > self.defect_target else "NORMAL"

    def _equipment_status(self, now: float) -> str:
        if self._thermal() == "critical":
            return "THERMAL_FAULT"
        if self._training_evt or self._telemetry.get("training"):
            return "MODEL_TRAINING"
        if self._line_status() == "ALERT":
            return "QA_ALERT"
        if self._last_part_ts and (now - self._last_part_ts) <= _IDLE_AFTER_S:
            return "RUNNING"
        return "IDLE"

    # ── 스냅샷 ─────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """{"line": §3-2 line, "stats": §3-2 stats} — WS/REST 공용."""
        now = time.time()
        with self._lock:
            speed = self._speed_mps()
            # 처리량: 윈도 실측 — 가동 60s 미만이면 경과시간으로 정규화
            span = min(_WINDOW_S, max(now - self._t0, 1.0))
            recent = [t for t in self._window if t >= now - _WINDOW_S]
            throughput = len(recent) / span * 60.0
            line = {
                "station": self.station,
                "conveyor_speed_mps": speed,
                "conveyor_speed_factor": _SPEED_FACTOR.get(self._thermal(), 1.0),
                "tact_time_s": round(self._tact_s, 2) if self._tact_s is not None else None,
                "transit_time_s": round(self.line_length_m / speed, 1) if speed > 0 else None,
                "throughput_per_min": round(throughput, 1),
                "uptime_s": round(now - self._t0, 1),
                "equipment_status": self._equipment_status(now),
            }
            stats = {
                **self._counts,
                "defect_rate": round(self._defect_rate(), 4) if self._defect_rate() is not None else None,
                "avg_score": round(self._score_sum / self._score_n, 4) if self._score_n else None,
                "avg_latency_ms": round(self._lat_sum / self._lat_n, 1) if self._lat_n else None,
                "line_status": self._line_status(),
                "defect_target": self.defect_target,
            }
        return {"line": line, "stats": stats}

    def configure(self, base_speed_mps=None, line_length_m=None, defect_target=None) -> dict:
        """운영 파라미터 변경 (양수 검증). 반환 = 현재 설정."""
        with self._lock:
            if base_speed_mps is not None and float(base_speed_mps) > 0:
                self.base_speed_mps = float(base_speed_mps)
            if line_length_m is not None and float(line_length_m) > 0:
                self.line_length_m = float(line_length_m)
            if defect_target is not None and 0 < float(defect_target) <= 1:
                self.defect_target = float(defect_target)
            return {"base_speed_mps": self.base_speed_mps,
                    "line_length_m": self.line_length_m,
                    "defect_target": self.defect_target}

    def reset(self) -> None:
        """카운터/추세 초기화 (설정·텔레메트리는 유지)."""
        with self._lock:
            self._t0 = time.time()
            self._counts = {"total": 0, "ok": 0, "ng": 0, "deferred": 0}
            self._score_sum = self._score_n = 0
            self._lat_sum = self._lat_n = 0
            self._tact_s = None
            self._last_part_ts = None
            self._window.clear()
            self._seen.clear()


# 모듈 싱글톤 — ws 급전 탭 · twin 라우터 양쪽이 이걸 import
_line = FactoryLine()


def get_line() -> FactoryLine:
    return _line
