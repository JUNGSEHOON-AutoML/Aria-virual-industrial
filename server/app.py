"""ARIA API 조립 — create_app(). 구 monolithic app.py 대체 (:8200).

실행: uvicorn server.app:app --host 0.0.0.0 --port 8200
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import asyncio
import time

from server.config import CORS_ORIGINS, DIST_DIR, API_HOST, API_PORT
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
        """P-core 시작 시 pdm_fusion 서비스 기동 (P-producer의 NG IPC 수신 준비)."""
        try:
            from aria.inspection.pdm_fusion import get_fusion
            from aria.core.config import pdm as _pdm_cfg
            loop = asyncio.get_running_loop()
            from server.ws import broadcast_threadsafe
            f = get_fusion(publish=lambda d: broadcast_threadsafe(loop, d))
            f.start_service(interval=_pdm_cfg.fusion_interval_s)
        except Exception:
            pass

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
