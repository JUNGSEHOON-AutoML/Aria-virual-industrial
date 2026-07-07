#!/bin/bash
# ARIA 2-프로세스 기동 스크립트 (S3b-4 2026-07-02)
#
# 프로세스 경계:
#   P-core     (:8200) — TwinState·Gateway·PdMFusion·WS
#   P-producer (:8201) — PatchCore·YOLO·취득루프·IPC bus
#   HMI        (:5173) — React/Vite (Vite가 /api·/ws를 :8200으로 프록시)
#
# ── 구 단일 프로세스 기동 경로 은퇴 (2026-07-02) ──────────────────────────
# 이전 경로: uvicorn server.app:app 단독 → 검사 기능 포함
# 은퇴 이유: S3b-4 2-프로세스 분리 완료. P-producer가 :8200 안에 있으면
#   크래시 격리(P-producer kill → P-core survive)가 불가능.
# 단일 프로세스가 필요하면: inspection_node.py의 ARIA_CORE_URL=localhost:8200
#   루프백 모드를 사용 (분리 배포 아님, 개발용).
# ─────────────────────────────────────────────────────────────────────────────
set -e

export CUDA_VISIBLE_DEVICES=1,2
# conda env `aria` (Python 3.10 + Node 20) — torch는 cu124 빌드 고정(드라이버 12.4 호환)
export PATH="/userHome/userhome4/sehoon/miniconda3/envs/aria/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/python
NPM=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/npm
cd "$ROOT"
mkdir -p logs

echo "🔄 기존 프로세스 정리..."
pkill -f "uvicorn app:app"                  2>/dev/null || true   # 레거시 :8080
pkill -f "uvicorn server.app"               2>/dev/null || true   # 구 단일 P-core
pkill -f "uvicorn aria.planes.inspection"   2>/dev/null || true   # 구 P-producer
pkill -f "vite"                             2>/dev/null || true
sleep 1

# ── [1/3] P-core (:8200) ────────────────────────────────────────────────────
echo "🚀 [1/3] P-core (server/app.py) → :8200"
nohup $PYTHON -m uvicorn server.app:app \
    --host 0.0.0.0 --port 8200 --reload \
    > logs/core_$(date +%Y%m%d).log 2>&1 &
CORE_PID=$!
echo "  ✅ P-core PID: $CORE_PID  ·  tail -f logs/core_$(date +%Y%m%d).log"

# P-core가 응답할 때까지 대기 (최대 15초)
for i in $(seq 1 15); do
    if curl -sf http://localhost:8200/api/health > /dev/null 2>&1; then
        echo "  ✅ P-core 응답 확인 (${i}s)"
        break
    fi
    sleep 1
done

# ── [2/3] P-producer (:8201) ────────────────────────────────────────────────
echo "🔬 [2/3] P-producer (aria/planes/inspection_node.py) → :8201"
ARIA_CORE_URL=http://localhost:8200 \
ARIA_IPC_BUFFER_MAXLEN=2000 \
PRODUCER_PORT=8201 \
nohup $PYTHON -m uvicorn aria.planes.inspection_node:app \
    --host 0.0.0.0 --port 8201 \
    > logs/producer_$(date +%Y%m%d).log 2>&1 &
PROD_PID=$!
echo "  ✅ P-producer PID: $PROD_PID  ·  tail -f logs/producer_$(date +%Y%m%d).log"

# ── [3/3] HMI (Vite :5173) ──────────────────────────────────────────────────
echo "🖥️  [3/3] ARIA HMI (Vite → /api·/ws 프록시 :8200) → :5173"
cd "$ROOT/frontend"
BACKEND_HOST=localhost BACKEND_PORT=8200 VITE_API_URL="" \
nohup $NPM run dev \
    > "$ROOT/logs/web_$(date +%Y%m%d).log" 2>&1 &
WEB_PID=$!
echo "  ✅ HMI PID: $WEB_PID  ·  tail -f $ROOT/logs/web_$(date +%Y%m%d).log"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🖥️  ARIA HMI        →  http://localhost:5173"
echo "  🔧 P-core API      →  http://localhost:8200/api/health"
echo "  🔬 P-producer헬스  →  http://localhost:8201/internal/health"
echo "  📡 WS              →  ws://localhost:8200/ws/chat"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "종료: pkill -f 'uvicorn server.app' && pkill -f 'inspection_node' && pkill -f vite"
echo ""
echo "kill 격리 테스트: kill $PROD_PID  # P-producer만 종료 → P-core 생존 확인"
echo "재기동:          cd $ROOT && ARIA_CORE_URL=http://localhost:8200 $PYTHON -m uvicorn aria.planes.inspection_node:app --port 8201"
