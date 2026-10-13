#!/usr/bin/env bash
# Replay starts read-only. Explicit Live controls start a separate CPU-only DES.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
PYTHON_BIN=${CNOTTA_PYTHON:-python}
NODE_BIN=${CNOTTA_NODE:-node}
export CNOTTA_API_PORT=${CNOTTA_API_PORT:-5277} CNOTTA_WEB_PORT=${CNOTTA_WEB_PORT:-5278}
export CNOTTA_PILOT=${CNOTTA_PILOT:-$ROOT/docs/validation/aria_dt_20261013_03/des_pilot30}
export CNOTTA_P1=${CNOTTA_P1:-$ROOT/docs/validation/aria_dt_20261012_02/p1_verified}
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export CUDA_VISIBLE_DEVICES=''
LOG_DIR=${CNOTTA_LOG_DIR:-$ROOT/docs/autopilot/local/demo}
mkdir -p "$LOG_DIR"
[[ -d "$CNOTTA_PILOT/runs" && -d "$CNOTTA_P1" ]] || { echo 'CNOTTA_PILOT/CNOTTA_P1에 검증된 데이터 경로가 필요합니다.' >&2; exit 2; }
[[ -f frontend/node_modules/vite/bin/vite.js ]] || { echo 'frontend 로컬 의존성이 필요합니다. README를 확인하세요.' >&2; exit 2; }
"$PYTHON_BIN" -c 'import fastapi,uvicorn'
"$NODE_BIN" -e 'if(Number(process.versions.node.split(".")[0])<20)process.exit(2)'
"$PYTHON_BIN" - <<'PY'
import os,socket
for name in ('CNOTTA_API_PORT','CNOTTA_WEB_PORT'):
 with socket.socket() as s:
  s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',int(os.environ[name])))
PY
api_pid='';web_pid=''
cleanup(){ for pid in "$web_pid" "$api_pid"; do if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi; done; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$PYTHON_BIN" -m uvicorn aria.dashboard.server:app --host 127.0.0.1 --port "$CNOTTA_API_PORT" >"$LOG_DIR/api.log" 2>&1 & api_pid=$!
(cd frontend && exec "$NODE_BIN" node_modules/vite/bin/vite.js --config vite.cnotta.config.js) >"$LOG_DIR/web.log" 2>&1 & web_pid=$!
"$PYTHON_BIN" - <<'PY'
import json,os,time,urllib.request
for suffix,port in [('/api/dt/runs',os.environ['CNOTTA_API_PORT']),('/cnotta.html',os.environ['CNOTTA_WEB_PORT'])]:
 for attempt in range(100):
  try:
   with urllib.request.urlopen('http://127.0.0.1:'+port+suffix,timeout=2) as r:data=r.read()
   if suffix.endswith('runs'):assert len(json.loads(data))>=1
   else:assert b'cnotta' in data
   break
  except Exception:
   if attempt==99:raise
   time.sleep(.2)
with urllib.request.urlopen('http://127.0.0.1:'+os.environ['CNOTTA_API_PORT']+'/api/dt/runs') as response:runs=json.load(response)
run=next((r for r in runs if r['cell']=='robot'),runs[0])
for endpoint in ('timeline','kpi?t=1800'):
 with urllib.request.urlopen('http://127.0.0.1:'+os.environ['CNOTTA_API_PORT']+'/api/dt/runs/'+run['run_id']+'/'+endpoint,timeout=120) as response:assert json.load(response)
print('Ready: http://127.0.0.1:' +os.environ['CNOTTA_WEB_PORT']+'/cnotta.html')
PY
if [[ ${1:-} == '--check' ]]; then exit 0; fi
wait -n "$api_pid" "$web_pid"
