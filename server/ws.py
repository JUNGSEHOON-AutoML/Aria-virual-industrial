"""단일 WebSocket 신호 채널 — 프론트 signalStore가 구독하는 유일한 실시간 소스."""
import asyncio
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self.agent_status: dict = {}   # agent → {state, detail} 캐시(/api/agents/status가 읽음)

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    def _cache(self, message: dict):
        if message.get("type") == "agent_status" and message.get("agent"):
            self.agent_status[message["agent"]] = {
                "state": message.get("state", "idle"), "detail": message.get("detail", ""),
            }
        self._feed_factory_line(message)

    @staticmethod
    def _feed_factory_line(message: dict):
        """FactoryLine 급전 — 검사 결과·학습 이벤트를 라인 지표로 (단일 choke point).
        급전 실패가 방송을 막지 않는다."""
        t = message.get("type")
        if t not in ("inspector_result", "training"):
            return
        try:
            from aria.planes.factory_line import get_line
            if t == "inspector_result":
                # 중복 키 = 레인+part_id+ts. 파이프라인 재기동(클래스 순환)마다 part_id가
                # P000001부터 재발번되므로 ts를 포함해야 정당한 재사용이 집계에서 누락되지 않는다.
                # (막는 대상은 동일 메시지의 문자 그대로의 재수신뿐)
                pid = message.get("part_id")
                if pid is not None:
                    pid = f"L{message.get('lane', 0)}:{pid}:{message.get('ts', '')}"
                get_line().on_result(
                    part_id=pid, verdict=message.get("verdict"),
                    score=message.get("score"), latency_ms=message.get("latency_ms"),
                )
            else:
                get_line().notify_training(message.get("status"))
        except Exception:
            pass

    async def broadcast(self, message: dict):
        self._cache(message)   # 모든 브로드캐스트의 단일 choke point → agent_status 캐시 동기
        for c in list(self.active):
            try:
                await c.send_json(message)
            except Exception:
                self.disconnect(c)


manager = ConnectionManager()


def broadcast_threadsafe(loop, message: dict):
    """워커 스레드에서 안전하게 브로드캐스트(추론 스레드 → WS)."""
    try:
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), loop)
    except Exception:
        pass
