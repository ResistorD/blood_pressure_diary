# PolySyndicate v1 — Operator Runbook

## 1) Запуск
```bash
# Рекомендуемый быстрый dev-профиль
./scripts/run_modes/psrun-fast
```

Альтернатива:
```bash
PS_DEV=1 python -u -m app.main
```

## 2) Главная операторская страница
- Открыть: `http://127.0.0.1:8000/dashboard-v2`
- Это основной вход для live-оператора.

## 3) Где смотреть состояние
- System status (на `/dashboard-v2`):
  - `Freshness`
  - `Decision mode`
  - `Reconcile` + reason
  - `Opens` (blocked/alowed by freshness)
  - `Paper` (last/candidate/decision)
- Health API:
  - `GET /health/state`
  - ключевые поля: `freshness.state`, `paper_pipeline.*`, `paused`

## 4) Где смотреть причины решений
- Список кейсов: `/cases`
  - reason badges (`KILL`, `RISK`, `FRESHNESS`, ...)
- Детали кейса: `/cases/{market_id}`
  - блок «Почему это решение»
  - поля: status/reason/risk/kill/freshness/decision mode

## 5) Focused scenario validation (короткая проверка)
В отдельном терминале при запущенном loop:
```bash
python scripts/diagnostics/decision_quality_scenario_runner.py \
  --db-path polysyndicate.db \
  --markets 3 \
  --phase-seconds 45 \
  --tick-seconds 1.0 \
  --focus-max-notional-total
```

Ожидаемые маркеры:
- `SCENARIO_PHASE`
- `SCENARIO_NOTIONAL_TOTAL_INJECT`
- `SCENARIO_NOTIONAL_TOTAL_CLEAR`

Смотреть в логах:
- `PIPELINE_OBS`
- `CASE_LIFECYCLE_SUMMARY`

## 6) Быстрая проверка здоровья
- `GET /health/ping` должен вернуть `{"status":"ok"}`
- `GET /health/state`:
  - `freshness.state.overall` не должен стабильно быть `STOP`
  - `paper_pipeline.decision_mode` ожидается `FULL` или `SAFE` в рабочем режиме

## 7) Безопасная остановка
- Остановить процесс `app.main` (Ctrl+C в терминале запуска).
- Перед остановкой при необходимости:
  - включить pause/kill через control endpoint’ы (с admin token),
  - убедиться, что нет нежелательных открытых paper-позиций (`/positions`).
