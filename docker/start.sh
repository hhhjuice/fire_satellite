#!/usr/bin/env bash
set -euo pipefail

CODE_DIR="${CODE_DIR:-/app}"
APP_MODULE="${APP_MODULE:-app.main:app}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORLDCOVER_DIR="${SAT_WORLDCOVER_DIR:-/data/worldcover}"

if [[ ! -f "${CODE_DIR}/app/main.py" ]]; then
    echo "ERROR: project code not found at ${CODE_DIR}."
    exit 1
fi

if [[ ! -d "${WORLDCOVER_DIR}" ]]; then
    if [[ "${SAT_REQUIRE_WORLDCOVER:-false}" == "true" ]]; then
        echo "ERROR: WorldCover data directory not found at ${WORLDCOVER_DIR}."
        exit 1
    fi
    echo "WARNING: WorldCover data directory not found at ${WORLDCOVER_DIR}."
fi

cd "${CODE_DIR}"
exec python3 -m uvicorn "${APP_MODULE}" --host "${HOST}" --port "${PORT}"
