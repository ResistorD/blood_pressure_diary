#!/usr/bin/env sh
set -eu

export PS_API_HOST="${PS_API_HOST:-127.0.0.1}"
export PS_API_PORT="${PS_API_PORT:-8000}"

python -u -m app.main
