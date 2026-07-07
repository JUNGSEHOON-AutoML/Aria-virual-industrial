"""P-producer 진입점 — 카메라·추론 프로세스 (기본 포트 8201).

실행: uvicorn aria.planes.inspection_node:app --host 0.0.0.0 --port 8201

P-producer 소유:
  - PatchCore/YOLO 모델·뱅크 로딩
  - AsyncPipeline 워커 스레드
  - _trigger_loop / lane_worker 취득 루프
  - IPC bus (bus.publish → HTTP POST → P-core /internal/ingest)

P-core(:8200)이 제어 명령(/api/inspector/*)을 받아 이 FastAPI 앱에도 포함.
단일 프로세스 모드: IPC bus가 localhost:8200에 루프백 POST (P-core = P-producer = 1 proc).
분리 프로세스 모드: ARIA_CORE_URL=http://p-core:8200 설정 후 별도 uvicorn 기동.
"""
from __future__ import annotations
import os
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="ARIA P-producer", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/internal/health")
    async def health():
        from server.routers.inspector import get_last_trigger_ts
        last_ts = get_last_trigger_ts()
        age_s = (time.monotonic() - last_ts) if last_ts > 0 else None
        from aria.core.config import inference as _cfg
        alive = age_s is not None and age_s < _cfg.stale_threshold_s
        return {
            "ok": True,
            "service": "aria-producer",
            "port": int(os.environ.get("PRODUCER_PORT", 8201)),
            "last_tick_ts": round(last_ts, 3) if last_ts else None,
            "tick_age_s": round(age_s, 2) if age_s is not None else None,
            "alive": alive,
        }

    # 검사 제어 라우터 포함 (P-core가 없을 때 standalone 모드용)
    from server.routers import inspector
    app.include_router(inspector.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PRODUCER_PORT", 8201))
    uvicorn.run("aria.planes.inspection_node:app", host="0.0.0.0", port=port, reload=False)
