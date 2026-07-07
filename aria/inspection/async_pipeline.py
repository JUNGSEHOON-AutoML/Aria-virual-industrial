"""비병목 비동기 검사 파이프라인 (ARIA_Vision_Inspection_Node_Spec.md §3, §4).

명세의 1순위: **검사 추론이 라인 인입 속도를 못 따라가도 라인을 멈추지 않는다.**

설계
- Acquisition(트리거→grab→enqueue)과 Inference(dequeue→run→decide)를 분리.
  트리거 ack는 grab 직후 즉시 반환(추론 대기 금지). SLA: 트리거→ack < 20ms (§9).
- Bounded Queue(기본 Q=4): 생산자=grab, 소비자=추론 워커(N개).
- Backpressure: 큐 만재 시 drop-oldest + drop_count++ + 해당 파트 SKIPPED (보수적 라우팅).
- 격리: 추론 예외/타임아웃이 acquisition·telemetry 루프를 죽이지 않음(워커 try/except).
- 노출 지표: tact_time, infer_latency(p95), queue_depth, drop_count, state, yield (§3, §5).

추론 재작성 금지(§11 DON'T): 추론은 `infer_fn(image) -> (score, heatmap)` 으로 **주입**한다.
  - 실제 연동:  infer_fn = lambda img_path: (cosine_score(img_path, bank), heatmap)
                (aria.perception.scorer.feature_bank.cosine_score 재사용)
  - 개발/증명:  MockDriver + mock_infer_factory(지연 주입) — 카메라/GPU 없이 동작.

런타임 증명: `python -m aria.inspection.async_pipeline`
  → 추론을 5× 느리게 해도 트리거 ack가 < 20ms로 유지됨(라인 비병목)을 출력 (§10-1).
"""
from __future__ import annotations

import os
import threading
import time
import random
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ─────────────────────────── 데이터 모델 ───────────────────────────
@dataclass
class Frame:
    part_id: str
    image: Any
    trigger_ts: float
    grab_ts: float


@dataclass
class InspectionResult:
    part_id: str
    verdict: str           # OK | NG | SKIPPED | ERROR
    score: float
    tau: float
    latency_ms: float
    ts: float
    heatmap: Any = None
    defect_class: Optional[str] = None   # YOLO26 결함 종류(있으면)
    bbox: Optional[list] = None          # YOLO26 bbox [x,y,w,h] (있으면)


# ─────────────────────────── 카메라 추상화 (§6) ───────────────────────────
class AcquisitionDriver(ABC):
    """GenICam/GigE 카메라 추상화. grab()은 1프레임 획득 비용만 블로킹."""

    @abstractmethod
    def grab(self) -> Any:
        ...


class MockDriver(AcquisitionDriver):
    """카메라 없이 동작하는 목 드라이버 (§6, §11 BUILD).

    두 모드:
    - image_paths 미지정: 합성 시드 dict 반환(순수 비병목 증명용, torch 불필요).
    - image_paths 지정: 폴더 이미지 경로를 순환 반환(실제 patchcore 추론 end-to-end).
    grab은 짧은 고정 비용만 소모(카메라 grab 모사).
    """

    def __init__(self, grab_ms: float = 2.0, seed: Optional[int] = None,
                 image_paths: Optional[list] = None):
        self.grab_ms = grab_ms
        self._rng = random.Random(seed)
        self.image_paths = list(image_paths) if image_paths else None
        self._i = 0

    def grab(self):
        if self.grab_ms > 0:
            time.sleep(self.grab_ms / 1000.0)
        if self.image_paths:
            p = self.image_paths[self._i % len(self.image_paths)]
            self._i += 1
            return p                       # 실제 이미지 경로 → 디텍터가 추론
        return {"seed": self._rng.random()}


# ─────────────────────────── Bounded Queue + Backpressure (§3) ───────────────────────────
class BoundedFrameQueue:
    """깊이 제한 큐. 만재 시 drop-oldest + drop_count 증가(백프레셔)."""

    def __init__(self, capacity: int = 4):
        self.capacity = capacity
        self._dq: deque = deque()
        self._cond = threading.Condition()
        self.drop_count = 0
        self._stopped = False

    def put(self, item: Frame) -> Optional[Frame]:
        """프레임 적재. 만재면 가장 오래된 것을 드롭하고 그 프레임을 반환(SKIPPED 처리용)."""
        with self._cond:
            dropped = None
            if len(self._dq) >= self.capacity:
                dropped = self._dq.popleft()     # drop-oldest
                self.drop_count += 1
            self._dq.append(item)
            self._cond.notify()
            return dropped

    def get(self, timeout: float = 0.2) -> Optional[Frame]:
        with self._cond:
            deadline = time.perf_counter() + timeout
            while not self._dq and not self._stopped:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)
            return self._dq.popleft() if self._dq else None

    def depth(self) -> int:
        with self._cond:
            return len(self._dq)

    def stop(self):
        with self._cond:
            self._stopped = True
            self._cond.notify_all()


# ─────────────────────────── 메트릭 (§3 노출 지표) ───────────────────────────
class Metrics:
    def __init__(self, window: int = 200):
        self._lock = threading.Lock()
        self.state = "IDLE"
        self._ack_ms: deque = deque(maxlen=window)
        self._infer_ms: deque = deque(maxlen=window)
        self._tact_ms: deque = deque(maxlen=window)
        self._last_trigger: Optional[float] = None
        self.n_trigger = 0
        self.n_ok = 0
        self.n_ng = 0
        self.n_skipped = 0
        self.n_error = 0

    def on_trigger(self, ack_ms: float):
        with self._lock:
            self.n_trigger += 1
            self._ack_ms.append(ack_ms)
            now = time.perf_counter()
            if self._last_trigger is not None:
                self._tact_ms.append((now - self._last_trigger) * 1000.0)
            self._last_trigger = now

    def on_infer(self, latency_ms: float, verdict: str):
        with self._lock:
            self._infer_ms.append(latency_ms)
            if verdict == "OK":
                self.n_ok += 1
            elif verdict == "NG":
                self.n_ng += 1
            elif verdict == "ERROR":
                self.n_error += 1

    def on_skipped(self, n: int = 1):
        with self._lock:
            self.n_skipped += n

    @staticmethod
    def _p95(d: deque) -> float:
        if not d:
            return 0.0
        s = sorted(d)
        idx = min(len(s) - 1, int(round(len(s) * 0.95)) - 1)
        return s[max(0, idx)]

    @staticmethod
    def _avg(d: deque) -> float:
        return sum(d) / len(d) if d else 0.0

    def snapshot(self, queue_depth: int, drop_count: int) -> dict:
        with self._lock:
            judged = self.n_ok + self.n_ng
            # ── OEE 분해(지표 온톨로지): SKIPPED/DROP=가용성, NG=품질 ──
            # 품질(Quality): 검사된 부품 중 양품 비율 (SKIPPED 미혼입)
            quality = (self.n_ok / judged) if judged else 0.0
            # 가용성(Availability): 트리거 대비 실제 검사 비율 (드롭/스킵이 깎음)
            availability = (judged / self.n_trigger) if self.n_trigger else 0.0
            # 성능(Performance): 평균 tact 대비 목표(공칭) — 데이터 없으면 1.0
            perf = 1.0  # 트리거 인터벌 대비 tact는 라우터에서 주입 가능(현재 보수적 1.0)
            oee = availability * perf * quality
            return {
                "state": self.state,
                "tact_time_ms": round(self._avg(self._tact_ms), 2),
                "ack_p95_ms": round(self._p95(self._ack_ms), 3),
                "ack_max_ms": round(max(self._ack_ms), 3) if self._ack_ms else 0.0,
                "infer_latency_p95_ms": round(self._p95(self._infer_ms), 2),
                "queue_depth": queue_depth,
                "drop_count": drop_count,
                "n_trigger": self.n_trigger,
                "n_ok": self.n_ok,
                "n_ng": self.n_ng,
                "n_skipped": self.n_skipped,
                "n_error": self.n_error,
                # 품질만 = 기존 yield_rate(하위호환). + OEE 분해
                "yield_rate": round(quality, 4),
                "quality": round(quality, 4),
                "availability": round(availability, 4),
                "performance": round(perf, 4),
                "oee": round(oee, 4),
            }


# ─────────────────────────── 추론 주입 헬퍼 ───────────────────────────
def mock_infer_factory(latency_ms_provider: Callable[[], float]) -> Callable[[Any], dict]:
    """목 추론기 생성. 지연을 provider로 받아 '느린 추론'을 모사.

    실제 연동 시에는 이 자리에 PatchCoreDetector 등을 감싼 infer_fn을 넣는다(추론 재작성 X).
    반환 계약: dict {score, heatmap, defect_class?, bbox?}."""

    def infer(image: Any) -> dict:
        lat = latency_ms_provider()
        if lat > 0:
            time.sleep(lat / 1000.0)            # 추론 비용 모사 (GIL 해제)
        score = float(image.get("seed", 0.5)) if isinstance(image, dict) else 0.5
        return {"score": score, "heatmap": {"mock_heatmap": True}}

    return infer


# ─────────────────────────── 파이프라인 (§3, §4) ───────────────────────────
class AsyncPipeline:
    def __init__(
        self,
        driver: AcquisitionDriver,
        infer_fn: Callable[[Any], tuple],
        tau: float = 0.7,
        queue_capacity: int = 4,
        n_workers: int = 2,
        telemetry_cb: Optional[Callable[[dict], None]] = None,
    ):
        self.driver = driver
        self.infer_fn = infer_fn
        self.tau = tau
        self.queue = BoundedFrameQueue(queue_capacity)
        self.metrics = Metrics()
        self.n_workers = n_workers
        self.telemetry_cb = telemetry_cb            # twin_bridge가 주입(없으면 무시) — §2 동시 송출 seam
        self._workers: list = []
        self._running = False
        self._part_seq = 0
        self._results: deque = deque(maxlen=512)
        self._results_lock = threading.Lock()

    # --- Acquisition: 트리거→grab→enqueue→즉시 ack (추론 대기 없음) ---
    def trigger(self, part_id: Optional[str] = None) -> dict:
        if part_id is None:
            self._part_seq += 1
            part_id = f"P{self._part_seq:06d}"
        t0 = time.perf_counter()
        img = self.driver.grab()
        frame = Frame(part_id=part_id, image=img, trigger_ts=t0, grab_ts=time.perf_counter())
        dropped = self.queue.put(frame)
        if dropped is not None:
            # 백프레셔: 밀려난 파트는 SKIPPED (보수적으로 수동검사 라우팅)
            self.metrics.on_skipped()
            self._emit({
                "type": "result", "part_id": dropped.part_id, "verdict": "SKIPPED",
                "score": None, "tau": self.tau, "ts": time.time(),
            })
        ack_ms = (time.perf_counter() - t0) * 1000.0
        self.metrics.on_trigger(ack_ms)
        return {"part_id": part_id, "ack_ms": round(ack_ms, 3), "queue_depth": self.queue.depth()}

    # --- Inference 워커: dequeue→run→decide→result→telemetry ---
    def _worker(self):
        while self._running:
            frame = self.queue.get(timeout=0.2)
            if frame is None:
                continue
            t0 = time.perf_counter()
            defect_class, bbox = None, None
            try:
                out = self.infer_fn(frame.image)
                if isinstance(out, dict):
                    score = out.get("score")
                    heatmap = out.get("heatmap")
                    defect_class = out.get("defect_class")
                    bbox = out.get("bbox")
                else:                                   # (score, heatmap) 튜플 하위호환
                    score, heatmap = out
                verdict = "NG" if (score is not None and score > self.tau) else "OK"
            except Exception:
                score, heatmap, verdict = None, None, "ERROR"   # 워커 격리: 예외가 노드를 죽이지 않음
            lat = (time.perf_counter() - t0) * 1000.0
            self.metrics.on_infer(lat, verdict)
            res = InspectionResult(
                part_id=frame.part_id, verdict=verdict,
                score=(score if score is not None else -1.0),
                tau=self.tau, latency_ms=round(lat, 3), ts=time.time(), heatmap=heatmap,
                defect_class=defect_class, bbox=bbox,
            )
            with self._results_lock:
                self._results.append(res)
            # 터미널 추론 로그(ARIA_LOG_RESULTS=1 일 때) — 추론 불변, stdout 한 줄.
            if os.environ.get("ARIA_LOG_RESULTS"):
                cls = f" cls={res.defect_class}" if res.defect_class else ""
                print(f"[INSPECT] {res.part_id} {res.verdict:<3} score={res.score:.3f} "
                      f"tau={res.tau:.2f} {res.latency_ms:6.1f}ms{cls}", flush=True)
            # 2D↔3D 시각화 보강(표현 레이어, 추론 불변) — image/heatmap/peak. 실패해도 무시.
            extra = {}
            try:
                from aria.inspection.result_encode import enrich_result
                extra = enrich_result(frame.image, heatmap)
            except Exception:
                extra = {}
            self._emit({
                "type": "result", "part_id": res.part_id, "verdict": res.verdict,
                "score": res.score, "tau": res.tau, "latency_ms": res.latency_ms,
                "defect_class": res.defect_class, "bbox": res.bbox, "ts": res.ts,
                **extra,
            })

    def _emit(self, msg: dict):
        cb = self.telemetry_cb
        if cb:
            try:
                cb(msg)
            except Exception:
                pass   # 텔레메트리 실패가 파이프라인을 막지 않음(§9)

    def start(self):
        self._running = True
        self.metrics.state = "RUN"
        for i in range(self.n_workers):
            th = threading.Thread(target=self._worker, name=f"infer-{i}", daemon=True)
            th.start()
            self._workers.append(th)

    def stop(self):
        self._running = False
        self.metrics.state = "IDLE"
        self.queue.stop()
        for th in self._workers:
            th.join(timeout=1.0)
        self._workers.clear()

    def drain(self, timeout: float = 2.0):
        """남은 큐가 비워질 때까지 대기(증명/측정용)."""
        deadline = time.perf_counter() + timeout
        while self.queue.depth() > 0 and time.perf_counter() < deadline:
            time.sleep(0.02)

    def snapshot(self) -> dict:
        return self.metrics.snapshot(self.queue.depth(), self.queue.drop_count)

    def results(self) -> list:
        with self._results_lock:
            return list(self._results)


# ─────────────────────────── 런타임 증명 (§10-1 비병목) ───────────────────────────
def _run_scenario(infer_ms: float, label: str, line_interval_ms: float = 40.0,
                  n_parts: int = 60, q: int = 4, workers: int = 2) -> dict:
    infer = mock_infer_factory(lambda: infer_ms)
    pipe = AsyncPipeline(MockDriver(grab_ms=2.0, seed=7), infer,
                         tau=0.7, queue_capacity=q, n_workers=workers)
    pipe.start()
    for _ in range(n_parts):
        t = time.perf_counter()
        pipe.trigger()
        # 라인 인입 페이스 유지(ack 처리시간 제외)
        rem = line_interval_ms - (time.perf_counter() - t) * 1000.0
        if rem > 0:
            time.sleep(rem / 1000.0)
    pipe.drain(timeout=max(1.0, infer_ms / 1000.0 * 4))
    snap = pipe.snapshot()
    pipe.stop()
    snap["_label"] = label
    return snap


def _prove_nonblocking():
    LINE_HZ = 25.0
    interval = 1000.0 / LINE_HZ        # 40ms
    base_ms, slow_ms = 30.0, 150.0     # 5×
    print("=" * 70)
    print(f"비병목 증명 — 라인 인입 {LINE_HZ:.0f} parts/s (간격 {interval:.0f}ms), 워커 2, Q=4")
    print("=" * 70)
    base = _run_scenario(base_ms, f"baseline 추론 {base_ms:.0f}ms", interval)
    slow = _run_scenario(slow_ms, f"5× 느린 추론 {slow_ms:.0f}ms", interval)

    def row(s):
        return (f"  {s['_label']:<22} | ack p95={s['ack_p95_ms']:>6.2f}ms  "
                f"ack max={s['ack_max_ms']:>6.2f}ms | infer p95={s['infer_latency_p95_ms']:>7.2f}ms "
                f"| drop={s['drop_count']:>3} skipped={s['n_skipped']:>3} "
                f"| OK={s['n_ok']} NG={s['n_ng']}")

    print(row(base))
    print(row(slow))
    print("-" * 70)
    SLA = 20.0
    ok_ack = base["ack_max_ms"] < SLA and slow["ack_max_ms"] < SLA
    grew = slow["infer_latency_p95_ms"] > base["infer_latency_p95_ms"] * 2
    backpressure = slow["drop_count"] > 0
    verdict = "PASS" if (ok_ack and grew and backpressure) else "FAIL"
    print(f"  추론 p95 {base['infer_latency_p95_ms']:.0f}ms → {slow['infer_latency_p95_ms']:.0f}ms "
          f"(5× 부하), 그러나 트리거 ack max는 {base['ack_max_ms']:.2f}ms → {slow['ack_max_ms']:.2f}ms "
          f"(둘 다 < {SLA:.0f}ms SLA)")
    print(f"  과부하분은 drop_count={slow['drop_count']}(SKIPPED)로 흡수 — 라인 미정지.")
    print(f"\n  [{verdict}] §10-1 비병목: 추론이 5× 느려져도 트리거 ack는 안 막힘.")
    print("=" * 70)
    return verdict == "PASS"


if __name__ == "__main__":
    import sys
    ok = _prove_nonblocking()
    sys.exit(0 if ok else 1)
