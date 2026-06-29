#!/bin/bash
# ARIA (Anomaly Reasoning Intelligence Agent) 통합 시작 스크립트
# 단일 URL: FastAPI(8080)가 React 빌드(frontend/dist)를 직접 서빙 → 접속은 http://localhost:8080 하나로.
# (개발용 Vite HMR이 필요하면 맨 아래 주석 블록 참고)
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

# ── React 프론트엔드 빌드 (dist 생성 → FastAPI가 서빙) ──
echo "📦 [0/1] React 프론트엔드 빌드 중..."
cd "$FRONTEND_DIR"
$NPM run build
cd "$ROOT_DIR"

# ── FastAPI 백엔드 기동 (포트 8080, dist를 직접 서빙) ──
echo "🚀 [1/1] ARIA 시작 중... (단일 포트 8080)"
nohup $PYTHON -m uvicorn app:app \
    --host 0.0.0.0 \
    --port 8080 \
    --reload \
    > logs/backend_$(date +%Y%m%d).log 2>&1 &
BACKEND_PID=$!
echo "  ✅ PID: $BACKEND_PID"
echo "  📋 로그: tail -f logs/backend_$(date +%Y%m%d).log"

# 기동 대기
sleep 2

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🖥️  ARIA Dashboard          →  http://localhost:8080"
echo "  🔧 API (동일 포트)           →  http://localhost:8080/api/..."
echo "  📡 WebSocket Chat           →  ws://localhost:8080/ws/chat"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ 접속 주소가 8080 하나로 통일되었습니다."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "종료하려면: pkill -f 'uvicorn app:app'"

# ──────────────────────────────────────────────────────────────────────────
# [선택] 개발 중 Vite HMR(즉시 반영)이 필요할 때만 아래를 수동 실행:
#   cd frontend && VITE_API_URL="" BACKEND_HOST=localhost npm run dev   # → http://localhost:5173
# 이 경우 5173(프론트 HMR) + 8080(API) 두 포트를 쓰게 됩니다. 평상시엔 빌드+8080 단일 권장.
# ──────────────────────────────────────────────────────────────────────────
