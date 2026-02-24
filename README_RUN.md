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
python -m app.main
./scripts/run_web.sh (mac/linux)
.\scripts\run_web.ps1 (windows)

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
