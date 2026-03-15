# Stage-0 Live Launch Checklist (Polymarket)

Цель Stage-0: первый реальный запуск с минимальным риском (1 рынок, микросайз, ручной контроль).

## 1) Preconditions перед первым live-действием
- `python -m pytest -q` зелёный.
- `ADMIN_TOKEN` задан и проверен (`/control/state` отвечает, mutating endpoints защищены).
- В `/health/state`:
  - `execution_mode=live_stage0`
  - `freshness.state.overall=OK`
  - `paper_pipeline.decision_mode=FULL`
  - `paused=false`
- На dashboard-v2 в System status:
  - `Freshness=FRESHNESS_OK`
  - `Decision mode=FULL`
  - `Reconcile=ALLOWED`
  - `Execution mode=live_stage0`
- Kill switch доступен оператору и проверен (pause/resume path рабочий).

## 2) Безопасные лимиты для Stage-0
- Один рынок на сессию.
- Один ордер на сессию (или очень малый `live_max_orders_per_day`, например `1`).
- Очень малый `live_max_notional` (микро-уровень).
- Ограничить одновременные позиции до минимума (через текущие risk limits).
- Сессию завершать сразу после подтверждённого пост-трейд аудита.

## 3) Процедура первого трейда
1. Выбрать один рынок с нормальной ликвидностью и свежим orderbook.
2. Проверить dashboard/health условия из раздела Preconditions.
3. Убедиться, что kill/resume путь доступен до отправки действия.
4. Выполнить одно контролируемое live-действие.
5. Сразу зафиксировать время, market_id, expected side/qty/price.

## 4) Post-trade audit
- Проверить telemetry/logs:
  - `PIPELINE_OBS`
  - `CASE_LIFECYCLE_SUMMARY` / `CASE_LIFECYCLE_SKIP_SUMMARY`
  - `DECISION_QUALITY_SUMMARY`
- Проверить `/health/state` и `/health/exec`.
- Сверить локальное состояние (позиция/статус в системе) с фактом на бирже.
- Убедиться, что нет неожиданных `kill_kind`, freshness-блокировок, dedup-аномалий.

## 5) Abort процедура
1. Немедленно включить kill/pause.
2. Остановить новые действия (никаких новых opens).
3. При необходимости выполнить controlled unwind/close.
4. Проверить, что reconcile больше не открывает новые позиции.
5. Зафиксировать инцидент и сохранить ключевые логи/health snapshot.
