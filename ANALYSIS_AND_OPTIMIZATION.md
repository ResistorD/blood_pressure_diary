# Анализ и план оптимизации приложения PolySyndicate

## Обзор системы

Это торговый бот для рынков предсказаний (Polymarket), построенный на архитектуре агентов с принятием решений и исполнением.

### Архитектура

```
┌─────────────┐
│   main.py   │ ─── Запускает FastAPI + Dispatcher в потоке
└─────────────┘
       │
       ├── HTTP API (FastAPI + HTMX UI)
       │   └── Routes: cases, markets, positions, logs, control
       │
       └── Dispatcher Loop
           ├── Ingestor (PolymarketClient) → Markets + Snapshots
           ├── Agents (Fast + Slow) → Signals
           ├── DecisionEngine → Decisions
           └── Execution (Paper/Live) → Orders + Fills
```

### Компоненты

1. **Agents** (6 агентов):
   - `QuantAgent` - быстрый, риск-ограничения по ликвидности/спреду
   - `ScoutAgent` - медленный, ищет похожие рынки
   - `LogicAgent` - медленный, логические противоречия
   - `RiskAgent` - медленный, глобальные риск-проверки
   - `AuditorAgent` - медленный, аудит качества данных
   
2. **Decision Engine** - простой арбитражный движок (YES+NO sum)

3. **Execution** - paper trading симулятор

4. **Database** - SQLite с WAL mode

## Найденные проблемы

### 🔴 Критические

1. **Неполная реализация агентов** - многие файлы содержат только заглушки или частичную логику
2. **Отсутствие обработки ошибок** в критических местах (ingest, agents)
3. **DB schema не синхронизирована** - есть `decisions_v0`, `paper_queue`, но они не везде используются
4. **Нет тестов** - только заглушки в `tests/`
5. **Hardcoded пути** - `polysyndicate.db` прописан в коде

### 🟡 Средние

1. **Дублирование кода**:
   - `_now_utc()` дублируется в нескольких агентах
   - Логика получения mid price повторяется
   - Парсинг settings дублируется

2. **Неэффективные запросы**:
   - `list_markets(limit=500)` вызывается часто
   - Нет кэширования snapshot данных
   - `_latest_snapshots_by_outcome` делает `LIMIT 50` каждый раз

3. **Слабая типизация**:
   - Много `Any`, `Optional[str]`
   - Нет валидации JSON полей
   - Inconsistent typing между модулями

4. **Плохая структура конфигурации**:
   - Settings разбросаны по коду
   - Magic numbers (0.99, 1.00, 0.04)
   - Нет validation

### 🟢 Незначительные

1. **Naming inconsistency**: `run_id` vs `runId`, `market_id` vs `marketId`
2. **Logging не структурирован** - простой `log.info()` без контекста
3. **UI templates используют устаревший подход** - нет компонентов
4. **Нет metrics/monitoring**

## План оптимизации

### Фаза 1: Стабилизация (Priority 1)

#### 1.1 Унификация утилит
```python
# utils/time.py
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

# utils/pricing.py
def get_mid(ctx: AgentContext, market_id: str, outcome: str) -> Optional[float]:
    ...

# utils/validation.py
def validate_market_data(data: dict) -> bool:
    ...
```

#### 1.2 Централизация конфигурации
```python
# app/config.py
class AgentConfig(BaseModel):
    min_edge: float = Field(0.03, ge=0, le=1)
    min_liquidity: float = Field(50.0, ge=0)
    max_spread: float = Field(0.10, ge=0, le=1)

class DecisionConfig(BaseModel):
    arb_buy_threshold: float = Field(0.99, ge=0, le=1)
    arb_close_threshold: float = Field(1.00, ge=0, le=2)
    min_emit_interval_sec: int = Field(120, ge=0)
```

#### 1.3 Добавить обработку ошибок
- Wrap все agent.propose() в try-except
- Retry логика для ingest
- Graceful degradation при сбоях БД

#### 1.4 Базовые тесты
```python
tests/
├── unit/
│   ├── test_agents.py
│   ├── test_decision_engine.py
│   └── test_repo.py
└── integration/
    ├── test_dispatcher.py
    └── test_api.py
```

### Фаза 2: Оптимизация производительности (Priority 2)

#### 2.1 Database оптимизация
```sql
-- Добавить индексы
CREATE INDEX idx_snapshots_composite ON snapshots(market_id, outcome, ts DESC);
CREATE INDEX idx_decisions_v0_composite ON decisions_v0(market_id, ts DESC);

-- Материализованное представление для hot data
CREATE TABLE latest_snapshots AS
  SELECT DISTINCT ON (market_id, outcome) 
    market_id, outcome, bid, ask, mid, spread, liquidity
  FROM snapshots 
  ORDER BY market_id, outcome, ts DESC;
```

#### 2.2 Кэширование
```python
from functools import lru_cache
from cachetools import TTLCache

class CachedRepo:
    def __init__(self, repo: Repo):
        self._repo = repo
        self._market_cache = TTLCache(maxsize=1000, ttl=60)
        self._snapshot_cache = TTLCache(maxsize=5000, ttl=10)
    
    @lru_cache(maxsize=100)
    def get_market(self, market_id: str) -> Market:
        ...
```

#### 2.3 Batch processing
```python
# Вместо:
for market in markets:
    agent.propose(ctx, market_id=market.market_id)

# Делать:
agent.propose_batch(ctx, market_ids=[m.market_id for m in markets])
```

### Фаза 3: Улучшение архитектуры (Priority 3)

#### 3.1 Dependency Injection
```python
from dataclasses import dataclass

@dataclass
class Dependencies:
    repo: Repo
    bus: EventBus
    config: AppSettings
    cache: Cache

class Agent(ABC):
    def __init__(self, deps: Dependencies):
        self.deps = deps
```

#### 3.2 Event-driven architecture
```python
# domain/events.py
class MarketUpdated(Event):
    market_id: str
    timestamp: datetime

class SignalGenerated(Event):
    signal: Signal

class DecisionMade(Event):
    decision: Decision

# dispatcher/handlers.py
@bus.subscribe(MarketUpdated)
def on_market_updated(event: MarketUpdated):
    ...
```

#### 3.3 Модульность агентов
```python
# agents/base.py
class Agent(ABC):
    @abstractmethod
    def setup(self, ctx: AgentContext) -> None:
        """Called once at startup"""
        
    @abstractmethod
    def process(self, ctx: AgentContext, data: Any) -> List[Signal]:
        """Called on each tick"""
        
    def teardown(self) -> None:
        """Called on shutdown"""
```

### Фаза 4: Функциональность (Priority 4)

#### 4.1 Завершить агентов
- ScoutAgent: добавить semantic similarity (embeddings?)
- LogicAgent: расширить constraint engine
- AuditorAgent: добавить anomaly detection
- RiskAgent: portfolio-level checks

#### 4.2 Расширить Decision Engine
```python
class DecisionEngineV1:
    """
    Features:
    - Multi-strategy support
    - Risk-adjusted sizing
    - Position lifecycle management
    - P&L tracking
    """
    
    def evaluate(self, signals: List[Signal]) -> List[Decision]:
        # 1. Filter by quality
        # 2. Rank by edge
        # 3. Check risk limits
        # 4. Optimize allocation
        # 5. Generate decisions
```

#### 4.3 Live execution
```python
# execution/live_executor.py
class LiveExecutor:
    def __init__(self, api_client: PolymarketAPI):
        self.client = api_client
        
    async def execute_order(self, order: Order) -> Fill:
        # Real API calls
```

### Фаза 5: Monitoring & Observability (Priority 5)

#### 5.1 Metrics
```python
from prometheus_client import Counter, Histogram, Gauge

signals_generated = Counter('signals_total', 'Total signals', ['agent_id', 'kind'])
decision_latency = Histogram('decision_latency_seconds', 'Decision latency')
position_pnl = Gauge('position_pnl', 'Position P&L', ['market_id'])
```

#### 5.2 Structured logging
```python
import structlog

logger = structlog.get_logger()
logger.info("signal_generated", 
    signal_id=signal.signal_id,
    agent_id=signal.agent_id,
    market_id=signal.scope_market_id,
    kind=signal.kind.value
)
```

#### 5.3 Dashboard
- Real-time P&L
- Signal heatmap
- Decision timeline
- Error rates
- System health

## Приоритизация задач

### Week 1: Foundation
- [ ] Унифицировать утилиты (utils/)
- [ ] Централизовать конфигурацию
- [ ] Добавить error handling везде
- [ ] Написать unit tests для Repo

### Week 2: Stability
- [ ] Оптимизировать DB запросы
- [ ] Добавить кэширование
- [ ] Написать integration tests
- [ ] Fix incomplete agents

### Week 3: Performance
- [ ] Batch processing
- [ ] DB indexes
- [ ] Profiling & optimization
- [ ] Load testing

### Week 4: Features
- [ ] Complete decision engine v1
- [ ] Add monitoring
- [ ] Improve UI
- [ ] Documentation

## Метрики успеха

1. **Производительность**:
   - Decision latency < 100ms
   - Ingest throughput > 100 markets/sec
   - Agent processing < 50ms per market

2. **Надёжность**:
   - Uptime > 99.5%
   - Error rate < 0.1%
   - Test coverage > 80%

3. **Качество**:
   - Type coverage > 90%
   - No hardcoded values
   - All TODOs resolved

## Рекомендуемые библиотеки

- **Performance**: `orjson`, `msgpack`, `uvloop`
- **Caching**: `cachetools`, `redis-py`
- **Testing**: `pytest`, `pytest-asyncio`, `hypothesis`
- **Monitoring**: `prometheus-client`, `sentry-sdk`
- **Typing**: `pydantic v2`, `mypy`
- **Async**: `asyncio`, `aiohttp`

## Технический долг

### High Priority
1. ❌ Нет транзакций в критических местах
2. ❌ Race conditions в paper executor
3. ❌ Memory leaks в event bus (unbounded queue?)
4. ❌ No connection pooling

### Medium Priority
1. ⚠️ Inconsistent datetime handling (ISO vs UTC)
2. ⚠️ No data validation on API boundaries
3. ⚠️ Magic strings вместо enums
4. ⚠️ No rate limiting on ingest

### Low Priority
1. ℹ️ Code duplication
2. ℹ️ Missing docstrings
3. ℹ️ Inconsistent naming
4. ℹ️ No type stubs for external libs

## Заключение

Приложение имеет **хорошую архитектурную основу**, но нуждается в:
1. **Стабилизации** - error handling, tests, validation
2. **Оптимизации** - caching, batching, indexes
3. **Завершении** - incomplete features, missing logic
4. **Observability** - monitoring, logging, metrics

Рекомендуется начать с **Фазы 1 (Стабилизация)**, т.к. без надёжной основы дальнейшая оптимизация будет непродуктивной.

Estimated effort: **4-6 weeks** для полной реализации всех фаз.
