"""PdM 융합 서비스(T1-C C3) — 선행(물리 RUL) × 후행(NG 공간) 교차확증.

★독립 서비스: `recent_health()`(시계열) + 주입식 NG 피드/publish만 소비한다.
`app.py` 전역 상태에 의존하지 않음 → 평면 분리의 첫 out-of-process 후보(§11).
출력은 새 WS 타입이 아니라 기존 `diagnostic_result`(kind=predictive) 확장(§5).

정직성 규칙:
- 물리 단독 → 더 이른 주의, confidence ≤ 0.60.
- 물리 + 동일 자산 NG → corroborated, confidence ≤ 0.85(×1.4), RUL은 물리 모델값, NG는 근거.
- NG 단독 → ≤0.60 + note "물리 신호 미확인"(T1-B 성격 유지), RUL 없음.
- RUL은 항상 밴드 + 확인요망. 난수 없음(결정론적 입력 → 결정론적 가설).
"""
from __future__ import annotations
import threading
import time
from collections import deque

from aria.inspection.timeseries import recent_health, health_assets, record_episode
from aria.inspection import health_features as hf
from aria.inspection.rul_estimator import estimate as rul_estimate

CORROB_CONF_CAP = 0.85
PHYS_CONF_CAP = 0.60
CORROB_MULT = 1.4

_ASSET_ACTION = {
    "robot_arm":      "해당 관절 점검·재윤활 / 재교정",
    "vision_camera":  "카메라 재교정·렌즈 점검",
    "conveyor_motor": "모터 점검·벨트 장력 확인",
}


def _action_for(asset_id: str) -> str:
    for k, v in _ASSET_ACTION.items():
        if asset_id.startswith(k):
            return v
    return "설비 점검"


class PdMFusion:
    def __init__(self, recent_fn=recent_health, assets_fn=health_assets,
                 estimate_fn=rul_estimate, features_fn=hf.extract,
                 publish=None, episode_fn=record_episode,
                 window_min: int = 30, cooldown_s: float = 120.0, ng_window_s: float = 600.0,
                 ng_min: int = 3):
        self.recent_fn = recent_fn
        self.assets_fn = assets_fn
        self.estimate_fn = estimate_fn
        self.features_fn = features_fn
        self.publish = publish or (lambda d: None)
        self.episode_fn = episode_fn
        self.window_min = window_min
        self.cooldown_s = cooldown_s
        self.ng_window_s = ng_window_s
        self.ng_min = ng_min
        self._ng = {}                 # asset_id -> deque[(ts, cell)]
        self._last_emit = {}          # asset_id -> ts (쿨다운)
        self._lock = threading.Lock()
        self._thread = None
        self._running = False

    # ── 후행(NG) 피드: inspector NG 결과가 호출 ──
    def note_ng(self, asset_id: str, cell, ts: float | None = None):
        ts = ts or time.time()
        with self._lock:
            dq = self._ng.setdefault(asset_id, deque(maxlen=256))
            dq.append((ts, str(cell) if cell is not None else "?"))

    def _ng_evidence(self, asset_id: str, now: float):
        """창 내 NG 집계 → {cell, window} 또는 None(정직: 근거 부족 시 없음)."""
        with self._lock:
            dq = self._ng.get(asset_id)
            recent = [(t, c) for (t, c) in (dq or []) if now - t <= self.ng_window_s]
        if len(recent) < self.ng_min:
            return None
        # 최빈 셀
        counts = {}
        for _, c in recent:
            counts[c] = counts.get(c, 0) + 1
        top_cell, top_n = max(counts.items(), key=lambda kv: kv[1])
        return {"cell": top_cell, "window": f"{top_n}/{len(recent)} NG"}

    def run_once(self, now: float | None = None) -> list:
        now = now or time.time()
        emitted = []
        for asset in self.assets_fn(self.window_min):
            rows = self.recent_fn(asset, self.window_min)
            feats = self.features_fn(rows)
            est = self.estimate_fn(rows, asset, features=feats)
            ng = self._ng_evidence(asset, now)
            has_phys = bool(est and est["rul"]["est_hours"] is not None)
            if not has_phys and ng is None:
                continue

            # 쿨다운(자산별)
            if now - self._last_emit.get(asset, 0.0) < self.cooldown_s:
                continue

            hyp = self._build(asset, est, ng, has_phys, now)
            self._last_emit[asset] = now
            try:
                self.episode_fn(hyp)
            except Exception:
                pass
            try:
                self.publish(hyp)
            except Exception:
                pass
            emitted.append(hyp)
        return emitted

    def _build(self, asset, est, ng, has_phys, now) -> dict:
        corroborated = bool(has_phys and ng is not None)
        if has_phys:
            phys_conf = est["confidence"]
            conf = min(CORROB_CONF_CAP, phys_conf * CORROB_MULT) if corroborated else min(PHYS_CONF_CAP, phys_conf)
            health = est["health_index"]
            rul = est["rul"]
            leading = est["leading_signals"]
            note = est["note"]
        else:
            # NG 단독 — T1-B 성격(≤0.6), 물리 미확인
            conf = min(PHYS_CONF_CAP, 0.45)
            health = None
            rul = {"est_hours": None, "lo": None, "hi": None, "model": "none"}
            leading = []
            note = "확인요망 · 물리 신호 미확인(NG 패턴만)"
        return {
            "type": "diagnostic_result", "kind": "predictive",
            "asset": asset, "health_index": health, "rul": rul,
            "leading_signals": leading, "corroborated": corroborated,
            "ng_evidence": ng, "confidence": round(conf, 3),
            "note": note, "recommended_action": _action_for(asset),
            "ts": now,
        }

    # ── 재기동 복원 ──────────────────────────────────────────────────────────
    def restore_from_timeseries(self, minutes: int = 1440) -> dict:
        """P-core 재기동 시 호출 — recent_episodes에서 자산별 마지막 emit 시각 복원.

        쿨다운(_last_emit)을 복원해 재기동 직후 같은 가설이 중복 발화하지 않게 함.
        _ng(NG 이벤트 큐)는 영속화 안 됨 → 재기동 후 새로 쌓기 시작(수용).
        IPC 버퍼 재전송 레코드가 timeseries에 쌓인 뒤에 이 메서드가 불려도 안전
        — last emit ts를 덮어쓸 뿐 가설을 생성하지 않음.
        """
        try:
            from aria.inspection.timeseries import recent_episodes
            episodes = recent_episodes(minutes=minutes)
            restored: dict = {}
            for ep in episodes:  # DESC 정렬이므로 첫 번째 = 최신
                asset = ep.get("asset")
                ts = ep.get("ts")
                if asset and ts and asset not in restored:
                    restored[asset] = ts
            with self._lock:
                self._last_emit.update(restored)
            return {"restored_assets": list(restored.keys()), "count": len(restored)}
        except Exception as e:
            return {"error": str(e), "count": 0}

    # ── 백그라운드 서비스(선택) ──
    def start_service(self, interval: float = 5.0):
        if self._running:
            return
        self._running = True

        def _loop():
            while self._running:
                try:
                    self.run_once()
                except Exception:
                    pass
                time.sleep(interval)

        self._thread = threading.Thread(target=_loop, name="pdm-fusion", daemon=True)
        self._thread.start()

    def stop_service(self):
        self._running = False


# ── 모듈 싱글톤(inspector가 note_ng·서비스 기동에 사용) ──
_fusion = None
_flock = threading.Lock()


def get_fusion(publish=None) -> PdMFusion:
    global _fusion
    with _flock:
        if _fusion is None:
            _fusion = PdMFusion(publish=publish)
        elif publish is not None:
            _fusion.publish = publish
    return _fusion
