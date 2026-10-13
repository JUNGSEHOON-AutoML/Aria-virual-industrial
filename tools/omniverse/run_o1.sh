#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
capture_python="${CNOTTA_CAPTURE_PYTHON:-python}"
usd_python="$PWD/venv/omniverse/bin/python"
web_url="${CNOTTA_WEB_URL:-http://127.0.0.1:5278}"
if [[ ! -x "$usd_python" ]]; then
  echo 'Project venv/omniverse is missing. Follow tools/omniverse/README.md.' >&2
  exit 1
fi
# Only child processes inherit this; no experiment or existing service control.
export CUDA_VISIBLE_DEVICES=""
"$capture_python" -m tools.omniverse.capture_static --url "$web_url/usd-export.html"
"$capture_python" -m tools.omniverse.capture_static --dashboard --url "$web_url/cnotta.html" --output docs/autopilot/local/usd-dashboard.json
"$usd_python" -m tools.omniverse.export_usd
"$usd_python" -m unittest tools.gates.test_omniverse_preflight tools.gates.test_omniverse_usd
"$usd_python" -m tools.omniverse.validate_export
