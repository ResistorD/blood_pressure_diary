# SANITY_REPORT.md (Phase 0)

Дата: 2026-02-20

## Точки входа (кандидаты на канон)
- `app/main.py`: Канон. Запускает dispatcher loop (`dispatcher.loop`) + FastAPI через `api/http.create_app`. Стартует `uvicorn`.
- `api/http.py`: Фабрика FastAPI, используется `app/main.py`.
- `app/main_v2.py`: Deprecated thin-wrapper → вызывает `app.main.main()`.
- `app/main_final.py`: Deprecated thin-wrapper → вызывает `app.main.main()`.
- `app/demo.py`: Демо-обертка, выставляет env и вызывает `app.main_v2.main()`.

## Дубли / Пересечения и использование
- `dispatcher/loop.py` + `decision/engine.py` (DecisionEngineV0):
  - Используется в `app/main.py` (прямой импорт `dispatcher.loop`).
- `dispatcher/optimized_loop.py` + `decision/engine_v2.py` (DecisionEngine v2):
  - Ранее использовался в `app/main_v2.py`/`app/main_final.py`, теперь они тонкие алиасы.
  - Импортируется в тестах (`tests/unit/test_tradeability_v2.py`).
- `app/main_v2.py` vs `app/main_final.py` vs `app/main.py`:
  - Все три — запускаемые entrypoint’ы и все стартуют uvicorn.
  - README и completion-docs местами ссылаются на `app/main_v2.py`/`app/main_final.py`.
- `app/demo.py` — тонкая обертка над `app.main_v2`.

## Решение по дефолтной петле
- Дефолт: V0 loop — `dispatcher/loop.py` + `DecisionEngineV0` через канонический `app/main.py`.

## Canonical Execution Reality
Loop: `dispatcher/loop.py` (V0)
Engine: `decision/engine.py` (DecisionEngineV0)
Status: DEFAULT
Note: `app/main.py` imports only `dispatcher.loop` (no v2/optimized imports).

## Рискованные/хрупкие точки
- `agents/logic.py` содержит `IndentationError` (compileall падает). Опциональный импорт в `dispatcher/loop.py` обернут try/except, но `python -m compileall .` будет падать, пока не исправлено.
- Несколько entrypoint’ов каждый стартует uvicorn — риск дрейфа поведения веб-старта.
- Две «реальности» dispatcher (V0 vs V2) сосуществуют; дефолтный путь зависит от entrypoint.

## Dead Code & Stubs Audit
- `_find_threshold_pairs` → returns []
- No unused imports in canonical runtime
- Experimental modules isolated

## Perf-2 (Write-Behind Buffer)
- `DB_FLUSH_SEC` controls batched commits for `events_log` + `pnl_snapshots`
- trades/positions are not buffered

## Статус compile/smoke
- `python -m compileall .`: FAILED из-за `agents/logic.py` IndentationError (line 462).
- Импорты:
  - `python -c "import app.main as m; print('ok')"`: OK
  - `python -c "import app.main_v2 as m; print('ok')"`: OK
  - `python -c "import app.main_final as m; print('ok')"`: OK
