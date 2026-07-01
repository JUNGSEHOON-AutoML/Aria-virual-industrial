#!/bin/bash
# ARIA 공식 진입점 — 모듈형 백엔드(server/, :8200) + Vite HMI(:5173)
#
# [B5 컷오버 완료 2026-07-01]
# 구 레거시 app.py(:8080)는 폐기됨. 이 스크립트가 유일한 기동 스크립트.
# 레거시 참조: app.py (aria/agents/ 호환 목적으로만 파일 존재, uvicorn 기동 금지)
#
set -e

export CUDA_VISIBLE_DEVICES=1,2
export PATH="/userHome/userhome4/sehoon/miniconda3/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=/userHome/userhome4/sehoon/miniconda3/envs/patchcore/bin/python
NPM=/userHome/userhome4/sehoon/miniconda3/bin/npm
cd "$ROOT"; mkdir -p logs

echo "🔄 기존 프로세스 정리..."
pkill -f "uvicorn app:app"    2>/dev/null || true   # 레거시 :8080 혹시 실행 중이면 제거
pkill -f "uvicorn server.app" 2>/dev/null || true
pkill -f "vite"               2>/dev/null || true
sleep 1

echo "🚀 [1/2] ARIA API (server/app.py) → :8200"
nohup $PYTHON -m uvicorn server.app:app --host 0.0.0.0 --port 8200 --reload \
    > logs/api_$(date +%Y%m%d).log 2>&1 &
API_PID=$!
echo "  ✅ API PID: $API_PID  ·  로그: tail -f logs/api_$(date +%Y%m%d).log"
sleep 2

echo "🖥️ [2/2] ARIA HMI (Vite dev, /api·/ws → :8200 프록시) → :5173"
cd "$ROOT/frontend"
export BACKEND_HOST=localhost BACKEND_PORT=8200 VITE_API_URL=""
nohup $NPM run dev > "$ROOT/logs/web_$(date +%Y%m%d).log" 2>&1 &
WEB_PID=$!
echo "  ✅ WEB PID: $WEB_PID  ·  로그: tail -f $ROOT/logs/web_$(date +%Y%m%d).log"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🖥️  ARIA HMI   →  http://localhost:5173"
echo "  🔧 API        →  http://localhost:8200/api/health"
echo "  📡 WS         →  ws://localhost:8200/ws/chat (5173 프록시)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "종료: pkill -f 'uvicorn server.app' && pkill -f vite"
