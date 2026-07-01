"""
⚠️ [DEPRECATED 2026-07-01 — B5 컷오버 완료]
이 파일은 레거시 진입점(:8080)입니다. 더 이상 uvicorn 기동 대상이 아닙니다.
  - 현재 진입점: server/app.py (:8200)
  - 기동 스크립트: start_aria.sh (server.app:app --port 8200)

파일이 남아있는 이유: aria/agents/*.py · aria/mcp/*.py 가 내부에서 lazy import
(try/except 감싸진 get_engine 등)를 사용하므로 삭제 시 에러 방지 목적.
이 임포트들도 T2B/에이전트 트랙에서 server/ 기반으로 이관될 때 이 파일을 최종 삭제합니다.

app.py — ARIA (Anomaly Reasoning Intelligence Agent) 실시간 모니터링 대시보드 (FastAPI 백엔드) [구버전]

역할:
  1. /video_feed — MJPEG 스트리밍 (웹캠 + Anomaly Score 오버레이)
  2. /api/state — SESSION.md & MEMORY.md를 JSON으로 반환
  3. /api/action — 프론트엔드 제어 신호 수신 (강제정지/승인)

사용법:
  conda activate patchcore
  uvicorn app:app --host 0.0.0.0 --port 8000 --reload
"""

import json
import os
import asyncio
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
import torchvision.models as models
import torchvision.transforms as transforms
from fastapi import FastAPI, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from aria.agents.autonomous_agent import AutonomousAgent
from aria.mcp.mcp_client import MCPClient, load_env
from aria.core.database import init_db, SessionLocal, AnalysisHistory, AgentMemory
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()

# ── 메모리 뱅크 경로 ─────────────────────────────────────────────────────
# 탐색 우선순위: ① 환경변수 MEMORY_BANK_PATH → ② 로컬 memory_bank_t95.npy → ③ memory_bank.npy
_env_memory = os.environ.get("MEMORY_BANK_PATH", "")
if _env_memory and os.path.exists(_env_memory):
    MEMORY_BANK_PATH = _env_memory
elif os.path.exists(str(BASE_DIR / "memory_bank_t95.npy")):
    MEMORY_BANK_PATH = str(BASE_DIR / "memory_bank_t95.npy")
else:
    MEMORY_BANK_PATH = str(BASE_DIR / "memory_bank.npy")


THRESHOLD = 15.0
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────
# FastAPI 앱
# ──────────────────────────────────────────────
app = FastAPI(title="ARIA Anomaly Watch Center", version="1.0.0")

# ──────────────────────────────────────────────
# CORS 설정
# React 개발 서버(localhost:5173), 스테이징(5174), Vercel 프로덕션 도메인 허용
# ──────────────────────────────────────────────
CORS_ORIGINS = [
    "http://localhost:5173",        # Vite 개발 서버
    "http://localhost:5174",        # Vite 대체 포트
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://localhost:3000",        # CRA / Next.js 개발 서버
    "https://*.vercel.app",         # Vercel 프로덕션/프리뷰 배포
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",  # Vercel 서브도메인 전체 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")

# 전역 상태
agent_state = {
    "score": 0.0,
    "threshold": THRESHOLD,
    "status": "idle",
    "fps": 0.0,
    "is_running": True,
    "loop_count": 0,
    "last_action": None,
    "last_action_time": None,
}
state_lock = threading.Lock()

latest_stats = {
    "stats": {
        "score": 0.0,
        "mean": 0.0,
        "variance": 0.0,
        "ci_lower": 0.0,
        "ci_upper": 0.0,
    },
    "pca_data": {
        "normal": [],
        "query": []
    }
}

# [LED] 에이전트 상태 캐시 — idle 초기값으로 시작
# Frontend AgentSwarm이 기대하는 {state, detail} 포맷으로 채운다
agent_status_cache = {
    "router":      {"state": "idle", "detail": "대기 중"},
    "vision":      {"state": "idle", "detail": "대기 중"},
    "scout":       {"state": "idle", "detail": "대기 중"},
    "detector":    {"state": "idle", "detail": "대기 중"},
    "debate":      {"state": "idle", "detail": "대기 중"},
    "research":    {"state": "idle", "detail": "대기 중"},
    "code":        {"state": "idle", "detail": "대기 중"},
    "verifier":    {"state": "idle", "detail": "대기 중"},
    "synthesizer": {"state": "idle", "detail": "대기 중"},
}
# ──────────────────────────────────────────────
# Pydantic JSON 응답 규격 정의
# ──────────────────────────────────────────────
class AgentStateModel(BaseModel):
    score: float
    threshold: float
    status: str
    fps: float
    is_running: bool
    loop_count: int
    last_action: Optional[str] = None
    last_action_time: Optional[str] = None

class StateResponse(BaseModel):
    agent: AgentStateModel
    session: str
    memory: str
    timestamp: str
    mcp_servers: Optional[list] = None

class PCAData(BaseModel):
    normal: List[List[float]]
    query: List[List[float]]

class StatsData(BaseModel):
    score: Optional[float] = None
    mean: Optional[float] = None
    variance: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None

class AnalyzeResponse(BaseModel):
    # [§1] 일반 이미지는 score/threshold/defect_prob가 None일 수 있습니다
    image_domain: Optional[str] = None      # "general_object" | "industrial_anomaly"
    score: Optional[float] = None
    anomaly_score: Optional[float] = None
    threshold: Optional[float] = None
    defect_probability_percent: Optional[int] = None
    status: str
    filename: str
    model_used: str
    model_type: str
    render_type: str
    heatmap_url: str
    auto_mode: bool
    vlm_scene: str
    model_discussion: str
    defect_location_description: str
    scout_log: List[str]
    scout_meta: Dict[str, Any]
    stats: StatsData
    pca_data: PCAData
    inference_time_ms: int

class ThoughtRecord(BaseModel):
    type: str
    content: Optional[str] = None
    tool: Optional[str] = None
    result: Optional[str] = None

class ChatResponse(BaseModel):
    status: str
    reply: str
    thoughts: List[ThoughtRecord]

class ActionResponse(BaseModel):
    result: str
    time: str

class MCPCallRequest(BaseModel):
    tool_name: str
    params: dict = {}


# ──────────────────────────────────────────────
# WebSocket 및 MCP 전역 제어
# ──────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

mcp_client = None
agent = None
mcp_status = "stopped"  # stopped, starting, running, error

def start_mcp_in_background():
    """
    MCP 서버를 2단계로 기동한다.
    1단계: 필수 서버(filesystem, shell_exec, web_search, arxiv) — 즉시 기동
    2단계: 선택 서버(huggingface, youtube, 등) — 10초 지연 후 기동
    하나가 실패해도 나머지에 영향 없음.
    """
    global mcp_client, agent, mcp_status
    mcp_status = "starting"

    # 필수 MCP 서버 목록 (mcp_config.json에 존재하는 서버 목록 기준)
    ESSENTIAL_SERVERS = ["filesystem", "system", "database"]
    OPTIONAL_SERVERS  = ["huggingface"]

    try:
        load_env()
        mcp_client = MCPClient("mcp_config.json")

        # ── 1단계: 필수 서버 기동 ──
        print("[MCP] ① 필수 MCP 서버 기동 중...")
        essential_results = mcp_client.start_servers(server_names=ESSENTIAL_SERVERS)
        running = [k for k, v in essential_results.items() if v]
        failed  = [k for k, v in essential_results.items() if not v]
        print(f"[MCP] 필수 서버 완료 — 성공: {running}, 실패: {failed}")

        # 에이전트는 필수 서버만 올라와도 즉시 사용 가능
        agent = AutonomousAgent(mcp_client=mcp_client)
        mcp_status = "running"
        print("[MCP] ✅ 에이전트 초기화 완료 (필수 서버 기준)")

        # ── 2단계: 선택 서버 지연 기동 (별도 스레드) ──
        def _start_optional():
            time.sleep(10)  # 10초 대기 후 선택 서버 기동
            print("[MCP] ② 선택 MCP 서버 지연 기동 중...")
            opt_results = mcp_client.start_servers(server_names=OPTIONAL_SERVERS)
            opt_running = [k for k, v in opt_results.items() if v]
            opt_failed  = [k for k, v in opt_results.items() if not v]
            print(f"[MCP] 선택 서버 완료 — 성공: {opt_running}, 실패(무시): {opt_failed}")

        threading.Thread(target=_start_optional, daemon=True).start()

    except Exception as e:
        mcp_status = "error"
        print(f"[MCP] 백그라운드 서버 기동 중 에러 발생: {e}")
        import traceback
        traceback.print_exc()



# ──────────────────────────────────────────────
# CCIFPS Vision Engine 및 CCIFPSEngine 클래스가 제거되었습니다.
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# .md 파일 읽기
# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# 데이터베이스 기반 세션 및 메모리 텍스트 구성
# ──────────────────────────────────────────────
def get_session_db_text():
    db = SessionLocal()
    try:
        histories = db.query(AnalysisHistory).order_by(AnalysisHistory.timestamp.desc()).limit(20).all()
        if not histories:
            return "# 🔄 Current Session State\n\n> 아직 검사 이력이 기록되지 않았습니다."
        
        lines = ["# 🔄 Current Session State (SQLite DB)"]
        for h in histories:
            lines.append(f"### [ID: {h.id}] {h.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"- **Domain**: {h.domain_type}")
            lines.append(f"- **Image Path**: `{h.image_path}`")
            lines.append(f"- **Anomaly Score**: `{h.score:.3f}`")
            lines.append(f"- **Defect Probability**: `{h.defect_probability}%`")
            if h.heatmap_url:
                lines.append(f"- **Heatmap URL**: [Link]({h.heatmap_url})")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error loading session: {e}"
    finally:
        db.close()

def get_memory_db_text():
    db = SessionLocal()
    try:
        memories = db.query(AgentMemory).order_by(AgentMemory.timestamp.desc()).limit(30).all()
        if not memories:
            return "# 🧠 Memory Core\n\n> 아직 인지 이벤트가 기록되지 않았습니다."
        
        # 최신 기록이 아래로 오도록 반전
        memories = list(reversed(memories))
        lines = ["# 🧠 Memory Core (SQLite DB)"]
        for m in memories:
            lines.append(f"### [{m.role.upper()}] {m.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"- {m.content}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error loading memory: {e}"
    finally:
        db.close()

def append_memory_event(event_type, detail):
    """AgentMemory 테이블에 이벤트 추가."""
    db = SessionLocal()
    try:
        memory = AgentMemory(
            session_id="default",
            role="agent" if event_type != "error" else "tool",
            content=f"[{event_type.upper()}] {detail}"
        )
        db.add(memory)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[DB] append_memory_event 에러: {e}")
    finally:
        db.close()


# ──────────────────────────────────────────────
# MJPEG 비디오 스트리밍 (추론 로직이 제거되고 단순 카메라 피드로 단순화)
# ──────────────────────────────────────────────

def generate_frames():
    """MJPEG 프레임 생성기. 웹캠 프레임 단순 바이패스."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        # 웹캠 없을 때 더미 프레임 생성
        while agent_state["is_running"]:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "No Camera Available",
                        (120, 230), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                        (100, 100, 100), 2)
            cv2.putText(frame, "Connect webcam and restart",
                        (100, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (80, 80, 80), 1)
            _, buf = cv2.imencode(".jpg", frame)
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" +
                   buf.tobytes() + b"\r\n")
            time.sleep(0.1)
        return

    frame_count = 0
    fps_start = time.time()
    fps = 0.0

    while agent_state["is_running"]:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.03)
            continue

        # 추론 제거, 상시 정상으로 상태 업데이트
        score = 0.0
        status = "normal"
        with state_lock:
            agent_state["score"] = score
            agent_state["status"] = status
            agent_state["loop_count"] += 1

        # FPS 계산
        frame_count += 1
        elapsed = time.time() - fps_start
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            frame_count = 0
            fps_start = time.time()
            with state_lock:
                agent_state["fps"] = round(fps, 1)

        # 오버레이 그리기
        h, w = frame.shape[:2]

        # 상단 바
        bar_color = (0, 120, 0)
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 70), bar_color, -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        label = "NORMAL"
        cv2.putText(frame, label, (15, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(frame, f"Score: {score:.2f} | Thr: {THRESHOLD:.1f}",
                    (15, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (200, 200, 200), 1)
        cv2.putText(frame, f"FPS: {fps:.1f}", (w - 110, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" +
               buf.tobytes() + b"\r\n")

    cap.release()


# ──────────────────────────────────────────────
# API 라우트
# ──────────────────────────────────────────────
@app.get("/api/mcp/servers")
async def list_mcp_servers():
    """연결된 MCP 서버와 도구 목록 반환."""
    if not mcp_client:
        return {"servers": [], "status": "stopped"}

    servers = []
    try:
        for name, server in mcp_client.servers.items():
            is_process_alive = server.process is not None and server.process.poll() is None
            try:
                tools = server.list_tools()
            except Exception:
                tools = []
            
            is_enabled = is_process_alive and len(tools) >= 1
            
            servers.append({
                "name": name,
                "status": "connected" if is_enabled else "disconnected",
                "enabled": is_enabled,
                "tool_count": len(tools),
                "tools": [
                    {"name": t.get("name") if isinstance(t, dict) else getattr(t, 'name', str(t)),
                     "description": t.get("description", "") if isinstance(t, dict) else getattr(t, 'description', "")}
                    for t in tools
                ]
            })
    except Exception as e:
        print(f"[API] list_mcp_servers 에러: {e}")
        
    return {"servers": servers, "status": mcp_status}


@app.post("/api/mcp/call")
async def call_mcp_tool(req: MCPCallRequest):
    """
    대시보드 버튼에서 MCP 도구 직접 호출.
    예: 뉴스 버튼 → web_search 도구 → 결과 반환
    """
    if not mcp_client:
        return {"status": "error", "error": "MCP not running"}

    try:
        result = mcp_client.call_tool(req.tool_name, req.params)
        return {
            "status": "success",
            "tool": req.tool_name,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/quick/{action}")
async def quick_action(action: str):
    """
    원클릭 빠른 액션.
    뉴스/논문/모델 검색을 버튼 하나로.
    """
    if not mcp_client:
        return {"status": "error", "error": "MCP not running"}

    actions = {
        "news": lambda: mcp_client.call_tool(
            "search_web",
            {"query": "anomaly detection AI 최신 뉴스"}),
        "papers": lambda: mcp_client.call_tool(
            "search_arxiv",
            {"query": "industrial anomaly detection 2026"}),
        "models": lambda: mcp_client.call_tool(
            "search_models",
            {"query": "defect detection"}),
        "gpu": lambda: get_gpu_status_string(),
    }
    if action not in actions:
        return {"error": f"unknown action: {action}"}

    try:
        result = actions[action]()
        return {"action": action, "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_gpu_status_string():
    import subprocess
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.free",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            return res.stdout.strip()
        return "N/A (nvidia-smi return error)"
    except Exception:
        return "N/A (No GPU Available)"


@app.get("/api/system/status")
async def system_status():
    """GPU, 메모리, 모델, MCP 상태."""
    import subprocess

    gpu = "N/A (No GPU Available)"
    try:
        gpu_res = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if gpu_res.returncode == 0:
            gpu = gpu_res.stdout.strip()
    except Exception:
        pass

    # Ollama 모델 수
    models_count = 0
    try:
        models_res = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=5
        )
        if models_res.returncode == 0:
            models_count = max(0, models_res.stdout.count("\n") - 1)
    except Exception:
        pass

    return {
        "gpu": gpu,
        "models_loaded": models_count,
        "mcp_servers": len(mcp_client.servers) if mcp_client else 0,
        "mcp_status": mcp_status,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/agents/status")
async def get_agents_status():
    """서브 에이전트들의 실시간 상태 스냅샷 반환 ({state, detail} 포맷으로 정규화)."""
    # cache 값이 이미 {state, detail} 포맷이고, 일부 이전 복잡 포맷도 있으므로 정제
    normalized = {}
    for agent_name, val in agent_status_cache.items():
        if isinstance(val, dict):
            normalized[agent_name] = {
                "state":  val.get("state",  "idle"),
                "detail": val.get("detail", val.get("message", ""))
            }
        else:
            normalized[agent_name] = {"state": "idle", "detail": ""}
    return normalized


@app.get("/api/autonomous/log")
async def get_autonomous_log():
    """DB에서 최근 20개의 자율 에이전트 활동 로그(role이 agent, tool인 로그)를 가져옴."""
    db = SessionLocal()
    try:
        logs = db.query(AgentMemory).filter(
            AgentMemory.role.in_(["agent", "tool"])
        ).order_by(AgentMemory.timestamp.desc()).limit(20).all()
        
        result = []
        for l in logs:
            result.append({
                "timestamp": l.timestamp.strftime("%H:%M:%S"),
                "role": l.role,
                "content": l.content
            })
        return {"logs": result}
    except Exception as e:
        return {"logs": [], "error": str(e)}
    finally:
        db.close()


@app.get("/")
async def root_spa():
    """React SPA root."""
    return FileResponse("frontend/dist/index.html")


@app.get("/video_feed")
async def video_feed():
    """MJPEG 비디오 스트리밍 엔드포인트."""
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/state", response_model=StateResponse)
async def get_state():
    """에이전트 상태 + DB 기반 Session/Memory 반환."""
    with state_lock:
        state_copy = dict(agent_state)

    session_text = get_session_db_text()
    memory_text = get_memory_db_text()

    # MCP 서버 상태 조회
    servers_list = []
    if mcp_client:
        for name, server in mcp_client.servers.items():
            is_process_alive = server.process is not None and server.process.poll() is None
            try:
                tools = server.list_tools()
            except Exception:
                tools = []
            
            is_enabled = is_process_alive and len(tools) >= 1
            
            servers_list.append({
                "name": name,
                "enabled": is_enabled,
                "tools": [
                    {"name": t.get("name") if isinstance(t, dict) else getattr(t, "name", str(t)),
                     "description": t.get("description", "") if isinstance(t, dict) else getattr(t, "description", "")}
                    for t in tools
                ]
            })

    return StateResponse(
        agent=AgentStateModel(**state_copy),
        session=session_text,
        memory=memory_text,
        timestamp=datetime.now().isoformat(),
        mcp_servers=servers_list
    )



@app.get("/api/stats")
async def get_stats():
    """최신 통계 지표 및 PCA 2D 좌표 리턴."""
    return JSONResponse(latest_stats)


@app.post("/api/action")
async def post_action(request: Request):
    """프론트엔드 제어 신호 수신."""
    body = await request.json()
    action = body.get("action", "unknown")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with state_lock:
        agent_state["last_action"] = action
        agent_state["last_action_time"] = now

    if action == "emergency_stop":
        with state_lock:
            agent_state["is_running"] = False
            agent_state["status"] = "stopped"
        append_memory_event("action", f"관리자 긴급 정지 명령 실행 ({now})")
        return JSONResponse({"result": "emergency_stop_executed", "time": now})

    elif action == "approve":
        append_memory_event("action", f"관리자 행동 승인 ({now})")
        return JSONResponse({"result": "approved", "time": now})

    elif action == "resume":
        with state_lock:
            agent_state["is_running"] = True
            agent_state["status"] = "idle"
        append_memory_event("action", f"관리자 시스템 재개 명령 ({now})")
        return JSONResponse({"result": "resumed", "time": now})

    return JSONResponse({"result": "unknown_action", "action": action})


# ──────────────────────────────────────────────
# 샌드박스: 이미지 업로드 → 추론 (자율 에이전트 라우팅)
# ──────────────────────────────────────────────
@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_image(file: UploadFile = File(...), auto: bool = False):
    """
    브라우저에서 이미지를 업로드하면 자율 에이전트(Orchestrator → VisionAgent)를 통해 추론 실행.
    """
    global latest_stats
    try:
        # 1. 파일 저장
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = Path(file.filename).suffix or ".jpg"
        save_path = UPLOAD_DIR / f"upload_{ts}{ext}"
        contents = await file.read()
        with open(save_path, "wb") as f:
            f.write(contents)


        # 2. 이미지 로드 검증
        frame_bgr = cv2.imread(str(save_path))
        if frame_bgr is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="이미지를 읽을 수 없습니다.")

        # 결과 이미지 경로 미리 정의
        heatmap_path = OUTPUT_DIR / f"heatmap_{ts}.jpg"

        # 실제 추론 시간 측정을 위해 타이머 시작
        start_time = time.time()

        # 3. 에이전트 오케스트레이터를 통한 이미지 분석 라우팅
        from aria.orchestration.agent_orchestrator import AgentOrchestrator
        orchestrator = AgentOrchestrator(mcp_hub=mcp_client)

        print("  [app.py API] AgentOrchestrator 라우팅 호출 시작...")
        loop = asyncio.get_running_loop()
        
        def analyze_callback(msg):
            if msg.get("type") == "agent_status":
                agent_name = msg.get("agent")
                if agent_name:
                    # [LED] {state, detail} 포맷으로 정규화하여 저장 (프론트엔드와 포맷 일치)
                    agent_status_cache[agent_name] = {
                        "state":  msg.get("state",  "idle"),
                        "detail": msg.get("detail", msg.get("message", ""))
                    }
                # WebSocket으로 broadcast할 때는 원본 msg 전체 전송 (type 필드 포함)
                msg["source"] = "analysis"
                asyncio.run_coroutine_threadsafe(manager.broadcast(msg), loop)

        route_res = await loop.run_in_executor(
            None,
            lambda: orchestrator.route(
                user_input="이 이미지에서 이상/결함 또는 객체를 감지하라",
                image_path=str(save_path),
                callback=analyze_callback
            )
        )
        
        # vision 에이전트 결과 획득
        vision_data = {}
        if "results" in route_res and "vision" in route_res["results"]:
            vision_data = route_res["results"]["vision"]
        else:
            vision_data = route_res

        # [§1 분기 키] domain: "general_object" | "industrial_anomaly" | "counting" | "label_inspect" | "dimension"
        image_domain = vision_data.get("domain", "general_object")
        # 이상탐지 수치(score/threshold)를 표시할 산업 도메인 집합
        INDUSTRIAL_DOMAINS = {"industrial_anomaly", "counting", "label_inspect", "dimension", "segmentation"}
        is_industrial = image_domain in INDUSTRIAL_DOMAINS

        score = vision_data.get("anomaly_score") or vision_data.get("score") or 0.0
        status_str = vision_data.get("status", "normal")
        model_name = vision_data.get("model_used") or "VisionAgent (Hybrid)"
        model_type = "yolo" if "yolo" in model_name.lower() else "custom"
        vlm_scene = vision_data.get("vlm_scene") or ""
        model_discussion = vision_data.get("model_discussion") or ""
        defect_location_description = vision_data.get("defect_location_description") or ""

        # [§1] 일반/문서 이미지는 status를 "content"로 덮어써 프론트엔드가 이상탐지 패널 숨김
        # 카운팅/라벨/치수 도메인은 산업 검사로 처리 (수치 패널 표시)
        if not is_industrial:
            status_str = "content"
            print(f"  [app.py §1] domain='{image_domain}' → 이상탐지 관련 수치 비활성화 (status='content')")
        else:
            print(f"  [app.py §1] domain='{image_domain}' → 산업 검사 도메인 확인 (탐지기 결과 표시)")

        # 결과 이미지 복사
        disc_img = vision_data.get("result_image_path")
        if disc_img and os.path.exists(disc_img):
            import shutil
            shutil.copy(disc_img, heatmap_path)
            print(f"  [app.py API] 결과 이미지를 대시보드 오버레이 경로로 복사 완료: {heatmap_path}")
        else:
            import shutil
            shutil.copy(str(save_path), heatmap_path)
            print(f"  [app.py API] 결과 이미지가 없어 원본 복사: {heatmap_path}")

        # 실제 추론 지연시간 계산
        inference_time_ms = int((time.time() - start_time) * 1000)

        # [§1] 산업 이미지일 때만 결함 확률 계산
        if is_industrial:
            is_anom = status_str in ("anomaly", "detected") or score > THRESHOLD
            if is_anom:
                defect_probability_percent = int(min(85 + (score / THRESHOLD) * 5, 99))
            else:
                defect_probability_percent = int(max(min((score / THRESHOLD) * 15, 15), 1))
        else:
            # 일반/문서 이미지 → 결함확률 N/A
            is_anom = False
            defect_probability_percent = None

        # 통계 지표 업데이트 (산업 도메인일 때만 의미 있음)
        latest_stats = {
            "stats": {
                "score": round(float(score), 3) if is_industrial else None,
                "mean": round(float(score) * 0.8, 3) if is_industrial else None,
                "variance": 1.2 if is_industrial else None,
                "ci_lower": 0.0 if is_industrial else None,
                "ci_upper": THRESHOLD if is_industrial else None,
            },
            "pca_data": {
                "normal": [[0.5, 0.5]],
                "query": [[0.6, 0.6]]
            }
        }

        # scout 로그 구성
        scout_log = [
            "🚀 AgentOrchestrator 단일 진입점 호출 성공",
            f"📦 VisionAgent VLM 분석 결과: {vlm_scene}",
            f"⚡ 모델 추론: {model_name} (소요시간: {inference_time_ms}ms)"
        ]

        result_data = {
            "type": "diagnostic_result",
            "source": "analysis",
            "image_domain": image_domain,   # [§1] "general_object" | "industrial_anomaly" — 프론트 분기용
            # [§1] 일반 이미지는 score/threshold/defect_prob를 null로 표시
            "score": round(float(score), 3) if is_industrial else None,
            "anomaly_score": round(float(score), 3) if is_industrial else None,
            "threshold": THRESHOLD if is_industrial else None,
            "defect_probability_percent": defect_probability_percent,
            "status": status_str,
            "filename": file.filename,
            "model_used": model_name,
            "model_type": model_type,
            "render_type": vision_data.get("render_type", "bounding_box"),
            "heatmap_url": f"/api/result/{heatmap_path.name}",
            "auto_mode": auto,
            "vlm_scene": vlm_scene,
            "model_discussion": model_discussion,
            "defect_location_description": defect_location_description,
            "scout_log": scout_log,
            "scout_meta": vision_data.get("data", {}),
            "stats": latest_stats.get("stats", {}),
            "pca_data": latest_stats.get("pca_data", {}),
            "inference_time_ms": inference_time_ms,
            "device": vision_data.get("device", "cpu"),
            "device_reason": vision_data.get("device_reason", "VLM 또는 기본 디바이스"),
            # [§3 LED] 분석 완료 시점의 에이전트 상태 스냅샷 — 프론트엔드가 WS 없이도 LED 업데이트 가능
            "agents_status": dict(agent_status_cache),
        }
        await manager.broadcast(result_data)

        # ── DB에 시편 검사 이력 저장 ──
        db = SessionLocal()
        try:
            history = AnalysisHistory(
                image_path=str(save_path),
                domain_type=status_str,
                score=float(score),
                defect_probability=float(defect_probability_percent) if defect_probability_percent is not None else 0.0,
                heatmap_url=f"/api/result/{heatmap_path.name}"
            )
            db.add(history)
            db.commit()
            print(f"[DB] AnalysisHistory 저장 완료: ID={history.id}")
        except Exception as db_err:
            db.rollback()
            print(f"[DB] AnalysisHistory 저장 중 에러 발생: {db_err}")
        finally:
            db.close()

        # 백그라운드로 LLM 정밀 관측 소견 생성 및 WebSocket Chat 패널 자동 송신
        loop = asyncio.get_running_loop()
        # VisionAgent가 실제로 사용한 모델명 파악
        _vlm_model = vision_data.get("vlm_model") or vision_data.get("model_name") or model_name or "qwen2.5vl:7b"
        _ccifps_score = vision_data.get("ccifps_score") or vision_data.get("anomaly_score") or score
        _render_type = vision_data.get("render_type", "heatmap")

        def generate_llm_observation():
            try:
                from aria.orchestration.agent_orchestrator import _call_ollama
                import re

                if is_industrial:
                    # ── 산업 제품 이미지 → [판정][소견][조치] 진단 리포트 ────────────────
                    print(f"  [§1] 산업 도메인 → 진단 리포트 생성")
                    prompt = (
                        f"너는 산업용 비전 검사 시스템의 진단 엔진이다.\n"
                        f"아래 데이터를 기반으로 3줄 진단 리포트를 작성하라.\n"
                        f"출력 규칙:\n"
                        f"- 마크다운 기호(*,**,#,~) 절대 사용 금지\n"
                        f"- 인사말, 서론, AI 어투('~하겠습니다', '도와드리겠습니다') 금지\n"
                        f"- 숫자와 단위를 정확히 기입하라\n"
                        f"- 각 줄은 [판정], [소견], [조치] 접두어로 시작하라\n\n"
                        f"[입력 데이터]\n"
                        f"추론 모델: {_vlm_model}\n"
                        f"이상 스코어 (CCIFPS): {_ccifps_score:.3f}  /  임계치: {THRESHOLD}\n"
                        f"판정: {'ANOMALY' if is_anom else 'NORMAL'}\n"
                        f"결함 확률: {defect_probability_percent}%\n"
                        f"추론 시간: {inference_time_ms} ms\n"
                        f"렌더링 타입: {_render_type}\n"
                        f"VLM 장면 설명: {vlm_scene[:200] if vlm_scene else '없음'}\n"
                        f"결함 위치: {defect_location_description[:200] if defect_location_description else '없음'}\n\n"
                        f"[출력 형식 — 정확히 3줄, 각 줄은 아래 형식 준수]\n"
                        f"[판정] ...\n"
                        f"[소견] ...\n"
                        f"[조치] ..."
                    )
                else:
                    # ── 일반/문서/표 이미지 → 이상탐지 금지, VLM 내용 설명만 ──────────────
                    print(f"  [§1] 일반 도메인('{image_domain}') → VLM 내용 설명 모드 (판정/소견/조치 금지)")
                    if vlm_scene:
                        # VisionAgent가 이미 장면을 설명했으면 그대로 사용
                        obs = vlm_scene
                        msg = {"type": "response", "content": obs, "source": "analysis"}
                        asyncio.run_coroutine_threadsafe(manager.broadcast(msg), loop)
                        db_mem = SessionLocal()
                        try:
                            db_mem.add(AgentMemory(
                                session_id="default",
                                role="agent",
                                content=f"[이미지 내용 설명 | 모델:{_vlm_model}] {obs}"
                            ))
                            db_mem.commit()
                            print(f"[DB] 이미지 내용 설명 저장 완료")
                        except Exception as mem_err:
                            db_mem.rollback()
                        finally:
                            db_mem.close()
                        return
                    # vlm_scene이 비어 있으면 LLM에 내용 설명 요청
                    prompt = (
                        f"이미지를 분석한 결과 도메인은 '{image_domain}'이다.\n"
                        f"VLM 장면 설명: {vlm_scene[:300] if vlm_scene else '(미분석)'}\n\n"
                        f"이 이미지의 내용을 한국어로 명확하게 설명하라.\n"
                        f"출력 규칙:\n"
                        f"- 마크다운 기호 절대 사용 금지\n"
                        f"- 이상탐지/결함/판정 관련 언급 금지\n"
                        f"- 이미지가 표/그래프라면 핵심 수치를 요약하라\n"
                        f"- 이미지가 문서라면 주요 내용을 요약하라\n"
                        f"- 2~3문장 이내로 간결하게"
                    )

                obs = _call_ollama("qwen2.5:14b", prompt)
                obs = obs.strip()
                if "</think>" in obs:
                    obs = obs.split("</think>")[-1].strip()
                obs = re.sub(r'\*+', '', obs)
                obs = re.sub(r'#+\s*', '', obs)

                msg = {"type": "response", "content": obs, "source": "analysis"}
                asyncio.run_coroutine_threadsafe(manager.broadcast(msg), loop)

                # DB에 소견 저장
                db_mem = SessionLocal()
                try:
                    label = "진단 소견" if is_industrial else "이미지 내용 설명"
                    db_mem.add(AgentMemory(
                        session_id="default",
                        role="agent",
                        content=f"[{label} | 모델:{_vlm_model}] {obs}"
                    ))
                    db_mem.commit()
                    print(f"[DB] {label} 저장 완료 (모델: {_vlm_model})")
                except Exception as mem_err:
                    db_mem.rollback()
                    print(f"[DB] 소견 저장 에러: {mem_err}")
                finally:
                    db_mem.close()

            except Exception as e:
                print(f"[Observation Generator] Error: {e}")

        threading.Thread(target=generate_llm_observation, daemon=True).start()


        # JSON 응답에는 type을 제거하여 호환성 유지
        response_data = dict(result_data)
        response_data.pop("type", None)
        return response_data
    except Exception as e:
        import traceback
        print(f"[api_analyze] 에러 발생: {e}\n{traceback.format_exc()}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/train/upload")
async def train_upload(file: UploadFile = File(...)):
    import time
    from aria.learning.training.ingest import ingest_zip
    from aria.learning.training.dummy_trainer import run_dummy_training
    from aria.orchestration.event_bus import event_bus
    from aria.learning.training.events import TRAINING_TOPIC

    run_id = f"run_{int(time.time())}"
    # 파일 확장자 그대로 보존해서 임시 저장 (.tar.gz, .tgz, .zip 등 처리)
    orig_ext = ".zip"
    if file.filename:
        if file.filename.endswith(".tar.gz"):
            orig_ext = ".tar.gz"
        elif file.filename.endswith(".tgz"):
            orig_ext = ".tgz"
        else:
            orig_ext = Path(file.filename).suffix
            
    archive_path = UPLOAD_DIR / f"{run_id}{orig_ext}"
    archive_path.write_bytes(await file.read())

    work_dir = UPLOAD_DIR / run_id
    manifest = ingest_zip(str(archive_path), str(work_dir))

    loop = asyncio.get_running_loop()
    def _publish(ev):
        asyncio.run_coroutine_threadsafe(event_bus.publish(TRAINING_TOPIC, ev), loop)

    threading.Thread(
        target=run_dummy_training, args=(run_id, manifest, _publish),
        daemon=True).start()

    return {"run_id": run_id, "n_images": manifest["n_images"],
            "classes": manifest["classes"], "status": "training_started"}


from fastapi import Body
@app.post("/api/sim/train")
async def sim_train(payload: dict = Body(...)):
    import json, asyncio, threading
    import numpy as np
    from pathlib import Path
    from aria.perception.scorer.feature_bank import build_bank
    from aria.learning.training.events import TRAINING_TOPIC, make_training_event
    from aria.orchestration.event_bus import event_bus
    run_id = payload.get("run_id")
    work = UPLOAD_DIR / str(run_id)
    mpath = work / "manifest.json"
    if not run_id or not mpath.exists():
        return {"ok": False, "error": "manifest 없음 — 먼저 인테이크/생성 필요"}
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    imgs = manifest.get("images", [])
    good = [p for p in imgs if Path(p).parent.name.lower() in ("good", "normal", "ok")] or imgs
    loop = asyncio.get_running_loop()
    def publish(ev):
        asyncio.run_coroutine_threadsafe(event_bus.publish(TRAINING_TOPIC, ev), loop)
    def emit_agent(agent, state, detail):
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "agent_status", "agent": agent, "state": state, "detail": detail}), loop)
    def worker():
        try:
            emit_agent("TRAINER", "running", "메모리뱅크 구축")
            publish(make_training_event(run_id, 0, len(good), "running", loss=0.0))  # 조기 하트비트(모델 로딩)
            bank = build_bank(good, run_id, publish)              # 진짜 FM 특징 추출
            np.save(str(work / "bank.npy"), bank)                  # 모델 저장
            publish(make_training_event(run_id, len(good), len(good), "done", loss=0.0))
            emit_agent("TRAINER", "done", f"{len(good)} 이미지 · {bank.shape[0]} 패치")
        except Exception as e:
            print(f"[sim_train] bank build 실패: {e}")
            publish(make_training_event(run_id, 0, 0, "error", loss=0.0))  # 루프 가드가 정지
            emit_agent("TRAINER", "idle", f"실패: {e}")
    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "run_id": run_id}


@app.post("/api/sim/validate")
async def sim_validate(payload: dict = Body(...)):
    import json
    from aria.simulation.validation.validate import run_validation
    run_id = payload.get("run_id")
    mpath = UPLOAD_DIR / str(run_id) / "manifest.json"
    if not run_id or not mpath.exists():
        return {"ok": False, "error": "manifest 없음 — 먼저 인테이크 필요"}
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    await manager.broadcast({"type": "agent_status", "agent": "VERIFIER",
                             "state": "running", "detail": "NG 검증"})
    criteria = payload.get("criteria")
    result = run_validation(manifest, criteria=criteria)
    er = result.get("escape_rate")
    detail = f"escape {er:.0%}" if er is not None else (result.get("error") or "검증")
    await manager.broadcast({"type": "agent_status", "agent": "VERIFIER",
                             "state": "done", "detail": detail})

    v = result.get("fat_verdict", "N/A")
    state = "done" if v == "PASS" else ("idle" if v == "FAIL" else "running")
    await manager.broadcast({"type": "agent_status", "agent": "FAT",
                             "state": state, "detail": f"{v} · escape {er:.0%}" if er is not None else f"{v}"})
    return result


BANKS_DIR = BASE_DIR / "banks"
BANKS_DIR.mkdir(exist_ok=True)
IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp")

@app.get("/api/mvtec/scan")
async def mvtec_scan(root: str):
    from pathlib import Path
    base = Path(root)
    if not base.is_dir():
        return {"ok": False, "error": f"디렉토리 없음: {root}"}
    classes = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "train" / "good").is_dir() and (d / "test").is_dir():
            classes.append(d.name)
    return {"ok": True, "root": str(base), "classes": classes}

@app.get("/api/class/samples")
async def class_samples(classId: str, mvtec_path: str, n: int = 9):
    from pathlib import Path; import urllib.parse
    test = Path(mvtec_path) / "test"
    if not test.is_dir(): return {"ok": False, "error": f"test 없음: {test}"}
    def url(p): return "/api/image?path=" + urllib.parse.quote(str(p))
    items = []
    
    # good 9//3 = 3개 수집
    good_dir = test / "good"
    if good_dir.is_dir():
        for p in sorted(good_dir.glob("*"))[:max(1, n // 3)]:
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp"):
                items.append({"url": url(p), "label": "OK"})
                
    # defect 수집
    for d in sorted(test.iterdir()):
        if d.is_dir() and d.name != "good":
            for p in sorted(d.glob("*"))[:2]:
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp"):
                    items.append({"url": url(p), "label": "NG", "defect": d.name})
                if len(items) >= n: break
        if len(items) >= n: break
    return {"ok": True, "classId": classId, "items": items[:n]}

@app.get("/api/image")
async def serve_image(path: str):
    from pathlib import Path
    p = Path(path).resolve()
    # 안전: 데이터/업로드 루트 하위만 허용 (경로 탈출 방지)
    allowed = [BASE_DIR.resolve(), (BASE_DIR / "data").resolve(), UPLOAD_DIR.resolve()]
    if not any(str(p).startswith(str(a)) for a in allowed) or not p.is_file():
        return JSONResponse({"error": "허용되지 않은 경로"}, status_code=403)
    return FileResponse(str(p))

@app.post("/api/class/train")
async def class_train(payload: dict = Body(...)):
    import numpy as np
    import threading
    import asyncio
    from pathlib import Path
    from aria.perception.scorer.feature_bank import build_bank
    
    cid = payload.get("classId")
    root = Path(payload.get("mvtec_path", ""))
    good_dir = root / "train" / "good"
    if not good_dir.exists():
        return {"ok": False, "error": f"good 디렉토리 없음: {good_dir}"}
    goods = sorted(str(p) for p in good_dir.glob("*") if p.suffix.lower() in IMG_EXT)
    if not cid or not goods:
        return {"ok": False, "error": f"good 이미지 없음: {good_dir}"}
    
    loop = asyncio.get_running_loop()
    def emit(state, detail):
        asyncio.run_coroutine_threadsafe(manager.broadcast(
            {"type": "agent_status", "agent": cid.upper(), "state": state, "detail": detail}), loop)
            
    def worker():
        try:
            emit("running", f"{len(goods)} good 학습")
            bank = build_bank(goods, run_id=cid)
            np.save(str(BANKS_DIR / f"{cid}.npy"), bank)
            emit("done", f"bank {bank.shape[0]} 패치")
        except Exception as e:
            emit("idle", f"실패: {e}")
            
    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "classId": cid, "n_good": len(goods)}

@app.post("/api/class/validate")
async def class_validate(payload: dict = Body(...)):
    import numpy as np
    from pathlib import Path
    from aria.perception.scorer.feature_bank import cosine_score
    from aria.simulation.validation.validate import run_validation
    
    cid = payload.get("classId")
    root = Path(payload.get("mvtec_path", ""))
    bank_path = BANKS_DIR / f"{cid}.npy"
    if not bank_path.exists():
        return {"ok": False, "error": f"bank 없음 — 먼저 학습: {cid}"}
    test_imgs = [str(p) for p in (root / "test").rglob("*") if p.suffix.lower() in IMG_EXT]
    if not test_imgs:
        return {"ok": False, "error": f"test 이미지 없음: {root/'test'}"}
    
    bank = np.load(bank_path)
    manifest = {"images": test_imgs, "work_dir": str(BANKS_DIR)}
    result = run_validation(manifest, score_fn=lambda p: cosine_score(p, bank),
                            criteria=payload.get("criteria"))
    result["classId"] = cid
    await manager.broadcast({"type": "class_result", "classId": cid,
        "escape_rate": result.get("escape_rate"), "fp_rate": result.get("fp_rate"),
        "fat_verdict": result.get("fat_verdict"), "threshold": result.get("threshold")})
    return result


@app.post("/api/dataset/intake")
async def dataset_intake(file: UploadFile = File(...)):
    import time
    from pathlib import Path
    from aria.perception.intake.scan_agent import scan_dataset
    from aria.perception.intake.domain_agent import classify_domain
    from fastapi import HTTPException

    run_id = f"ds_{int(time.time())}"
    orig_ext = ".zip"
    if file.filename:
        if file.filename.endswith(".tar.gz"):
            orig_ext = ".tar.gz"
        elif file.filename.endswith(".tgz"):
            orig_ext = ".tgz"
        else:
            orig_ext = Path(file.filename).suffix or ".zip"

    arc = UPLOAD_DIR / f"{run_id}{orig_ext}"
    contents = await file.read()
    arc.write_bytes(contents)
    work = UPLOAD_DIR / run_id

    async def emit_async(agent, state, detail=""):
        await manager.broadcast({
            "type": "agent_status",
            "agent": agent,
            "state": state,
            "detail": detail
        })

    try:
        await emit_async("SCAN", "running", "압축 해제·구조 분석")
        rep = await asyncio.to_thread(scan_dataset, str(arc), str(work))
        (work / "manifest.json").write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
        await emit_async("SCAN", "done", f"{rep['n_images']}장 · 클래스 {len(rep['classes'])}")
        
        await emit_async("DOMAIN", "running", "VLM 도메인 판단")
        dom = await asyncio.to_thread(classify_domain, rep)
        await emit_async("DOMAIN", "done", dom["domain"])
        
        return {
            "run_id": run_id,
            "n_images": rep["n_images"],
            "classes": rep["classes"],
            "resolution": rep["resolution"],
            "formats": rep["formats"],
            "domain": dom
        }
    except Exception as e:
        await emit_async("SCAN", "idle", f"실패: {e}")
        await emit_async("DOMAIN", "idle", "중단됨")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sim/dataset")
async def sim_dataset(payload: dict = None):
    # payload가 None이거나 dict가 아닐 경우 Body에서 dict로 받기 위해 FastAPI가 자동 디시리얼라이즈함
    if payload is None:
        payload = {}
    import time
    from aria.simulation.dataset import save_sim_dataset
    run_id = f"sim_{int(time.time())}"
    work = UPLOAD_DIR / run_id
    m = save_sim_dataset(
        payload.get("images", []),
        str(work),
        defect_ratio=float(payload.get("defect_ratio", 0.3)),
        defect_type=payload.get("defect_type", "scratch")
    )
    return {"run_id": run_id, "n_images": m["n_images"], "classes": m["classes"], "work_dir": m["work_dir"]}


@app.get("/api/result/{filename}")
async def serve_result(filename: str):
    """전체 결과 이미지 제공 (heatmap 등)."""
    path = OUTPUT_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "파일 없음"}, status_code=404)
    return FileResponse(str(path), media_type="image/jpeg")


@app.get("/api/hardware")
async def hardware_telemetry():
    """하드웨어 텔레메트리 스냅샷 반환."""
    from hardware.monitor import get_snapshot
    return get_snapshot()


@app.get("/api/history")
async def get_analysis_history(limit: int = 10):
    """최근 N건의 분석 이력 반환 (§4 Quick Actions - 검사 이력 조회)."""
    db = SessionLocal()
    try:
        histories = db.query(AnalysisHistory).order_by(
            AnalysisHistory.timestamp.desc()
        ).limit(limit).all()
        return {
            "history": [
                {
                    "id": h.id,
                    "image_path": h.image_path,
                    "domain_type": h.domain_type,
                    "score": round(h.score, 4) if h.score is not None else None,
                    "defect_probability": round(h.defect_probability, 2) if h.defect_probability is not None else None,
                    "heatmap_url": h.heatmap_url,
                    "timestamp": str(h.timestamp) if hasattr(h, 'timestamp') else None,
                }
                for h in histories
            ]
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()


def execute_mcp_verification(user_message: str) -> str:
    """LLM을 거치지 않고, 파이썬 MCPClient.call_tool() 메서드를 다이렉트로 호출하여 검증 리포트를 생성하는 헬퍼 함수"""
    parts = user_message.strip().split()
    server_name = parts[1] if len(parts) > 1 else None
    
    global mcp_client
    if not mcp_client:
        return "❌ MCP 클라이언트가 활성화되어 있지 않습니다."
        
    config_servers = mcp_client._config.get("mcpServers", {}) if hasattr(mcp_client, "_config") else {}
    
    targets = []
    if server_name:
        if server_name not in config_servers:
            return f"❌ `{server_name}` 서버는 `mcp_config.json`에 정의되지 않은 서버입니다."
        targets.append(server_name)
    else:
        targets = list(config_servers.keys())

    if not targets:
        return "⚠️ 검증할 MCP 서버가 설정에 존재하지 않습니다."

    results = []
    
    test_calls = {
        "shell_exec": {
            "tool": "run_command",
            "args": {"command": "echo 'ARGUS_MCP_ACTIVE'"},
            "validator": lambda res: "ARGUS_MCP_ACTIVE" in str(res)
        },
        "filesystem": {
            "tool": "list_directory",
            "args": {"path": "."},
            "validator": lambda res: isinstance(res, dict) and res.get("success", False) is True
        },
        "computer_use": {
            "tool": "get_screen_size",
            "args": {},
            "validator": lambda res: isinstance(res, dict) and "width" in res
        },
        "google-workspace": {
            "tool": "gmail.search",
            "args": {"query": "is:unread", "limit": 1},
            "validator": lambda res: isinstance(res, dict) and "error" not in res
        },
        "youtube": {
            "tool": "search_youtube",
            "args": {"query": "test"},
            "validator": lambda res: isinstance(res, dict) and "error" not in res
        },
        "web_search": {
            "tool": "check_endpoint",
            "args": {"url": "https://lite.duckduckgo.com/lite/"},
            "validator": lambda res: isinstance(res, dict) and res.get("success", False) is True
        },
        "arxiv": {
            "tool": "search_arxiv",
            "args": {"query": "machine learning", "max_results": 1},
            "validator": lambda res: isinstance(res, dict) and "error" not in res
        },
        "kaggle": {
            "tool": "search_datasets",
            "args": {"query": "test"},
            "validator": lambda res: isinstance(res, dict) and "error" not in res
        },
        "huggingface": {
            "tool": "search_models",
            "args": {"query": "test", "max_results": 1},
            "validator": lambda res: isinstance(res, dict) and "error" not in res
        }
    }

    for name in targets:
        server_proc = mcp_client.servers.get(name)
        if not server_proc or not server_proc.process or server_proc.process.poll() is not None:
            server_config = config_servers.get(name, {})
            missing_envs = []
            import os
            for env_key, env_val in server_config.get("env", {}).items():
                if isinstance(env_val, str) and env_val.startswith("${") and env_val.endswith("}"):
                    var_name = env_val[2:-1]
                    real_val = os.environ.get(var_name, "").strip()
                    if not real_val or "여기에_" in real_val or "ENTER_" in real_val.upper() or "INSERT_" in real_val.upper():
                        missing_envs.append(var_name)
            
            reason = "서버 프로세스가 기동되지 않았거나 중지되었습니다."
            if missing_envs:
                reason = f"필수 환경 변수({', '.join(missing_envs)})가 설정되지 않았습니다."
            
            results.append({
                "server": name,
                "status": "offline",
                "error": reason,
                "troubleshoot": f"서버 구동 상태와 환경 변수 설정을 확인하십시오. (필요 변수: {', '.join(missing_envs) if missing_envs else '없음'})"
            })
            continue

        test_info = test_calls.get(name)
        if not test_info:
            try:
                t_start = time.time()
                tools = server_proc.list_tools()
                elapsed = round((time.time() - t_start) * 1000, 2)
                results.append({
                    "server": name,
                    "status": "success",
                    "elapsed": elapsed,
                    "data_summary": f"도구 목록 조회 성공 (총 {len(tools)}개 제공)",
                    "detail": f"동적 핸드셰이크 완료"
                })
            except Exception as e:
                results.append({
                    "server": name,
                    "status": "error",
                    "error": str(e),
                    "troubleshoot": f"서버 '{name}' 실행 중 예기치 못한 에러: {e}"
                })
            continue

        tool_name = test_info["tool"]
        args = test_info["args"]
        validator = test_info["validator"]

        try:
            t_start = time.time()
            res = mcp_client.call_tool(tool_name, args, server_name=name)
            elapsed = round((time.time() - t_start) * 1000, 2)

            if isinstance(res, dict) and "error" in res:
                err_msg = res["error"]
                results.append({
                    "server": name,
                    "status": "error",
                    "error": err_msg,
                    "troubleshoot": f"서버 '{name}'가 도구 실행에 실패했습니다. 설정을 확인해 주세요."
                })
            elif validator(res):
                data_summary = "도구 실행 결과 정상 확인"
                if name == "computer_use":
                    data_summary = f"현재 해상도는 {res.get('width')}x{res.get('height')}로 확인되었습니다"
                elif name == "shell_exec":
                    data_summary = "터미널 제어 권한이 증명되었습니다"
                elif name == "filesystem":
                    data_summary = "프로젝트 폴더 조회 완료"
                elif name == "google-workspace":
                    data_summary = "이메일 긁어오기 정상 동작이 확인되었습니다"
                elif name == "youtube":
                    data_summary = "유튜브 동영상 검색 배열 수신 확인"
                
                results.append({
                    "server": name,
                    "status": "success",
                    "elapsed": elapsed,
                    "data_summary": data_summary,
                    "detail": f"E2E 실행 성공 ({elapsed} ms)"
                })
            else:
                results.append({
                    "server": name,
                    "status": "error",
                    "error": f"데이터 포맷 유효성 검증 실패: {res}",
                    "troubleshoot": "도구 호출은 성공하였으나 반환 데이터 검증 기준을 충족하지 못했습니다."
                })
        except Exception as e:
            results.append({
                "server": name,
                "status": "error",
                "error": str(e),
                "troubleshoot": f"서버 '{name}' 실행 중 에러 발생: {e}"
            })

    report_lines = [
        "⚡ **ARIA MCP E2E 심층 검증 진단 결과 (하드 인터셉트)**",
        ""
    ]
    for r in results:
        name = r["server"]
        if r["status"] == "success":
            report_lines.append(f"✅ **{name}**: 정상 가동 중. {r['data_summary']}. ({r['elapsed']} ms)")
        elif r["status"] == "offline":
            report_lines.append(f"❌ **{name}**: 🔴 오프라인 (Disconnected)")
            report_lines.append(f"  - *원인*: {r['error']}")
            report_lines.append(f"  - *해결 방안*: {r['troubleshoot']}")
        else:
            report_lines.append(f"❌ **{name}**: 🔴 오동작 (Execution Error)")
            report_lines.append(f"  - *에러 내용*: `{r['error']}`")
            report_lines.append(f"  - *해결 방안*: {r['troubleshoot']}")
        report_lines.append("")

    return "\n".join(report_lines)


# ──────────────────────────────────────────────
# ARIA Chat HTTP API (Fallback)
# ──────────────────────────────────────────────
@app.post("/api/chat", response_model=ChatResponse)
async def http_chat_endpoint(request: Request):
    body = await request.json()
    query = body.get("message", "").strip()
    image_path = body.get("image_path", None)
    
    print(f"[HTTP Chat] 자연어 쿼리 수신: {query}")

    # ── HITL 승인 / 거절 인터셉트 ──
    from aria.mcp.mcp_client import pending_approvals, pending_approvals_lock
    if "http" in pending_approvals:
        choice = query.strip().upper()
        if choice in ("Y", "승인", "YES"):
            with pending_approvals_lock:
                pending_approvals["http"]["decision"] = True
                pending_approvals["http"]["event"].set()
            return ChatResponse(
                status="success",
                reply="사용자 승인을 확인했습니다. 명령을 계속 실행합니다.",
                thoughts=[ThoughtRecord(type="thought", content="사용자의 보안 승인을 감지했습니다. 명령 실행을 재개합니다.")]
            )
        elif choice in ("N", "거절", "NO"):
            with pending_approvals_lock:
                pending_approvals["http"]["decision"] = False
                pending_approvals["http"]["event"].set()
            return ChatResponse(
                status="success",
                reply="사용자 거절을 확인했습니다. 도구 실행을 취소하고 대안을 탐색합니다.",
                thoughts=[ThoughtRecord(type="thought", content="사용자의 보안 거절을 감지했습니다. 도구 실행을 취소합니다.")]
            )

    # ── 하드 인터셉트 라우팅 (verify_mcp / test_mcp) ──
    if query.startswith("/verify_mcp") or query.startswith("/test_mcp"):
        print(f"[HTTP Chat Intercept] E2E MCP 검증 실행: {query}")
        verify_res = execute_mcp_verification(query)
        
        # DB 기록
        db_q = SessionLocal()
        try:
            db_q.add(AgentMemory(session_id="default", role="user", content=query))
            db_q.add(AgentMemory(session_id="default", role="agent", content=verify_res))
            db_q.commit()
        except Exception as e:
            db_q.rollback()
            print(f"[DB Intercept] 저장 실패: {e}")
        finally:
            db_q.close()
            
        return ChatResponse(
            status="success",
            reply=verify_res,
            thoughts=[ThoughtRecord(type="thought", content="사용자의 E2E MCP 검증 명령어를 감지하여 LLM 및 ReAct 루프를 완전히 우회하고 다이렉트로 검증합니다.")]
        )

    # ── 하드 인터셉트 라우팅 (/mcp tool_name args) ──
    if query.startswith("/mcp"):
        print(f"[HTTP Chat Intercept] MCP 매크로 실행: {query}")
        parts = query.strip().split(maxsplit=2)
        tool_name = parts[1] if len(parts) > 1 else None
        params_str = parts[2] if len(parts) > 2 else "{}"
        
        server_names = ['filesystem', 'shell_exec', 'weather', 'web_search', 'arxiv', 'youtube', 'huggingface', 'google-workspace']
        if tool_name == "run" and len(parts) > 2 and parts[2].strip() in server_names:
            tool_name = parts[2].strip()
            params_str = "{}"
        if tool_name in server_names:
            server_greetings = {
                "arxiv": "📚 arXiv 논문 검색 시스템에 연결했습니다. 어떤 분야의 논문을 찾아드릴까요?",
                "huggingface": "🤗 HuggingFace 모델 라이브러리에 연결했습니다. 찾으시는 모델명이나 태스크(예: text-generation, image-classification)를 입력해 주세요.",
                "web_search": "🔍 실시간 웹 검색 및 DuckDuckGo 검색 엔진에 연결했습니다. 어떤 정보를 검색해 드릴까요?",
                "weather": "☀️ 기상 정보 및 지역 날씨 정보 조회 시스템에 연결했습니다. 날씨를 알고 싶은 도시명을 입력해 주세요.",
                "youtube": "🎥 YouTube 동영상 검색 및 영상 요약 시스템에 연결했습니다. 보고 싶으신 영상의 키워드나 주제를 입력해 주세요.",
                "filesystem": "📁 로컬 파일 시스템 제어 센터에 연결했습니다. 읽거나 수정하고 싶으신 파일의 경로를 알려주세요.",
                "shell_exec": "🤖 시스템 터미널 및 명령 실행 제어기에 연결했습니다. 실행할 Bash 명령어를 입력해 주세요.",
                "google-workspace": "📧 Google Workspace(Gmail/Drive) 서비스에 연결했습니다. 메일 검색, 문서 목록 조회 등 원하시는 작업을 말씀해 주세요."
            }
            reply = server_greetings.get(tool_name, f"🤖 {tool_name} 툴을 준비했습니다. 내용을 입력하세요.")
            
            db_call = SessionLocal()
            try:
                db_call.add(AgentMemory(session_id="default", role="user", content=query))
                db_call.add(AgentMemory(session_id="default", role="agent", content=reply))
                db_call.commit()
            except Exception as db_err:
                db_call.rollback()
            finally:
                db_call.close()
                
            return ChatResponse(
                status="success",
                reply=reply,
                thoughts=[ThoughtRecord(type="thought", content=f"사용자 매크로 요청에 따라 {tool_name} 툴 활성화 안내 전송")]
            )
            
        if not tool_name:
            return ChatResponse(
                status="success",
                reply="❌ 도구 이름이 명시되지 않았습니다. 사용법: `/mcp <tool_name> <json_args>`",
                thoughts=[ThoughtRecord(type="thought", content="사용자 매크로 명령어에 도구 이름 누락")]
            )
            
        try:
            params = json.loads(params_str)
        except Exception as e:
            return ChatResponse(
                status="success",
                reply=f"❌ JSON 파싱 에러: {e}",
                thoughts=[ThoughtRecord(type="thought", content=f"파라미터 JSON 파싱 실패: {params_str}")]
            )
            
        if not mcp_client:
            return ChatResponse(
                status="success",
                reply="❌ MCP 클라이언트가 실행 중이 아닙니다.",
                thoughts=[ThoughtRecord(type="thought", content="MCP client offline")]
            )
            
        try:
            t_start = time.time()
            res = mcp_client.call_tool(tool_name, params)
            elapsed = round((time.time() - t_start) * 1000, 2)
            res_str = json.dumps(res, ensure_ascii=False)
            
            reply = f"✅ **/mcp {tool_name} 실행 완료 ({elapsed} ms)**\n\n```json\n{json.dumps(res, indent=2, ensure_ascii=False)}\n```"
            
            # DB logging
            db_call = SessionLocal()
            try:
                db_call.add(AgentMemory(session_id="default", role="user", content=query))
                db_call.add(AgentMemory(session_id="default", role="agent", content=f"[Thought] 사용자 매크로를 통해 MCP 도구 '{tool_name}'를 다이렉트로 실행합니다."))
                truncated_res = res_str[:1000] + "... (생략)" if len(res_str) > 1000 else res_str
                db_call.add(AgentMemory(session_id="default", role="tool", content=f"🔧 [Tool Start via Macro] {tool_name}({params})"))
                db_call.add(AgentMemory(session_id="default", role="tool", content=f"✅ [Tool End via Macro] {tool_name} -> {truncated_res}"))
                db_call.add(AgentMemory(session_id="default", role="agent", content=reply))
                db_call.commit()
            except Exception as db_err:
                db_call.rollback()
                print(f"[DB MCP Macro HTTP] 에러: {db_err}")
            finally:
                db_call.close()
                
            return ChatResponse(
                status="success",
                reply=reply,
                thoughts=[
                    ThoughtRecord(type="thought", content=f"사용자 매크로를 통해 MCP 도구 '{tool_name}'를 다이렉트로 실행합니다."),
                    ThoughtRecord(type="tool_start", tool=tool_name, result=json.dumps(params)),
                    ThoughtRecord(type="tool_end", tool=tool_name, result=res_str)
                ]
            )
        except Exception as tool_err:
            reply_err = f"❌ **/mcp {tool_name} 실행 에러**\n\n`{tool_err}`"
            
            db_err = SessionLocal()
            try:
                db_err.add(AgentMemory(session_id="default", role="user", content=query))
                db_err.add(AgentMemory(session_id="default", role="tool", content=f"❌ [Tool Error via Macro] {tool_name} -> {tool_err}"))
                db_err.add(AgentMemory(session_id="default", role="agent", content=reply_err))
                db_err.commit()
            except Exception:
                db_err.rollback()
            finally:
                db_err.close()
                
            return ChatResponse(
                status="success",
                reply=reply_err,
                thoughts=[
                    ThoughtRecord(type="thought", content=f"MCP '{tool_name}' 실행 중 에러 발생: {tool_err}"),
                    ThoughtRecord(type="tool_start", tool=tool_name, result=json.dumps(params)),
                    ThoughtRecord(type="tool_end", tool=tool_name, result=f"Error: {tool_err}")
                ]
            )
    
    if not agent:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="⚠️ 에이전트 엔진이 백그라운드에서 초기화 중입니다. 잠시만 기다린 후 다시 시도해 주세요.")
        
    # 1. 사용자 입력 DB 기록
    db_q = SessionLocal()
    try:
        db_q.add(AgentMemory(session_id="default", role="user", content=query))
        db_q.commit()
    except Exception as e:
        db_q.rollback()
        print(f"[DB] HTTP Chat user query 저장 에러: {e}")
    finally:
        db_q.close()

    collected_thoughts = []
    def http_callback(msg):
        if msg.get("type") == "agent_status":
            agent_name = msg.get("agent")
            if agent_name:
                # [LED] {state, detail} 포맷으로 정규화하여 저장
                agent_status_cache[agent_name] = {
                    "state":  msg.get("state",  "idle"),
                    "detail": msg.get("detail", msg.get("message", ""))
                }
            msg["source"] = "chat"
            asyncio.run_coroutine_threadsafe(manager.broadcast(msg), loop)
            return

        if msg.get("type") in ("thought", "tool_start", "tool_end"):
            collected_thoughts.append(msg)
            # DB에 생각/도구 이력 기록
            db_call = SessionLocal()
            try:
                msg_type = msg.get("type")
                content = msg.get("content") or ""
                if msg_type == "thought":
                    db_call.add(AgentMemory(session_id="default", role="agent", content=f"[Thought] {content}"))
                elif msg_type == "tool_start":
                    db_call.add(AgentMemory(session_id="default", role="tool", content=f"🔧 [Tool Start] {msg.get('tool')}({msg.get('params')})"))
                elif msg_type == "tool_end":
                    res_str = str(msg.get("result"))
                    if len(res_str) > 1000:
                        res_str = res_str[:1000] + "... (생략)"
                    db_call.add(AgentMemory(session_id="default", role="tool", content=f"✅ [Tool End] {msg.get('tool')} -> {res_str}"))
                db_call.commit()
            except Exception as e:
                db_call.rollback()
                print(f"[DB HTTP Callback] 에러: {e}")
            finally:
                db_call.close()
            
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        def run_http_agent():
            from aria.mcp.mcp_client import current_channel
            current_channel.channel_type = "http"
            return agent.run(user_input=query, image_path=image_path, callback=http_callback)

        res = await loop.run_in_executor(
            None,
            run_http_agent
        )
        reply = res.get("reply", "")

        # 2. 에이전트 최종 답변 DB 기록
        db_ans = SessionLocal()
        try:
            db_ans.add(AgentMemory(session_id="default", role="agent", content=reply))
            db_ans.commit()
        except Exception as e:
            db_ans.rollback()
            print(f"[DB] HTTP Chat agent reply 저장 에러: {e}")
        finally:
            db_ans.close()

        # Pydantic 호환 응답 리턴
        thoughts_payload = []
        for t in collected_thoughts:
            thoughts_payload.append(ThoughtRecord(
                type=t.get("type"),
                content=t.get("content"),
                tool=t.get("tool"),
                result=t.get("result")
            ))

        return ChatResponse(
            status="success",
            reply=reply,
            thoughts=thoughts_payload
        )
    except Exception as e:
        import traceback
        print(f"[HTTP Chat] 실행 실패: {e}\n{traceback.format_exc()}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"❌ 에이전트 실행 중 오류가 발생했습니다: {e}")


# ──────────────────────────────────────────────
# ARIA Chat WebSocket API
# ──────────────────────────────────────────────
import asyncio

@app.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    print(f"[WebSocket] ARIA Chat 클라이언트가 연결되었습니다. (총 {len(manager.active_connections)}명)")

    # 1. 연결 시 이미 요청되어 있는 OAuth URL이 있다면 즉시 뿜어줌
    if mcp_client:
        try:
            urls = mcp_client.get_oauth_urls()
            for name, url in urls.items():
                await websocket.send_json({
                    "type": "oauth_url",
                    "server": name,
                    "url": url
                })
        except Exception:
            pass

    # 2. 2초 주기로 구글 OAuth 승인 요청을 모니터링하는 태스크
    async def oauth_monitor():
        last_urls = {}
        try:
            while True:
                if mcp_client:
                    try:
                        urls = mcp_client.get_oauth_urls()
                        for name, url in urls.items():
                            if last_urls.get(name) != url:
                                print(f"[WebSocket] OAuth 감지 ({name}) -> 전송")
                                await websocket.send_json({
                                    "type": "oauth_url",
                                    "server": name,
                                    "url": url
                                })
                        last_urls = dict(urls)
                    except Exception:
                        pass
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass

    monitor_task = asyncio.create_task(oauth_monitor())

    # 3. 챗 수신 및 에이전트 자율 Tool Calling 핸들링 루프
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "chat":
                query = data.get("message", "").strip()
                print(f"[WebSocket] 자연어 쿼리 수신: {query}")

                # ── HITL 승인 / 거절 인터셉트 ──
                from aria.mcp.mcp_client import pending_approvals, pending_approvals_lock
                if "websocket" in pending_approvals:
                    choice = query.strip().upper()
                    if choice in ("Y", "승인", "YES"):
                        with pending_approvals_lock:
                            pending_approvals["websocket"]["decision"] = True
                            pending_approvals["websocket"]["event"].set()
                        await websocket.send_json({
                            "type": "thought",
                            "content": "사용자 승인을 감지했습니다. 명령을 계속 실행합니다."
                        })
                        continue
                    elif choice in ("N", "거절", "NO"):
                        with pending_approvals_lock:
                            pending_approvals["websocket"]["decision"] = False
                            pending_approvals["websocket"]["event"].set()
                        await websocket.send_json({
                            "type": "thought",
                            "content": "사용자 거절을 감지했습니다. 도구 실행을 취소하고 대안을 탐색합니다."
                        })
                        continue
                    else:
                        await websocket.send_json({
                            "type": "thought",
                            "content": "⚠️ 승인 대기 중입니다. 'Y'(승인) 또는 'N'(거절)을 입력해 주세요."
                        })
                        continue

                # ── 하드 인터셉트 라우팅 (verify_mcp / test_mcp) ──
                if query.startswith("/verify_mcp") or query.startswith("/test_mcp"):
                    print(f"[WebSocket Intercept] E2E MCP 검증 실행: {query}")
                    verify_res = execute_mcp_verification(query)
                    
                    # DB 기록
                    db_q = SessionLocal()
                    try:
                        db_q.add(AgentMemory(session_id="default", role="user", content=query))
                        db_q.add(AgentMemory(session_id="default", role="agent", content=verify_res))
                        db_q.commit()
                    except Exception as e:
                        db_q.rollback()
                        print(f"[DB WS Intercept] 저장 실패: {e}")
                    finally:
                        db_q.close()
                    
                    # 즉시 클라이언트로 전송
                    await websocket.send_json({
                        "type": "thought",
                        "content": "사용자의 E2E MCP 검증 명령어를 감지하여 LLM 및 ReAct 루프를 완전히 우회하고 다이렉트로 검증합니다.",
                        "source": "chat"
                    })
                    await websocket.send_json({
                        "type": "response",
                        "content": verify_res,
                        "source": "chat"
                    })
                    continue

                # ── 하드 인터셉트 라우팅 (/mcp tool_name args) ──
                if query.startswith("/mcp"):
                    print(f"[WebSocket Intercept] MCP 매크로 실행: {query}")
                    parts = query.strip().split(maxsplit=2)
                    tool_name = parts[1] if len(parts) > 1 else None
                    params_str = parts[2] if len(parts) > 2 else "{}"
                    
                    server_names = ['filesystem', 'shell_exec', 'weather', 'web_search', 'arxiv', 'youtube', 'huggingface', 'google-workspace']
                    if tool_name == "run" and len(parts) > 2 and parts[2].strip() in server_names:
                        tool_name = parts[2].strip()
                        params_str = "{}"
                    if tool_name in server_names:
                        server_greetings = {
                            "arxiv": "📚 arXiv 논문 검색 시스템에 연결했습니다. 어떤 분야의 논문을 찾아드릴까요?",
                            "huggingface": "🤗 HuggingFace 모델 라이브러리에 연결했습니다. 찾으시는 모델명이나 태스크(예: text-generation, image-classification)를 입력해 주세요.",
                            "web_search": "🔍 실시간 웹 검색 및 DuckDuckGo 검색 엔진에 연결했습니다. 어떤 정보를 검색해 드릴까요?",
                            "weather": "☀️ 기상 정보 및 지역 날씨 정보 조회 시스템에 연결했습니다. 날씨를 알고 싶은 도시명을 입력해 주세요.",
                            "youtube": "🎥 YouTube 동영상 검색 및 영상 요약 시스템에 연결했습니다. 보고 싶으신 영상의 키워드나 주제를 입력해 주세요.",
                            "filesystem": "📁 로컬 파일 시스템 제어 센터에 연결했습니다. 읽거나 수정하고 싶으신 파일의 경로를 알려주세요.",
                            "shell_exec": "🤖 시스템 터미널 및 명령 실행 제어기에 연결했습니다. 실행할 Bash 명령어를 입력해 주세요.",
                            "google-workspace": "📧 Google Workspace(Gmail/Drive) 서비스에 연결했습니다. 메일 검색, 문서 목록 조회 등 원하시는 작업을 말씀해 주세요."
                        }
                        reply = server_greetings.get(tool_name, f"🤖 {tool_name} 툴을 준비했습니다. 내용을 입력하세요.")
                        
                        db_q = SessionLocal()
                        try:
                            db_q.add(AgentMemory(session_id="default", role="user", content=query))
                            db_q.add(AgentMemory(session_id="default", role="agent", content=reply))
                            db_q.commit()
                        except Exception:
                            db_q.rollback()
                        finally:
                            db_q.close()
                            
                        await websocket.send_json({
                            "type": "thought",
                            "content": f"사용자 매크로 요청에 따라 {tool_name} 툴 활성화 안내 전송",
                            "source": "chat"
                        })
                        await websocket.send_json({
                            "type": "response",
                            "content": reply,
                            "source": "chat"
                        })
                        continue
                        
                    if not tool_name:
                        await websocket.send_json({
                            "type": "thought",
                            "content": "사용자 매크로 명령어에 도구 이름이 명시되지 않았습니다.",
                            "source": "chat"
                        })
                        await websocket.send_json({
                            "type": "response",
                            "content": "❌ 도구 이름이 명시되지 않았습니다. 사용법: `/mcp <tool_name> <json_args>`",
                            "source": "chat"
                        })
                        continue
                        
                    try:
                        params = json.loads(params_str)
                    except Exception as e:
                        await websocket.send_json({
                            "type": "thought",
                            "content": f"JSON 파싱 실패: {params_str}",
                            "source": "chat"
                        })
                        await websocket.send_json({
                            "type": "response",
                            "content": f"❌ JSON 파싱 에러: {e}",
                            "source": "chat"
                        })
                        continue
                        
                    if not mcp_client:
                        await websocket.send_json({
                            "type": "thought",
                            "content": "MCP 클라이언트가 비활성화 상태입니다.",
                            "source": "chat"
                        })
                        await websocket.send_json({
                            "type": "response",
                            "content": "❌ MCP 클라이언트가 실행 중이 아닙니다.",
                            "source": "chat"
                        })
                        continue
                        
                    # Save user query to DB
                    db_q = SessionLocal()
                    try:
                        db_q.add(AgentMemory(session_id="default", role="user", content=query))
                        db_q.commit()
                    except Exception as db_err:
                        db_q.rollback()
                    finally:
                        db_q.close()
                        
                    await websocket.send_json({
                        "type": "thought",
                        "content": f"사용자 매크로를 통해 MCP 도구 '{tool_name}'를 즉시 직접 호출합니다 (LLM 우회).",
                        "source": "chat"
                    })
                    
                    # Tool Start
                    await websocket.send_json({
                        "type": "tool_start",
                        "tool": tool_name,
                        "params": params,
                        "source": "chat"
                    })
                    
                    db_call = SessionLocal()
                    try:
                        db_call.add(AgentMemory(session_id="default", role="agent", content=f"[Thought] 사용자 매크로를 통해 MCP 도구 '{tool_name}'를 즉시 직접 호출합니다 (LLM 우회)."))
                        db_call.add(AgentMemory(session_id="default", role="tool", content=f"🔧 [Tool Start via Macro] {tool_name}({params})"))
                        db_call.commit()
                    except Exception:
                        db_call.rollback()
                    finally:
                        db_call.close()
                        
                    # Execute tool
                    try:
                        t_start = time.time()
                        
                        loop = asyncio.get_running_loop()
                        res = await loop.run_in_executor(
                            None,
                            lambda: mcp_client.call_tool(tool_name, params)
                        )
                        elapsed = round((time.time() - t_start) * 1000, 2)
                        
                        res_str = json.dumps(res, ensure_ascii=False)
                        
                        # Send tool end
                        await websocket.send_json({
                            "type": "tool_end",
                            "tool": tool_name,
                            "result": res_str,
                            "source": "chat"
                        })
                        
                        reply = f"✅ **/mcp {tool_name} 실행 완료 ({elapsed} ms)**\n\n```json\n{json.dumps(res, indent=2, ensure_ascii=False)}\n```"
                        
                        # Send final response
                        await websocket.send_json({
                            "type": "response",
                            "content": reply,
                            "source": "chat"
                        })
                        
                        # Save tool end and reply to DB
                        db_end = SessionLocal()
                        try:
                            truncated_res = res_str[:1000] + "... (생략)" if len(res_str) > 1000 else res_str
                            db_end.add(AgentMemory(session_id="default", role="tool", content=f"✅ [Tool End via Macro] {tool_name} -> {truncated_res}"))
                            db_end.add(AgentMemory(session_id="default", role="agent", content=reply))
                            db_end.commit()
                        except Exception:
                            db_end.rollback()
                        finally:
                            db_end.close()
                            
                    except Exception as tool_err:
                        reply_err = f"❌ **/mcp {tool_name} 실행 에러**\n\n`{tool_err}`"
                        await websocket.send_json({
                            "type": "tool_end",
                            "tool": tool_name,
                            "result": f"Error: {tool_err}",
                            "source": "chat"
                        })
                        await websocket.send_json({
                            "type": "response",
                            "content": reply_err,
                            "source": "chat"
                        })
                        # Save error to DB
                        db_err = SessionLocal()
                        try:
                            db_err.add(AgentMemory(session_id="default", role="tool", content=f"❌ [Tool Error via Macro] {tool_name} -> {tool_err}"))
                            db_err.add(AgentMemory(session_id="default", role="agent", content=reply_err))
                            db_err.commit()
                        except Exception:
                            db_err.rollback()
                        finally:
                            db_err.close()
                    continue

                # 1. 사용자 입력 DB 기록
                db_q = SessionLocal()
                try:
                    db_q.add(AgentMemory(session_id="default", role="user", content=query))
                    db_q.commit()
                except Exception as e:
                    db_q.rollback()
                    print(f"[DB WS] query 저장 실패: {e}")
                finally:
                    db_q.close()

                # 백그라운드 스레드 내부에서 웹소켓 송신을 안전하게 호출하기 위한 콜백
                loop = asyncio.get_running_loop()
                def agent_callback(msg):
                    if msg.get("type") == "agent_status":
                        agent_name = msg.get("agent")
                        if agent_name:
                            # [LED] {state, detail} 포맷으로 정규화하여 저장
                            agent_status_cache[agent_name] = {
                                "state":  msg.get("state",  "idle"),
                                "detail": msg.get("detail", msg.get("message", ""))
                            }

                    msg["source"] = "chat"
                    asyncio.run_coroutine_threadsafe(
                        websocket.send_json(msg),
                        loop
                    )
                    
                    # 2. 에이전트 생각, 도구 사용, 최종 응답 DB 기록
                    m_type = msg.get("type")
                    if m_type == "agent_status":
                        return

                    db_msg = SessionLocal()
                    try:
                        m_content = msg.get("content") or ""
                        if m_type == "thought":
                            db_msg.add(AgentMemory(session_id="default", role="agent", content=f"[Thought] {m_content}"))
                        elif m_type == "tool_start":
                            db_msg.add(AgentMemory(session_id="default", role="tool", content=f"🔧 [Tool Start] {msg.get('tool')}({msg.get('params')})"))
                        elif m_type == "tool_end":
                            res_str = str(msg.get("result"))
                            if len(res_str) > 1000:
                                res_str = res_str[:1000] + "... (생략)"
                            db_msg.add(AgentMemory(session_id="default", role="tool", content=f"✅ [Tool End] {msg.get('tool')} -> {res_str}"))
                        elif m_type == "response":
                            db_msg.add(AgentMemory(session_id="default", role="agent", content=m_content))
                        db_msg.commit()
                    except Exception as e:
                        db_msg.rollback()
                        print(f"[DB WS Callback] 에러: {e}")
                    finally:
                        db_msg.close()

                def run_agent_worker(q, cb):
                    try:
                        if agent:
                            from aria.mcp.mcp_client import current_channel
                            current_channel.channel_type = "websocket"
                            current_channel.websocket = websocket
                            current_channel.loop = loop
                            agent.run(user_input=q, callback=cb)
                        else:
                            cb({
                                "type": "response",
                                "content": "⚠️ 에이전트 엔진이 백그라운드에서 초기화 중입니다. 잠시만 기다린 후 다시 시도해 주세요."
                            })
                    except Exception as ex:
                        cb({"type": "response", "content": f"❌ 에이전트 실행 실패: {ex}"})

                threading.Thread(target=run_agent_worker, args=(query, agent_callback), daemon=True).start()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        monitor_task.cancel()
        print("[WebSocket] ARIA Chat 클라이언트 연결 종료")


# 앱 시작 시 초기화
# ──────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    init_db()
    print("[DB] 데이터베이스 테이블 초기화 완료 (argus_core.db)")
    print(f"\n{'='*60}")
    print(f"  🖥️  ARIA (Anomaly Reasoning Intelligence Agent) Dashboard")
    print(f"{'='*60}")
    print(f"  Memory Bank : {MEMORY_BANK_PATH}")
    print(f"  Threshold   : {THRESHOLD}")
    print(f"  Dashboard   : http://127.0.0.1:8080")
    print(f"{'='*60}\n")
    
    # Event Bus 시작
    from aria.orchestration.event_bus import event_bus
    await event_bus.start()
    print("[EventBus] 중앙 비동기 이벤트 버스 시작 완료")
    
    from aria.learning.training.events import TRAINING_TOPIC
    async def _bridge_training_to_ws(event: dict):
        if event.get("preview_image"):
            import os
            p = event["preview_image"].replace("\\", "/")
            if "uploads/" in p:
                event["preview_image"] = "/uploads/" + p.split("uploads/")[1]
        await manager.broadcast(event)

    event_bus.subscribe(TRAINING_TOPIC, _bridge_training_to_ws)
    
    # MCP 및 에이전트 시스템 백그라운드 시작
    threading.Thread(target=start_mcp_in_background, daemon=True).start()


@app.on_event("shutdown")
async def shutdown_event():
    from aria.orchestration.event_bus import event_bus
    await event_bus.stop()
    print("[EventBus] 중앙 비동기 이벤트 버스 중지 완료")


# ── R-2 모니터 브릿지: 로봇 관절 상태를 WS로 스트리밍 ──────────────────────
@app.post("/api/robot/demo")
async def robot_demo(payload: dict = Body(...)):
    """백엔드 관절 상태를 WS joint_state 이벤트로 브로드캐스트.

    - action="start" → 백그라운드 루프 시작 (0.05 s 간격, ~20 fps)
    - action="stop"  → 루프 정지
    Three.js RobotArm이 이 이벤트를 받아 Math.sin 대신 실제 각도로 포즈.
    """
    import asyncio, math, threading

    action = payload.get("action", "start")

    if action == "stop":
        app.state._robot_demo_running = False
        return {"ok": True, "action": "stopped"}

    if getattr(app.state, "_robot_demo_running", False):
        return {"ok": True, "action": "already_running"}

    app.state._robot_demo_running = True
    loop = asyncio.get_running_loop()

    def _demo_loop():
        import time
        t = 0.0
        while getattr(app.state, "_robot_demo_running", False):
            # 데모 웨이브폼 (mujoco 없이도 "진짜 데이터처럼" 보이는 부드러운 움직임)
            js = {
                "L_j1": math.sin(t * 0.5) * 0.6,
                "L_j2": math.sin(t * 0.7) * 0.5 + 0.3,
                "L_j3": math.sin(t * 0.9) * 0.4,
                "L_g":  math.sin(t * 1.2) * 0.015,
                "R_j1": math.sin(t * 0.5 + 1.0) * 0.6,
                "R_j2": math.sin(t * 0.7 + 1.0) * 0.5 + 0.3,
                "R_j3": math.sin(t * 0.9 + 1.0) * 0.4,
                "R_g":  math.sin(t * 1.2 + 1.0) * 0.015,
            }
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "joint_state", "joints": js}), loop
            )
            t += 0.05
            time.sleep(0.05)

    threading.Thread(target=_demo_loop, daemon=True).start()
    return {"ok": True, "action": "started"}


# ── 비전 검사 노드 (ARIA_Vision_Inspection_Node_Spec §10-5: 비병목 노드 HMI 연동) ──
# 비병목 파이프라인을 /api/inspector/* 로 제어하고, 텔레메트리를 WS(inspector_result/state)로 송출.
def _inspector_collect_images(category: str, limit: int = 60):
    import glob
    from pathlib import Path
    cat = BASE_DIR / "data" / category
    good, defect = [], []
    test = cat / "test"
    if test.is_dir():
        for sub in sorted(test.iterdir()):
            if not sub.is_dir():
                continue
            files = [str(p) for p in sorted(sub.glob("*")) if p.suffix.lower() in IMG_EXT]
            (good if sub.name.lower() == "good" else defect).extend(files)
    out = []
    for i in range(max(len(good), len(defect))):
        if i < len(good):
            out.append(good[i])
        if i < len(defect):
            out.append(defect[i])
    return out[:limit] if limit else out


@app.post("/api/inspector/start")
async def inspector_start(payload: dict = Body(default={})):
    import asyncio
    from aria.inspection.async_pipeline import AsyncPipeline, MockDriver, mock_infer_factory
    from aria.inspection.twin_bridge import TwinBridge, WsFloorSink

    if getattr(app.state, "_inspector", None) and app.state._inspector.get("running"):
        return {"ok": False, "error": "이미 가동 중 — 먼저 stop"}

    mode = payload.get("mode", "mock")           # mock | patchcore
    category = payload.get("category", "bottle")
    tau = float(payload.get("tau", 0.5))
    q = int(payload.get("queue", 4))
    workers = int(payload.get("workers", 2))
    line_hz = float(payload.get("line_hz", 20.0))
    # 라이브 조정용 홀더(set_latency가 갱신)
    holder = {"infer_ms": float(payload.get("infer_ms", 40.0)),
              "extra_ms": float(payload.get("inflate_ms", 0.0))}

    # 추론 함수 구성 (추론 재작성 X — 기존 디텍터 주입)
    if mode in ("patchcore", "combined"):
        import time as _t
        from aria.inspection.detectors import PatchCoreDetector
        bank = BANKS_DIR / f"{category}.npy"
        if not bank.exists():
            return {"ok": False, "error": f"뱅크 없음: banks/{category}.npy — 먼저 학습/생성"}
        detector = PatchCoreDetector(str(bank), tau=tau)
        if mode == "combined":
            from aria.inspection.detectors import YoloDetector, CombinedDetector
            w = BASE_DIR / "models" / "yolo" / f"{category}.pt"
            if not w.exists():
                return {"ok": False, "error": f"YOLO weights 없음: models/yolo/{category}.pt — 먼저 학습"}
            detector = CombinedDetector(detector, YoloDetector(str(w), conf=0.25), tau=tau)
        images = _inspector_collect_images(category, limit=80)
        if not images:
            return {"ok": False, "error": f"이미지 없음: data/{category}/test"}
        detector.infer(images[0])                 # 백본/모델 웜업

        def infer_fn(image):
            out = detector.infer(image)
            if holder["extra_ms"] > 0:
                _t.sleep(holder["extra_ms"] / 1000.0)
            return out
        driver = MockDriver(grab_ms=2.0, image_paths=images)
    else:
        infer_fn = mock_infer_factory(lambda: holder["infer_ms"])
        driver = MockDriver(grab_ms=2.0, seed=7)

    loop = asyncio.get_running_loop()

    def _ws(msg):
        # 파이프라인 result/state → inspector_* 타입으로 내부 트윈(/ws) 송출
        t = msg.get("type")
        out = {**msg, "type": f"inspector_{t}"}
        asyncio.run_coroutine_threadsafe(manager.broadcast(out), loop)

    bridge = TwinBridge([WsFloorSink(_ws)])
    pipe = AsyncPipeline(driver, infer_fn, tau=tau, queue_capacity=q,
                         n_workers=workers, telemetry_cb=bridge.telemetry_cb())
    pipe.start()
    bridge.start_state_pump(pipe.snapshot, hz=5.0)

    import threading

    def _trigger_loop():
        interval = 1.0 / max(0.1, line_hz)
        while app.state._inspector.get("running"):
            pipe.trigger()
            time.sleep(interval)

    app.state._inspector = {"running": True, "pipe": pipe, "bridge": bridge,
                            "holder": holder, "mode": mode, "category": category}
    th = threading.Thread(target=_trigger_loop, name="inspector-trigger", daemon=True)
    th.start()
    app.state._inspector["trigger_thread"] = th
    return {"ok": True, "mode": mode, "category": category, "line_hz": line_hz}


@app.post("/api/inspector/stop")
async def inspector_stop():
    ins = getattr(app.state, "_inspector", None)
    if not ins or not ins.get("running"):
        return {"ok": True, "note": "이미 정지"}
    ins["running"] = False
    th = ins.get("trigger_thread")
    if th:
        th.join(timeout=1.0)
    try:
        ins["pipe"].stop()
        ins["bridge"].stop()
    except Exception as e:
        return {"ok": True, "warn": str(e)}
    return {"ok": True}


@app.post("/api/inspector/set_latency")
async def inspector_set_latency(payload: dict = Body(...)):
    ins = getattr(app.state, "_inspector", None)
    if not ins or not ins.get("running"):
        return {"ok": False, "error": "가동 중 아님"}
    h = ins["holder"]
    if "infer_ms" in payload:
        h["infer_ms"] = float(payload["infer_ms"])
    if "inflate_ms" in payload:
        h["extra_ms"] = float(payload["inflate_ms"])
    return {"ok": True, "infer_ms": h["infer_ms"], "inflate_ms": h["extra_ms"]}


@app.get("/api/inspector/state")
async def inspector_state():
    ins = getattr(app.state, "_inspector", None)
    if not ins or not ins.get("running"):
        return {"ok": True, "running": False}
    pipe = ins["pipe"]
    snap = pipe.snapshot()
    recent = [
        {"part_id": r.part_id, "verdict": r.verdict, "score": round(r.score, 4),
         "latency_ms": r.latency_ms, "defect_class": r.defect_class}
        for r in list(pipe.results())[-12:]
    ]
    return {"ok": True, "running": True, "mode": ins["mode"],
            "category": ins["category"], "snapshot": snap, "recent": recent}


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """SPA fallback redirecting all unknown routes to React root."""
    return FileResponse("frontend/dist/index.html")


# ──────────────────────────────────────────────
# 직접 실행 진입점
# python app.py 로 실행하면 포트 8080에서 uvicorn 자동 구동
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info",
    )
