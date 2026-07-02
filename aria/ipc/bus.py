"""IPC 버퍼·어댑터 — publish(kind, payload)가 유일한 인터페이스.

구현은 어댑터 뒤에 숨는다. 현재: HTTP POST 배치.
HIL 단계: set_adapter()로 OPC UA/MQTT 교체 — 호출부 불변.

설계 불변:
  - publish()는 절대 블록 안 됨 (deque append → 즉시 반환)
  - overflow 시 oldest silent-drop (backpressure 없는 텔레메트리)
  - 유실은 조용하지 않음: kind별 카운터 + 다음 성공 flush 시 WARNING 로그
  - 각 이벤트에 단조 seq 부여 → P-core 수신측 dedup (at-least-once → effectively-once)
  - POST 실패 시 batch 앞쪽 재삽입 (순서 보존, P-core 재기동 중 유실 없음)

용량 참고 (2026-07-02 실측):
  단일레인 ~12 ev/s → maxlen=2000 ≈ 2.8분 버퍼
  3레인    ~15 ev/s → maxlen=2000 ≈ 2.2분 버퍼
  환경변수 ARIA_IPC_BUFFER_MAXLEN 으로 확장 가능.

ng 우선순위 결정:
  현재: record/health/ng/ws 단일 큐. ng 유실은 overflow WARNING에 ng= 항목으로 가시화.
  구조 분리(priority queue)는 24h 라이프사이클 후 ng 유실이 드리프트 감지에
  실제로 영향을 줄 시점에 결정. 지금은 가시화로 정직성 확보.
"""
from __future__ import annotations
import collections
import logging
import os
import threading
import time

_log = logging.getLogger("aria.ipc.bus")


class _HttpAdapter:
    """HTTP POST 배치 어댑터. requests lazy import."""

    def __init__(self, url: str, timeout_s: float = 2.0) -> None:
        self._url = url
        self._timeout = timeout_s

    def send(self, batch: list) -> bool:
        try:
            import requests  # noqa: PLC0415
            r = requests.post(self._url, json={"events": batch}, timeout=self._timeout)
            return r.status_code < 300
        except Exception:
            return False


class IpcBus:
    """단방향 P-producer → P-core 버퍼·어댑터.

    publish(kind, payload) — 절대 블록 안 됨. deque append 후 즉시 반환.
    set_adapter(adapter) — 전송 구현 교체 (HTTP → OPC UA/MQTT 등).
    start() — flush background thread 시작 (멱등).
    get_stats() — overflow/seq 현황 조회.
    """

    def __init__(
        self,
        adapter=None,
        maxlen: int = 2000,
        flush_interval_s: float = 0.05,
    ) -> None:
        self._buf: collections.deque = collections.deque(maxlen=maxlen)
        self._adapter = adapter
        self._interval = flush_interval_s
        self._th: threading.Thread | None = None

        # 단조 이벤트 번호 — P-core 수신측 dedup 키
        self._seq: int = 0
        self._seq_lock = threading.Lock()

        # 오버플로 카운터 — 유실이 조용하지 않게
        self._overflow_count: int = 0
        self._overflow_by_kind: dict = {}
        self._overflow_lock = threading.Lock()

    def set_adapter(self, adapter) -> None:
        """전송 어댑터 교체 — HIL 단계에서 사용."""
        self._adapter = adapter

    def publish(self, kind: str, payload: dict) -> None:
        """절대 블록 안 됨. overflow 시 oldest 자동 drop + 카운터 증가.

        카운터는 drop되는 oldest 항목의 kind로 기록.
        (새로 들어오는 kind가 아님 — ng가 drop됐는지를 정확히 추적하기 위함)
        """
        with self._seq_lock:
            self._seq += 1
            seq = self._seq
        # overflow: buf 꽉 찼으면 oldest가 drop됨 → oldest의 kind 카운트
        if len(self._buf) >= self._buf.maxlen:
            dropped_kind = self._buf[0].get("kind", "unknown") if self._buf else "unknown"
            with self._overflow_lock:
                self._overflow_count += 1
                self._overflow_by_kind[dropped_kind] = self._overflow_by_kind.get(dropped_kind, 0) + 1
        self._buf.append({"kind": kind, "payload": payload, "ts": time.monotonic(), "seq": seq})

    def start(self) -> None:
        """flush background daemon thread 시작 (멱등)."""
        if self._th and self._th.is_alive():
            return
        self._th = threading.Thread(
            target=self._flush_loop, name="ipc-flush", daemon=True
        )
        self._th.start()

    def get_stats(self) -> dict:
        """현재 버퍼 상태 + 누적 overflow 현황."""
        with self._overflow_lock:
            return {
                "buf_size": len(self._buf),
                "buf_maxlen": self._buf.maxlen,
                "overflow_total": self._overflow_count,
                "overflow_by_kind": dict(self._overflow_by_kind),
                "seq": self._seq,
            }

    def _flush_loop(self) -> None:
        while True:
            time.sleep(self._interval)
            if not self._buf or not self._adapter:
                continue
            # GIL 보호 아래 deque에서 전부 꺼내기
            batch: list = []
            while self._buf:
                try:
                    batch.append(self._buf.popleft())
                except IndexError:
                    break
            if not batch:
                continue
            ok = self._adapter.send(batch)
            if ok:
                # 성공 flush 시 overflow 경고 방출 (다음 성공 flush 때까지 누적)
                with self._overflow_lock:
                    if self._overflow_count > 0:
                        ng_lost = self._overflow_by_kind.get("ng", 0)
                        _log.warning(
                            "IPC buffer overflow — %d events dropped "
                            "(ng=%d record=%d health=%d ws=%d); "
                            "P-core 재기동 전 %.0fs 이상 끊김으로 추정",
                            self._overflow_count,
                            ng_lost,
                            self._overflow_by_kind.get("record", 0),
                            self._overflow_by_kind.get("health", 0),
                            self._overflow_by_kind.get("ws", 0),
                            self._overflow_count / 12.0,  # 단일레인 기준 추정 초
                        )
                        if ng_lost > 0:
                            _log.warning(
                                "ng 이벤트 %d건 유실 — 예지 가설 누락 가능. "
                                "24h 트랙에서 ng 우선큐 분리 검토 필요",
                                ng_lost,
                            )
                        self._overflow_count = 0
                        self._overflow_by_kind.clear()
            else:
                # POST 실패 → 앞쪽 재삽입 (순서 보존, maxlen 초과분 silent drop)
                for ev in reversed(batch):
                    self._buf.appendleft(ev)
                _log.debug("IPC flush failed — %d events requeued", len(batch))


# ── 모듈 싱글톤 (P-producer 측) ────────────────────────────────────────────

_bus: IpcBus | None = None
_bus_lock = threading.Lock()


def get_bus() -> IpcBus:
    """P-producer 싱글톤. ARIA_CORE_URL / ARIA_IPC_BUFFER_MAXLEN 환경변수."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                url = os.environ.get("ARIA_CORE_URL", "http://localhost:8200")
                maxlen = int(os.environ.get("ARIA_IPC_BUFFER_MAXLEN", "2000"))
                _bus = IpcBus(
                    adapter=_HttpAdapter(f"{url}/internal/ingest"),
                    maxlen=maxlen,
                )
                _bus.start()
    return _bus
