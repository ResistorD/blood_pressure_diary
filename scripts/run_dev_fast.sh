#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

export PS_DEV=1
export PS_API_HOST=127.0.0.1
export PS_API_PORT=8000
export PS_INGEST_SNAPSHOTS_LIMIT=60
export PS_BOOK_TARGET_LIMIT=20

exec python -u -m app.main
