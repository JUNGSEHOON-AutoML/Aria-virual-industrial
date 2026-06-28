#!/bin/bash
# ARIA (Anomaly Reasoning Intelligence Agent) 통합 시작 스크립트
# 백엔드(FastAPI, 8080) + 프론트엔드(React/Vite, 5173) 동시 구동
set -e

# GPU 0 하드웨어 오류 우회 (동작하는 1, 2번 GPU만 사용)
export CUDA_VISIBLE_DEVICES=1,2

# Node/NPM 실행을 위해 PATH에 conda bin 폴더 추가
export PATH="/userHome/userhome4/sehoon/miniconda3/bin:$PATH"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=/userHome/userhome4/sehoon/miniconda3/envs/patchcore/bin/python
NPM=/userHome/userhome4/sehoon/miniconda3/bin/npm
FRONTEND_DIR=$ROOT_DIR/frontend

cd "$ROOT_DIR"

# logs 디렉토리 생성
mkdir -p logs

# ── 기존 프로세스 정리 ──
echo "🔄 기존 프로세스 정리 중..."
pkill -f "uvicorn app:app" 2>/dev/null || true
pkill -f "vite"            2>/dev/null || true
sleep 1

# ── React 프론트엔드 빌드 (dist 생성) ──
echo "📦 [0/2] React 프론트엔드 빌드 중..."
cd "$FRONTEND_DIR"
$NPM run build
cd "$ROOT_DIR"

# ── FastAPI 백엔드 기동 (포트 8080) ──
echo "🚀 [1/2] ARIA FastAPI 백엔드 시작 중... (port: 8080)"
nohup $PYTHON -m uvicorn app:app \
    --host 0.0.0.0 \
    --port 8080 \
    --reload \
    > logs/backend_$(date +%Y%m%d).log 2>&1 &
BACKEND_PID=$!
echo "  ✅ 백엔드 PID: $BACKEND_PID"
echo "  📋 로그: tail -f logs/backend_$(date +%Y%m%d).log"

# 백엔드 기동 대기
sleep 2

# ── React 프론트엔드 개발 서버 기동 (포트 5173) ──
echo "🚀 [2/2] React 프론트엔드 개발 서버 시작 중... (port: 5173)"
cd "$FRONTEND_DIR"
export BACKEND_HOST=localhost
export VITE_API_URL=""
nohup $NPM run dev \
    > $ROOT_DIR/logs/frontend_$(date +%Y%m%d).log 2>&1 &
FRONTEND_PID=$!
echo "  ✅ 프론트엔드 PID: $FRONTEND_PID"
echo "  📋 로그: tail -f $ROOT_DIR/logs/frontend_$(date +%Y%m%d).log"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🖥️  ARIA Dashboard (React)  →  http://localhost:5173"
echo "  🔧 FastAPI Backend          →  http://localhost:8080"
echo "  📡 WebSocket Chat           →  ws://localhost:8080/ws/chat"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "종료하려면: pkill -f 'uvicorn app:app' && pkill -f 'vite'"

