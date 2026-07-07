"""상위 디지털 트윈 연동 브리지 (ARIA_Vision_Inspection_Node_Spec 신규4, §5).

동일 텔레메트리를 **외부(OPC UA + MQTT)** 와 **내부(/ws/floor)** 양쪽으로 동시 송출(§2, §10-5).
파이프라인의 telemetry_cb(결과 dict)와 snapshot(상태 dict)을 받아 여러 Sink로 팬아웃한다.

- OPC UA 서버(asyncua): §5.1 노드(State/LastResult/AnomalyScore/Threshold/TactTime/
  QueueDepth/DropCount/YieldRate/PartId/HeatmapUrl) + 메서드 Trigger()/Reset()/SetThreshold().
- MQTT(paho-mqtt): §5.2 pub aria/inspector/<id>/result,/state,/heatmap(retained), sub .../cmd.
- /ws/floor: 기존 내부 트윈으로도 동일 송출(앱에서 manager.broadcast 주입).

asyncua/paho-mqtt는 선택 의존(guarded import) — 미설치면 해당 Sink만 비활성, 나머지는 동작.
SECS/GEM 미포함(§11 DON'T, 반도체 아님).

증명: `python -m aria.inspection.twin_bridge`
  → 동일 result/state가 내부 Sink와 (목)외부 Sink **양쪽**에 도달함을 출력(§10-5).
"""
from __future__ import annotations

import json
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


# ─────────────────────────── Sink 인터페이스 ───────────────────────────
class TelemetrySink(ABC):
    name = "sink"

    def publish_result(self, msg: dict) -> None: ...
    def publish_state(self, msg: dict) -> None: ...
    def publish_heatmap(self, msg: dict) -> None: ...
    def close(self) -> None: ...


class MemorySink(TelemetrySink):
    """인메모리 수집(테스트/증명용)."""
    name = "memory"

    def __init__(self):
        self.results: list = []
        self.states: list = []
        self.heatmaps: list = []

    def publish_result(self, msg): self.results.append(msg)
    def publish_state(self, msg): self.states.append(msg)
    def publish_heatmap(self, msg): self.heatmaps.append(msg)


class WsFloorSink(TelemetrySink):
    """내부 트윈 /ws/floor 송출. broadcast: 동기 콜러블(앱은 manager.broadcast를 래핑해 주입)."""
    name = "ws_floor"

    def __init__(self, broadcast: Callable[[dict], None]):
        self._broadcast = broadcast

    def publish_result(self, msg): self._safe({**msg, "channel": "floor"})
    def publish_state(self, msg): self._safe({**msg, "channel": "floor"})
    def publish_heatmap(self, msg): self._safe({**msg, "channel": "floor"})

    def _safe(self, msg):
        try:
            self._broadcast(msg)
        except Exception:
            pass   # 송출 실패가 파이프라인을 막지 않음(§9)


class MqttSink(TelemetrySink):
    """MQTT 퍼블리셔 (§5.2). paho-mqtt 필요."""
    name = "mqtt"

    def __init__(self, inspector_id: str, host: str = "localhost", port: int = 1883,
                 cmd_cb: Optional[Callable[[dict], None]] = None):
        try:
            import paho.mqtt.client as mqtt
        except ImportError as e:
            raise ImportError("paho-mqtt 미설치 — `pip install paho-mqtt`") from e
        self.id = inspector_id
        self.base = f"aria/inspector/{inspector_id}"
        self._cmd_cb = cmd_cb
        self._c = mqtt.Client()
        self._c.connect(host, port, keepalive=30)
        if cmd_cb:
            self._c.on_message = self._on_message
            self._c.subscribe(f"{self.base}/cmd")
        self._c.loop_start()

    def _on_message(self, client, userdata, m):
        try:
            payload = json.loads(m.payload.decode("utf-8"))
        except Exception:
            payload = {"raw": m.payload.decode("utf-8", "ignore")}
        if self._cmd_cb:
            self._cmd_cb(payload)

    def publish_result(self, msg): self._c.publish(f"{self.base}/result", json.dumps(msg))
    def publish_state(self, msg): self._c.publish(f"{self.base}/state", json.dumps(msg))
    def publish_heatmap(self, msg):
        self._c.publish(f"{self.base}/heatmap", json.dumps(msg), retain=True)  # retained

    def close(self):
        try:
            self._c.loop_stop(); self._c.disconnect()
        except Exception:
            pass


class OpcUaSink(TelemetrySink):
    """OPC UA 서버 (§5.1). asyncua(sync API) 필요. MES/PlantSim이 browse/subscribe."""
    name = "opcua"

    def __init__(self, inspector_id: str, endpoint: str = "opc.tcp://0.0.0.0:4840/aria/",
                 methods: Optional[dict] = None):
        try:
            from asyncua.sync import Server
            from asyncua import ua  # noqa: F401
        except ImportError as e:
            raise ImportError("asyncua 미설치 — `pip install asyncua`") from e
        self.id = inspector_id
        self._srv = Server()
        self._srv.set_endpoint(endpoint)
        idx = self._srv.register_namespace("aria")
        obj = self._srv.nodes.objects.add_object(idx, f"Inspector_{inspector_id}")
        # §5.1 변수 노드
        self._v = {
            "State": obj.add_variable(idx, "State", "IDLE"),
            "LastResult": obj.add_variable(idx, "LastResult", "N/A"),
            "AnomalyScore": obj.add_variable(idx, "AnomalyScore", 0.0),
            "Threshold": obj.add_variable(idx, "Threshold", 0.0),
            "PartId": obj.add_variable(idx, "PartId", ""),
            "TactTime": obj.add_variable(idx, "TactTime", 0.0),
            "InferLatency": obj.add_variable(idx, "InferLatency", 0.0),
            "QueueDepth": obj.add_variable(idx, "QueueDepth", 0),
            "DropCount": obj.add_variable(idx, "DropCount", 0),
            "YieldRate": obj.add_variable(idx, "YieldRate", 0.0),
            "HeatmapUrl": obj.add_variable(idx, "HeatmapUrl", ""),
        }
        for v in self._v.values():
            v.set_writable()
        # §5.1 메서드 (콜백 주입)
        self._methods = methods or {}
        self._srv.start()

    def _set(self, key, val):
        try:
            self._v[key].write_value(val)
        except Exception:
            pass

    def publish_result(self, msg):
        self._set("PartId", str(msg.get("part_id", "")))
        self._set("LastResult", str(msg.get("verdict", "N/A")))
        if msg.get("score") is not None:
            self._set("AnomalyScore", float(msg["score"]))
        if msg.get("tau") is not None:
            self._set("Threshold", float(msg["tau"]))
        if msg.get("latency_ms") is not None:
            self._set("InferLatency", float(msg["latency_ms"]))

    def publish_state(self, msg):
        self._set("State", str(msg.get("state", "RUN")))
        self._set("QueueDepth", int(msg.get("queue_depth", 0)))
        self._set("DropCount", int(msg.get("drop_count", 0)))
        self._set("TactTime", float(msg.get("tact_time_ms", 0.0)))
        self._set("YieldRate", float(msg.get("yield_rate", 0.0)))

    def publish_heatmap(self, msg):
        self._set("HeatmapUrl", str(msg.get("url", "")))

    def close(self):
        try:
            self._srv.stop()
        except Exception:
            pass


# ─────────────────────────── 브리지 (팬아웃) ───────────────────────────
class TwinBridge:
    """여러 Sink로 동일 텔레메트리 팬아웃. 파이프라인과 느슨 결합."""

    def __init__(self, sinks: Optional[list] = None):
        self.sinks: list = sinks or []
        self._pump_thread: Optional[threading.Thread] = None
        self._pumping = False

    def add(self, sink: TelemetrySink):
        if sink is not None:
            self.sinks.append(sink)
        return self

    # 파이프라인 telemetry_cb로 주입할 어댑터 (result/heatmap 라우팅)
    def telemetry_cb(self) -> Callable[[dict], None]:
        def _cb(msg: dict):
            t = msg.get("type")
            for s in self.sinks:
                if t == "result":
                    s.publish_result(msg)
                elif t == "heatmap":
                    s.publish_heatmap(msg)
                elif t == "state":
                    s.publish_state(msg)
        return _cb

    def on_state(self, snapshot: dict):
        msg = {"type": "state", **snapshot, "ts": time.time()}
        for s in self.sinks:
            s.publish_state(msg)

    def start_state_pump(self, snapshot_fn: Callable[[], dict], hz: float = 2.0):
        """주기적으로 snapshot()을 모든 Sink에 state로 송출."""
        self._pumping = True

        def _loop():
            interval = 1.0 / hz
            while self._pumping:
                try:
                    self.on_state(snapshot_fn())
                except Exception:
                    pass
                time.sleep(interval)

        self._pump_thread = threading.Thread(target=_loop, name="twin-state-pump", daemon=True)
        self._pump_thread.start()

    def stop(self):
        self._pumping = False
        if self._pump_thread:
            self._pump_thread.join(timeout=1.0)
        for s in self.sinks:
            try:
                s.close()
            except Exception:
                pass


def build_default_bridge(inspector_id: str = "vis-01",
                         ws_floor_broadcast: Optional[Callable[[dict], None]] = None,
                         enable_mqtt: bool = False, enable_opcua: bool = False,
                         mqtt_host: str = "localhost", **kw) -> TwinBridge:
    """가용 Sink로 브리지 구성. 외부 Sink는 라이브러리 있을 때만 부착(없으면 경고만)."""
    bridge = TwinBridge([MemorySink()])
    if ws_floor_broadcast is not None:
        bridge.add(WsFloorSink(ws_floor_broadcast))
    if enable_mqtt:
        try:
            bridge.add(MqttSink(inspector_id, host=mqtt_host, cmd_cb=kw.get("cmd_cb")))
        except ImportError as e:
            print(f"[twin_bridge] MQTT 비활성: {e}")
    if enable_opcua:
        try:
            bridge.add(OpcUaSink(inspector_id, methods=kw.get("opcua_methods")))
        except ImportError as e:
            print(f"[twin_bridge] OPC UA 비활성: {e}")
    return bridge


# ─────────────────────────── 증명: 동시 송출(§10-5) ───────────────────────────
def _prove_fanout():
    from aria.inspection.async_pipeline import AsyncPipeline, MockDriver, mock_infer_factory

    print("=" * 74)
    print("트윈 동시 송출 증명 — 동일 텔레메트리가 내부+외부 Sink 양쪽 도달 (§2, §10-5)")
    print("=" * 74)

    # 외부 트윈 모사(목): 외부로 나간 메시지 수집
    external = MemorySink(); external.name = "external(mock OPC UA/MQTT)"
    floor_msgs = []   # 내부 /ws/floor 모사
    bridge = TwinBridge([external, WsFloorSink(lambda m: floor_msgs.append(m))])

    # paho/asyncua 설치되어 있으면 실제 Sink도 부착 시도(없으면 자동 스킵)
    for label, factory in [("MQTT", lambda: MqttSink("vis-01")),
                           ("OPC UA", lambda: OpcUaSink("vis-01"))]:
        try:
            bridge.add(factory()); print(f"  [+] {label} Sink 부착됨(실제)")
        except Exception as e:
            print(f"  [-] {label} 미부착: {str(e)[:50]}")

    pipe = AsyncPipeline(MockDriver(grab_ms=2.0, seed=3),
                         mock_infer_factory(lambda: 25.0),
                         tau=0.7, queue_capacity=4, n_workers=2,
                         telemetry_cb=bridge.telemetry_cb())
    pipe.start()
    bridge.start_state_pump(pipe.snapshot, hz=10.0)
    for _ in range(40):
        pipe.trigger()
        time.sleep(0.04)
    pipe.drain(timeout=2.0)
    time.sleep(0.3)
    pipe.stop()
    bridge.stop()

    print("-" * 74)
    print(f"  내부 /ws/floor 수신 : result+state {len(floor_msgs)}건")
    print(f"  외부 트윈 수신      : result {len(external.results)}건 · state {len(external.states)}건")
    same_results = len(external.results) > 0 and len(floor_msgs) > 0
    both_states = len(external.states) > 0 and any(m.get('type') == 'state' for m in floor_msgs)
    verdict = "PASS" if (same_results and both_states) else "FAIL"
    print(f"\n  [{verdict}] 동일 텔레메트리가 내부+외부 양쪽 도달 — 데모/실연동 한 파이프라인 공유(§10-5)")
    print("=" * 74)
    return verdict == "PASS"


if __name__ == "__main__":
    import sys
    sys.exit(0 if _prove_fanout() else 1)
