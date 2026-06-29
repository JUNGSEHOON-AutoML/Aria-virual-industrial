#!/bin/bash
# ARIA v2 — 새 모듈형 백엔드(server/, :8200) + Vite 프론트(:5173). 8080 미사용.
# 구 start_aria.sh(8080 app.py)는 B5 컷오버 때 제거.
set -e

export CUDA_VISIBLE_DEVICES=1,2
export PATH="/userHome/userhome4/sehoon/miniconda3/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=/userHome/userhome4/sehoon/miniconda3/envs/patchcore/bin/python
NPM=/userHome/userhome4/sehoon/miniconda3/bin/npm
cd "$ROOT"; mkdir -p logs

echo "🔄 기존 v2 프로세스 정리..."
pkill -f "uvicorn server.app" 2>/dev/null || true
pkill -f "vite"              2>/dev/null || true
sleep 1

echo "🚀 [1/2] ARIA API (모듈형 백엔드) → :8200"
nohup $PYTHON -m uvicorn server.app:app --host 0.0.0.0 --port 8200 --reload \
    > logs/api_$(date +%Y%m%d).log 2>&1 &
echo "  ✅ API PID: $!  ·  로그: tail -f logs/api_$(date +%Y%m%d).log"
sleep 2

echo "🖥️ [2/2] ARIA HMI (Vite dev, /api·/ws → :8200 프록시) → :5173"
cd "$ROOT/frontend"
export BACKEND_HOST=localhost BACKEND_PORT=8200 VITE_API_URL=""
nohup $NPM run dev > "$ROOT/logs/web_$(date +%Y%m%d).log" 2>&1 &
echo "  ✅ WEB PID: $!"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🖥️  ARIA HMI   →  http://localhost:5173   (트윈 HMI)"
echo "  🔧 API        →  http://localhost:8200/api/health"
echo "  📡 WS         →  ws://localhost:8200/ws/chat (5173 프록시)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "종료: pkill -f 'uvicorn server.app' && pkill -f vite"
