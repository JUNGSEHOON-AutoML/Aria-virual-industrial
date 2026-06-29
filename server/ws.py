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
