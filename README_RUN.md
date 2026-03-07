# README_RUN.md

## Install
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

## Configure
copy .env.example to .env
ADMIN_TOKEN=your_secret_token
TAKER_FEE_RATE=0.02
SLIPPAGE_RATE=0.0
DISPATCHER_TICK_SEC=2.0
DB_FLUSH_SEC=10.0
DEPRIORITIZE_MODE=ui
DEPRIORITIZE_MIN_WEIGHT=0.05

## Settings
Source of truth: `app/settings.py` (`Settings` = `RuntimeSettings`).
Key runtime settings to know: `DEPRIORITIZE_MODE`, `DB_FLUSH_SEC`, `DISPATCHER_TICK_SEC`, `TAKER_FEE_RATE`.
DEPRIORITIZE_MODE=ui
DEPRIORITIZE_MIN_WEIGHT=0.05

## Run Web UI
PS_DEV=1 python -m app.main   # DEV (authoritative dev flag)
python -m app.main            # default mode
./scripts/run_web.sh (mac/linux)
.\scripts\run_web.ps1 (windows)

## Run Modes
psrun-fast   — быстрый dev (ограничение ingest/book)
psrun-full   — полный dev без ограничений
psrun-prod   — поведение близкое к продакшену

## Fast dev run
Use one command with known-good fast dev settings:
`./scripts/run_dev_fast.sh`

Expected logs should include:
- `SNAPSHOTS_PLAN ... planned=60 limit=60`
- `BOOK_PLAN targets=20 ...`

## Run Pipeline / Loop
python -m app.main

## Smoke checks
python scripts/smoke_check.py
python -m compileall .
python -c "import app.main as m; print('ok')"

## Auto Paper Agent (paper-only)
curl -X POST http://127.0.0.1:8000/agent/start -H "Content-Type: application/json" -d "{\"cadence_sec\":10,\"size_preset\":1,\"max_positions\":1}"
curl http://127.0.0.1:8000/agent/state
curl http://127.0.0.1:8000/agent/events?limit=50
curl -X POST http://127.0.0.1:8000/agent/stop

## Dev: no-cache & static versioning
Start in dev mode (enables no-cache headers for HTML and /static):
`PS_DEV=1 python -u -m app.main`

Authoritative dev flag across entrypoints: `PS_DEV=1`.

Header checks (GET with headers; useful if HEAD returns 405 on HTML routes):
1. `curl -sS -D - -o /dev/null http://127.0.0.1:8000/cases | grep -i cache`
2. `curl -sS -D - -o /dev/null http://127.0.0.1:8000/static/ps_terminal.css | grep -i cache`
3. `curl -sS http://127.0.0.1:8000/cases | grep -Eo '/static/[^\"]+\\?v=[^\"]+' | head`

Quick full sanity:
`PS_DEV=1 ./scripts/dev_sanity.sh`
