#!/bin/bash
# ARIA 완전 정지 — 검사 정지(API) → 프로세스 종료 → GPU VRAM 해제 확인
#
# 왜 이 스크립트인가:
#   stop_lanes/stop 은 "검사(연산)"만 멈춘다 (GPU util → 0%).
#   그러나 서버 프로세스가 모델(DINO 백본·PatchCore 뱅크)과 CUDA 컨텍스트를
#   VRAM에 계속 들고 있으므로, gpustat의 메모리 점유는 프로세스를 죽여야 사라진다.
#   pkill -f 패턴 방식은 자기 자신(패턴을 포함한 셸)과 매치되는 함정이 있어
#   /proc/<pid>/exe 로 aria env 파이썬인지 확인 후 PID로 죽인다.
API=http://localhost:8200

echo "① 검사 정지 (API — 서버가 살아있을 때만 의미 있음)"
curl -s -m 3 -X POST $API/api/inspector/stop_lanes >/dev/null 2>&1 || true
curl -s -m 3 -X POST $API/api/inspector/stop       >/dev/null 2>&1 || true
sleep 1

kill_aria() {   # $1=시그널, $2=패턴
  local found=1
  for pid in $(pgrep -f "$2" 2>/dev/null); do
    exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null)
    case "$exe" in
      *envs/aria/bin/python*) kill "$1" "$pid" 2>/dev/null && { echo "  $1 → PID $pid ($2)"; found=0; } ;;
    esac
  done
  return $found
}

echo "② 서버/프로듀서 프로세스 종료"
kill_aria -TERM "uvicorn server.app"
kill_aria -TERM "uvicorn aria.planes.inspection_node"
sleep 3
kill_aria -KILL "uvicorn server.app" && echo "  (SIGTERM 무응답 → 강제 종료)"
kill_aria -KILL "uvicorn aria.planes.inspection_node"

# Vite dev 서버 (start_aria.sh 로 띄운 경우)
pkill -f "vite" 2>/dev/null && echo "  vite dev 종료"

sleep 1
echo "③ GPU 상태 (sehoon 프로세스의 VRAM이 사라져야 정상 — gdm 몇 MB는 시스템 데스크톱)"
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu --format=csv,noheader
echo
echo "재시작: PATH=/userHome/userhome4/sehoon/miniconda3/envs/aria/bin:\$PATH \\"
echo "        python -m uvicorn server.app:app --host 0.0.0.0 --port 8200"
