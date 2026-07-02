"""ARIA API 조립 — create_app(). 구 monolithic app.py 대체 (:8200).

실행: uvicorn server.app:app --host 0.0.0.0 --port 8200
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import asyncio
import logging
import time

from server.config import CORS_ORIGINS, DIST_DIR, API_HOST, API_PORT

_log = logging.getLogger("aria.server")
from server.ws import manager
from server.routers import inspector, sim, classes, dataset, analyze, state, internal
from server.routers.internal import get_producer_last_seen


def create_app() -> FastAPI:
    app = FastAPI(title="ARIA API", version="0.3.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=CORS_ORIGINS,
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )

    for r in (inspector, sim, classes, dataset, analyze, state, internal):
        app.include_router(r.router)

    @app.on_event("startup")
    async def _startup():
        """P-core 재기동 복원 (S3b-2):
        1. TwinState 안전측 상태 명시
        2. pdm_fusion 쿨다운 timeseries 복원 + 서비스 기동
        3. stale heartbeat asyncio task 기동 (S3b-3)
        """
        # 1. TwinState 복원 (안전측: _run·_lanes=False, threshold=config)
        try:
            from aria.planes.twin_state import get_twin
            result = get_twin().restore()
            _log.info("TwinState restored: %s", result)
        except Exception as e:
            _log.warning("TwinState restore failed: %s", e)

        # 2. pdm_fusion 쿨다운 복원 + WS publish 등록 + 서비스 기동
        try:
            from aria.inspection.pdm_fusion import get_fusion
            from aria.core.config import pdm as _pdm_cfg
            loop = asyncio.get_running_loop()
            from server.ws import broadcast_threadsafe
            f = get_fusion(publish=lambda d: broadcast_threadsafe(loop, d))
            cooldown = f.restore_from_timeseries()
            _log.info("PdM fusion cooldown restored: %s", cooldown)
            f.start_service(interval=_pdm_cfg.fusion_interval_s)
        except Exception as e:
            _log.warning("PdM fusion startup failed: %s", e)

        # 3. stale heartbeat — producer 침묵 시 UI에 stale 상태 능동 전파
        asyncio.create_task(_stale_heartbeat())

    async def _stale_heartbeat(interval_s: float = 2.0) -> None:
        """P-producer가 침묵하는 동안 P-core가 주기적으로 stale 상태를 WS에 발행.

        - producer 연결 시: 아무것도 안 함 (inspector가 직접 WS 발행)
        - producer 단절 시: 마지막 known inspector_state + stale=True 재발행
          → UI는 값을 유지하면서 배지만 stale로 전환
        값 규칙: 마지막 실측값 유지 — 0 리셋·보간·N/A 치환 없음.
        """
        from server.routers.internal import (
            get_stale_status,
            get_last_ws_state,
        )
        from server.ws import manager

        while True:
            await asyncio.sleep(interval_s)
            try:
                status = get_stale_status()
                if not status["producer_connected"]:
                    last = get_last_ws_state()
                    if last is not None:
                        # 마지막 inspector_state에 stale 컨텍스트 덮어씌워 재전송
                        heartbeat = {
                            **last,
                            "stale": True,
                            "stale_reason": status["stale_reason"],
                            "age_s": status["age_s"],
                            "producer_connected": False,
                        }
                        await manager.broadcast(heartbeat)
                    else:
                        # producer가 한 번도 신호를 보내지 않은 경우 — 최소 신호 전송
                        await manager.broadcast({
                            "type": "inspector_state",
                            "stale": True,
                            "stale_reason": "producer_disconnected",
                            "age_s": status["age_s"],
                            "producer_connected": False,
                        })
            except Exception as exc:
                _log.debug("stale heartbeat error: %s", exc)

    @app.get("/api/health")
    async def health():
        last_seen = get_producer_last_seen()
        age_s = (time.monotonic() - last_seen) if last_seen > 0 else None
        from aria.core.config import inference as _cfg
        stale_threshold = getattr(_cfg, "stale_threshold_s", 10.0)
        connected = age_s is not None and age_s < stale_threshold
        return {
            "ok": True, "service": "aria-api", "port": API_PORT,
            "routers": ["inspector", "sim", "class", "dataset", "analyze", "state"],
            "producer_connected": connected,
            "producer_last_seen_s": round(age_s, 2) if age_s is not None else None,
        }

    # 단일 WS 신호 채널 (프론트 signalStore 구독). 경로는 기존과 동일 /ws/chat.
    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception:
            manager.disconnect(websocket)

    # 운영: 프론트 빌드(dist) 서빙(있으면). dev는 Vite :5173가 프록시.
    if DIST_DIR.exists():
        assets = DIST_DIR / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/")
        async def root():
            return FileResponse(str(DIST_DIR / "index.html"))

        @app.get("/{full_path:path}")
        async def spa(full_path: str):
            return FileResponse(str(DIST_DIR / "index.html"))

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.app:app", host=API_HOST, port=API_PORT, reload=True)
