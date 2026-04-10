#!/usr/bin/env bash
set -euo pipefail

CODE_DIR="${CODE_DIR:-/workspace/fire_satellite}"
APP_MODULE="${APP_MODULE:-app.main:app}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

if [[ ! -f "${CODE_DIR}/app/main.py" ]]; then
    echo "ERROR: project code not found at ${CODE_DIR}."
    echo "Mount fire_satellite project directory to ${CODE_DIR}."
    exit 1
fi

if [[ ! -d "${CODE_DIR}/data/worldcover" ]]; then
    echo "WARNING: ${CODE_DIR}/data/worldcover not found."
    echo "Set SAT_WORLDCOVER_DIR to an external mount path if needed."
fi

cd "${CODE_DIR}"
exec uvicorn "${APP_MODULE}" --host "${HOST}" --port "${PORT}"