#!/usr/bin/env bash
# Start the web UI from a checkout. Extra args go to the server (e.g. --host 0.0.0.0).
# Keys/tokens are read from the environment only: NVIDIA_API_KEY, SLG_QWEN_URL, SLG_ACCESS_TOKEN, ...
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
exec env PYTHONPATH=src "$PY" -m slg.web.server "$@"
