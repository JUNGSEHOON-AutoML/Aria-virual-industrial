"""공장 트윈 라우터 — 현실 라인 지표 + 실측 텔레메트리.

/api/twin/{snapshot,telemetry,config,reset,step}. 라인 이벤트는 단일 WS(/ws/chat)로
type="line"(2s)·type="telemetry"(6s) 방송 — 프론트 signalStore가 그대로 구독.

급전 경로:
  - inspector_result/training → server.ws._cache 탭 (단일 choke point)
  - GPU 텔레메트리 → line_loop가 주기 주입 (hardware.telemetry)
"""
import asyncio
import time

from fastapi import APIRouter, Body

from server.ws import manager
from aria.planes.factory_line import get_line

router = APIRouter(prefix="/api/twin", tags=["twin"])

LINE_INTERVAL_S = 2.0      # line 방송 주기
TELEMETRY_EVERY = 3        # N틱마다 풀 텔레메트리 방송

_step_seq = 0              # /step 디버그 주입 카운터 (결정론)


@router.get("/snapshot")
async def snapshot():
    """현재 라인 상태 + 텔레메트리 스냅샷 (REST 폴링용)."""
    from hardware.telemetry import get_telemetry
    tel = await asyncio.to_thread(get_telemetry)
    line = get_line()
    line.set_telemetry(tel.get("summary"))
    return {**line.snapshot(), "telemetry": tel.get("summary"), "ts": time.time()}


@router.get("/telemetry")
async def telemetry():
    """풀 텔레메트리 (§3-3) — GPU별 온도/VRAM/util + thermal/load 분류."""
    from hardware.telemetry import get_telemetry
    return await asyncio.to_thread(get_telemetry)


@router.post("/config")
async def config(payload: dict = Body(default={})):
    """라인 운영 파라미터 변경 — base_speed_mps · line_length_m · defect_target."""
    cfg = get_line().configure(
        base_speed_mps=payload.get("base_speed_mps"),
        line_length_m=payload.get("line_length_m"),
        defect_target=payload.get("defect_target"),
    )
    return {"ok": True, **cfg}


@router.post("/reset")
async def reset():
    """카운터/추세 초기화 (설정 유지)."""
    get_line().reset()
    return {"ok": True}


@router.get("/step")
async def step(verdict: str = None):
    """부품 1개 수동 주입(디버그) — 결정론: 7개 중 1개 NG(verdict 쿼리로 강제 가능)."""
    global _step_seq
    _step_seq += 1
    v = verdict if verdict in ("OK", "NG", "SKIPPED") else ("NG" if _step_seq % 7 == 0 else "OK")
    score = 0.72 if v == "NG" else 0.18
    get_line().on_result(part_id=f"STEP{_step_seq:05d}", verdict=v,
                         score=score, latency_ms=40.0)
    snap = get_line().snapshot()
    return {"ok": True, "injected": {"part_id": f"STEP{_step_seq:05d}", "verdict": v}, **snap}


async def line_loop():
    """백그라운드 방송 루프 — app startup에서 asyncio.create_task로 기동.

    매 틱: 텔레메트리 실측 → 라인에 주입 → type="line" 방송(요약 텔레메트리 포함).
    TELEMETRY_EVERY 틱마다 type="telemetry" 풀 페이로드 방송.
    실패해도 루프는 죽지 않는다(다음 틱 재시도).
    """
    from hardware.telemetry import get_telemetry
    tick = 0
    while True:
        try:
            tel = await asyncio.to_thread(get_telemetry)
            line = get_line()
            line.set_telemetry(tel.get("summary"))
            # TRAINER 에이전트 상태도 학습 신호로 반영 (이벤트 유실 대비 벨트&서스펜더)
            tr = (manager.agent_status.get("TRAINER") or {}).get("state")
            if tr in ("running", "done", "idle"):
                line.notify_training(tr)
            msg = {"type": "line", **line.snapshot(),
                   "telemetry": tel.get("summary"), "ts": time.time()}
            await manager.broadcast(msg)
            tick += 1
            if tick % TELEMETRY_EVERY == 0:
                await manager.broadcast({"type": "telemetry", **tel})
        except Exception:
            pass
        await asyncio.sleep(LINE_INTERVAL_S)
