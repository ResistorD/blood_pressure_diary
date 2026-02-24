# Action Plan - Приоритизированный план работ

## Статус проекта

**Текущее состояние:** Рабочий прототип с базовой функциональностью
**Целевое состояние:** Production-ready trading bot с полным функционалом

---

## Sprint 1: Стабилизация (Неделя 1) - КРИТИЧНО

### Day 1-2: Утилиты и конфигурация

**Задачи:**
- [ ] Создать `utils/time.py`, `utils/pricing.py`, `utils/validation.py`
- [ ] Создать `app/config.py` с полной валидацией
- [ ] Обновить все файлы для использования utils вместо дублированного кода
- [ ] Написать unit tests для utils

**Файлы для изменения:**
- agents/*.py (убрать дубликаты _now_utc, _get_mid)
- app/settings.py (мигрировать на config.py)
- dispatcher/loop.py (использовать utils)

**Приоритет:** 🔴 CRITICAL
**Оценка:** 8 часов

---

### Day 3-4: Error Handling

**Задачи:**
- [ ] Обернуть все agent.propose() в try-except с логированием
- [ ] Добавить retry логику в ingestor (3 попытки с экспоненциальным backoff)
- [ ] Добавить graceful degradation при сбоях БД
- [ ] Создать custom exceptions (ValidationError, DatabaseError, etc.)

**Файлы для изменения:**
- dispatcher/loop.py (_run_agents_for_market, _run_slow_agents, ingest)
- ingest/ingestor.py (добавить retry)
- agents/*.py (стандартизировать error handling)

**Приоритет:** 🔴 CRITICAL
**Оценка:** 6 часов

**Пример retry логики:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    reraise=True
)
def ingest():
    ...
```

---

### Day 5: Базовые тесты

**Задачи:**
- [ ] Настроить pytest с coverage
- [ ] Написать tests для utils (time, pricing, validation)
- [ ] Написать tests для config validation
- [ ] Написать tests для Repo (основные методы)

**Структура:**
```
tests/
├── conftest.py          # Фикстуры
├── unit/
│   ├── test_utils.py
│   ├── test_config.py
│   └── test_repo.py
└── integration/
    └── test_ingest.py
```

**Приоритет:** 🔴 CRITICAL
**Оценка:** 6 часов

**Целевой coverage:** >70%

---

## Sprint 2: Оптимизация (Неделя 2)

### Day 6-7: Database оптимизация

**Задачи:**
- [ ] Добавить индексы (композитные для hot queries)
- [ ] Создать view для latest_snapshots
- [ ] Реализовать connection pooling
- [ ] Добавить EXPLAIN QUERY PLAN логирование для медленных запросов

**SQL миграции:**
```sql
-- migration_001_indexes.sql
CREATE INDEX IF NOT EXISTS idx_snapshots_composite 
  ON snapshots(market_id, outcome, ts DESC);

CREATE INDEX IF NOT EXISTS idx_decisions_v0_composite 
  ON decisions_v0(market_id, ts DESC, status);

CREATE INDEX IF NOT EXISTS idx_signals_composite 
  ON signals(run_id, ts DESC, kind);

-- Materialized view for hot data
CREATE TABLE IF NOT EXISTS latest_snapshots AS
  SELECT DISTINCT ON (market_id, outcome) 
    market_id, outcome, bid, ask, mid, spread, liquidity, ts
  FROM snapshots 
  ORDER BY market_id, outcome, ts DESC;

CREATE UNIQUE INDEX idx_latest_snapshots_pk 
  ON latest_snapshots(market_id, outcome);
```

**Приоритет:** 🟡 HIGH
**Оценка:** 8 часов

---

### Day 8-9: Кэширование

**Задачи:**
- [ ] Создать `db/cache.py` с TTLCache
- [ ] Создать `db/optimized_repo.py` extends Repo
- [ ] Добавить кэширование для markets, snapshots
- [ ] Добавить cache metrics в UI

**Ожидаемый эффект:**
- Снижение DB load на 60-80%
- Ускорение agent processing в 3-5x

**Приоритет:** 🟡 HIGH
**Оценка:** 10 часов

---

### Day 10: Integration тесты

**Задачи:**
- [ ] Тесты для dispatcher loop
- [ ] Тесты для decision engine
- [ ] Тесты для paper execution
- [ ] End-to-end тест (ingest → agents → decisions → execution)

**Приоритет:** 🟡 HIGH
**Оценка:** 6 часов

---

## Sprint 3: Функциональность (Неделя 3-4)

### Week 3: Завершение агентов

**ScoutAgent (Day 11-12):**
- [ ] Добавить semantic similarity (sentence-transformers)
- [ ] Улучшить группировку рынков
- [ ] Добавить filters (closed markets, низкая активность)

**LogicAgent (Day 13-14):**
- [ ] Расширить constraint engine (implication, mutex)
- [ ] Добавить parity checks
- [ ] Интегрировать с TradePlan generation

**AuditorAgent (Day 15):**
- [ ] Anomaly detection (z-score, IQR)
- [ ] Data quality checks
- [ ] Стэйл data detection

**RiskAgent (Day 16):**
- [ ] Portfolio-level risk checks
- [ ] Correlation analysis
- [ ] Exposure limits

**Приоритет:** 🟢 MEDIUM
**Оценка:** 30 часов

---

### Week 4: Decision Engine v2

**Задачи:**
- [ ] Рефакторинг на strategy pattern
- [ ] Multi-strategy support (arb + pair trading + hedge)
- [ ] Risk-adjusted sizing (Kelly criterion)
- [ ] Position lifecycle management
- [ ] P&L tracking

**Приоритет:** 🟢 MEDIUM
**Оценка:** 20 часов

---

## Sprint 4: Production Ready (Неделя 5-6)

### Week 5: Monitoring & Observability

**Prometheus metrics:**
- [ ] signals_total (counter)
- [ ] decision_latency (histogram)
- [ ] agent_processing_time (histogram)
- [ ] position_pnl (gauge)
- [ ] errors_total (counter)

**Structured logging:**
- [ ] Мигрировать на structlog
- [ ] Добавить correlation IDs
- [ ] Log sampling для высоконагруженных мест

**Dashboard:**
- [ ] Grafana dashboard
- [ ] Real-time P&L chart
- [ ] Signal heatmap
- [ ] Error rate alerts

**Приоритет:** 🟢 MEDIUM
**Оценка:** 15 часов

---

### Week 6: Live Execution & Polish

**Live execution:**
- [ ] Реализовать LiveExecutor
- [ ] Order management system
- [ ] Fill reconciliation
- [ ] Position tracking

**Polish:**
- [ ] Улучшить UI (HTMX → Alpine.js компоненты)
- [ ] Документация (README, API docs, architecture)
- [ ] Security audit
- [ ] Load testing

**Приоритет:** 🟢 LOW
**Оценка:** 25 часов

---

## Метрики прогресса

### Sprint 1 (Стабилизация)
- ✅ Нет дублированного кода
- ✅ Все критические пути с error handling
- ✅ Test coverage > 70%
- ✅ Конфигурация централизована

### Sprint 2 (Оптимизация)
- ✅ DB queries < 10ms (p95)
- ✅ Cache hit rate > 80%
- ✅ Agent processing < 50ms per market
- ✅ Memory usage stable

### Sprint 3 (Функциональность)
- ✅ Все агенты complete & tested
- ✅ Decision engine supports multiple strategies
- ✅ Position lifecycle fully implemented
- ✅ P&L tracking working

### Sprint 4 (Production)
- ✅ Monitoring dashboard live
- ✅ Alerts configured
- ✅ Documentation complete
- ✅ Load tested (1000 markets, 100 decisions/min)

---

## Быстрые победы (Quick Wins)

Можно сделать сегодня за 2-3 часа:

### Quick Win #1: Централизация time utils
```bash
# 30 минут
touch utils/time.py
# Написать now_utc(), parse_iso(), to_iso()
# Заменить во всех файлах
grep -r "datetime.now(timezone.utc)" --include="*.py" | wc -l
# ~15 мест для замены
```

### Quick Win #2: Добавить базовые метрики
```bash
# 1 час
pip install prometheus-client
# Добавить в main.py:
from prometheus_client import Counter, Histogram, start_http_server
signals_total = Counter('signals_total', 'Total signals', ['agent_id'])
# Инструментировать agents
start_http_server(9090)
```

### Quick Win #3: Простой health check endpoint
```python
# api/routes/health.py - 30 минут
@router.get("/health")
def health():
    return {
        "status": "ok",
        "db": check_db(),
        "ingest": check_ingest(),
        "agents": [a.get_metrics() for a in agents]
    }
```

### Quick Win #4: Retry в ingestor
```python
# ingest/ingestor.py - 30 минут
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_markets(self):
    ...
```

---

## Риски и митигация

### Риск 1: DB блокировки при высокой нагрузке
**Вероятность:** HIGH
**Воздействие:** HIGH
**Митигация:**
- WAL mode (уже включен)
- Connection pooling
- Read replicas (будущее)
- Batch inserts вместо построчных

### Риск 2: Memory leaks в event bus
**Вероятность:** MEDIUM
**Воздействие:** HIGH
**Митигация:**
- Ограничить размер очереди
- Добавить monitoring memory usage
- Periodic cleanup старых events

### Риск 3: Race conditions в paper executor
**Вероятность:** MEDIUM
**Воздействие:** MEDIUM
**Митигация:**
- Добавить locks/transactions
- Idempotency keys
- Audit log всех изменений позиций

### Риск 4: API rate limits от Polymarket
**Вероятность:** HIGH
**Воздействие:** MEDIUM
**Митигация:**
- Exponential backoff
- Rate limiter (token bucket)
- Кэширование market data

---

## Рекомендуемый порядок работы

1. **Сначала стабильность** (Sprint 1)
   - Без надёжной основы оптимизация бессмысленна
   - Тесты дадут уверенность для рефакторинга

2. **Потом производительность** (Sprint 2)
   - Кэширование даст 3-5x ускорение
   - DB оптимизация critical для масштабирования

3. **Затем функциональность** (Sprint 3)
   - Агенты уже работают, нужно завершить
   - Decision engine основная ценность системы

4. **Наконец production готовность** (Sprint 4)
   - Monitoring необходим для операционной поддержки
   - Live execution последний шаг

---

## Следующие шаги

**Сегодня (2-3 часа):**
1. ✅ Создать `utils/time.py`
2. ✅ Заменить все `_now_utc()` на `from utils.time import now_utc`
3. ✅ Добавить retry в ingestor
4. ✅ Написать 5-10 базовых тестов

**На этой неделе:**
1. Завершить Sprint 1 (стабилизация)
2. Начать Sprint 2 (DB оптимизация)

**Нужна помощь?**
Скажите, с чего хотите начать, и я помогу с конкретной реализацией!
