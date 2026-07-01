"""IPC 버퍼·어댑터 — publish(kind, payload)가 유일한 인터페이스.

구현은 어댑터 뒤에 숨는다. 현재: HTTP POST 배치.
HIL 단계: set_adapter()로 OPC UA/MQTT 교체 — 호출부 불변.

설계 불변:
  - publish()는 절대 블록 안 됨 (deque append → 즉시 반환)
  - overflow 시 oldest silent-drop (backpressure 없는 텔레메트리)
  - POST 실패 시 batch 재삽입 (P-core 재기동 중 유실 없음)
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

    def set_adapter(self, adapter) -> None:
        """전송 어댑터 교체 — HIL 단계에서 사용."""
        self._adapter = adapter

    def publish(self, kind: str, payload: dict) -> None:
        """절대 블록 안 됨. overflow 시 oldest 자동 drop."""
        self._buf.append({"kind": kind, "payload": payload, "ts": time.monotonic()})

    def start(self) -> None:
        """flush background daemon thread 시작 (멱등)."""
        if self._th and self._th.is_alive():
            return
        self._th = threading.Thread(
            target=self._flush_loop, name="ipc-flush", daemon=True
        )
        self._th.start()

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
            if not ok:
                # POST 실패 → 앞쪽에 재삽입 (maxlen 초과분 silent drop)
                for ev in reversed(batch):
                    self._buf.appendleft(ev)
                _log.debug("IPC flush failed — %d events requeued", len(batch))


# ── 모듈 싱글톤 (P-producer 측) ────────────────────────────────────────────

_bus: IpcBus | None = None
_bus_lock = threading.Lock()


def get_bus() -> IpcBus:
    """P-producer 싱글톤. ARIA_CORE_URL 환경변수로 P-core URL 지정."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                url = os.environ.get("ARIA_CORE_URL", "http://localhost:8200")
                _bus = IpcBus(adapter=_HttpAdapter(f"{url}/internal/ingest"))
                _bus.start()
    return _bus
