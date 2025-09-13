#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

source "$PROJECT_ROOT/.venv/bin/activate"
cd "$PROJECT_ROOT"
PYTHONPATH="$PROJECT_ROOT" exec uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload

