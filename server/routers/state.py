"""상태/하드웨어/에이전트/제어 라우터.
/api/state·/api/hardware·/api/agents/status·/api/action. hardware.monitor 재사용.
(풀 LLM 에이전트 챗 thought/response 는 MCP/Ollama 의존 → 이 트랙 범위 밖, 별도.)
"""
import json
from datetime import datetime

from fastapi import APIRouter, Body

from server.config import ROOT
from server.ws import manager
from aria.planes.twin_state import get_twin as _get_twin

router = APIRouter(prefix="/api", tags=["state"])


def _mcp_servers():
    try:
        cfg = json.loads((ROOT / "mcp_config.json").read_text(encoding="utf-8"))
        return [{"name": n, "enabled": False, "tools": []} for n in (cfg.get("mcpServers") or {}).keys()]
    except Exception:
        return []


@router.get("/state")
async def get_state():
    return {"agent": _get_twin().get_agent(), "mcp_servers": _mcp_servers(),
            "session": "", "memory": "", "timestamp": datetime.now().isoformat()}


@router.get("/hardware")
async def hardware():
    try:
        from hardware.monitor import get_snapshot
        return get_snapshot()
    except Exception as e:
        return {"error": str(e)}


@router.get("/agents/status")
async def agents_status():
    return {k: {"state": v.get("state", "idle"), "detail": v.get("detail", "")}
            for k, v in manager.agent_status.items()}


@router.post("/action")
async def action(payload: dict = Body(...)):
    twin = _get_twin()
    act = payload.get("action", "unknown")
    now = datetime.now().isoformat()
    twin.update_agent(last_action=act)
    if act == "emergency_stop":
        # TwinState.emergency_stop() 이 _agent 갱신 + 검사 노드 정지를 함께 처리.
        # state.py → inspector._run reach-in 완전 제거.
        twin.emergency_stop()
        await manager.broadcast({"type": "agent_status", "agent": "SYSTEM", "state": "idle", "detail": "긴급 정지"})
        return {"result": "emergency_stop_executed", "time": now}
    if act == "approve":
        return {"result": "approved", "time": now}
    if act == "resume":
        twin.update_agent(is_running=True, status="idle")
        return {"result": "resumed", "time": now}
    return {"result": "unknown_action", "action": act}
