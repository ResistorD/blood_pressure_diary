# PolySyndicate v1 — Release Note

## Статус релиза
- Вердикт: `READY_FOR_V1`.
- Финальный blocker закрыт: mutating operator endpoints защищены `ADMIN_TOKEN`.

## Что поддерживает v1
- Decision/risk pipeline с freshness-режимами:
  - `FULL` (`FRESHNESS_OK`)
  - `SAFE` (`FRESHNESS_WARN`, `OPEN` блокируется)
  - `HALTED` (`FRESHNESS_STOP`, decision execution пропускается)
- Risk gating и приоритизация с явной атрибуцией причин.
- Paper operator actions и batch/unwind сценарии через защищённые mutating endpoint’ы.

## Операторские возможности
- Главная операторская страница: `/dashboard-v2`.
- Компактный `System status` блок:
  - freshness
  - decision mode
  - reconcile state/skip reason
  - open_blocked_by_freshness
  - paper last/candidate/decision
- Просмотр кейсов: `/cases` с reason badges (`KILL`, `RISK`, `FRESHNESS`, `BLOCKED`, `NORMAL`).
- Детали кейса: `/cases/{market_id}` с блоком «Почему это решение».

## Explainability/observability
- Логи и телеметрия:
  - `PIPELINE_OBS`
  - `CASE_LIFECYCLE_SUMMARY`
  - `CASE_LIFECYCLE_SKIP_SUMMARY`
  - `CASE_OBS_SUMMARY`
  - `DECISION_QUALITY_SUMMARY`
- Ключевые поля:
  - `risk_kind`, `kill_kind`
  - `freshness_gate`, `freshness_reason`
  - `decision_mode`, `open_blocked_by_freshness`

## Подтверждённые risk coverage families
- `RISK_CONSTRAINT_SIGNAL`
- `QUALITY_ALERT_SIGNAL`
- `AUTO_LIMIT_MARKET_ALREADY_OPEN`
- `AUTO_LIMIT_MAX_NOTIONAL_PER_GROUP`
- `AUTO_LIMIT_MAX_OPEN_POSITIONS`
- `AUTO_LIMIT_MAX_NOTIONAL_TOTAL`
- Recovery-paths наблюдались в focused run’ах.

## Security note
- Все mutating operator endpoint’ы (категории `cases/*/paper/*`, `paper/*`, `agent/*`, `control/*`) требуют admin-token guard.
- Read-only endpoint’ы оставлены без лишней защиты.

## Неблокирующие ограничения (v1)
- Runtime telemetry часть полей хранится в памяти процесса (после рестарта сбрасывается).
- Для v1 это допустимо; историчность runtime-диагностики можно расширить позже.
