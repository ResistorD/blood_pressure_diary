# Детальный план рефакторинга PolySyndicate

## 1. Утилиты (utils/)

### utils/time.py
```python
"""Time utilities for consistent datetime handling."""
from datetime import datetime, timezone
from typing import Union


def now_utc() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)


def parse_iso(ts: Union[str, datetime]) -> datetime:
    """Parse ISO timestamp, handling various formats."""
    if isinstance(ts, datetime):
        return ts
    # Handle both 'Z' and '+00:00' suffixes
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def to_iso(dt: datetime) -> str:
    """Convert datetime to ISO string with seconds precision."""
    return dt.isoformat(timespec="seconds")
```

### utils/pricing.py
```python
"""Pricing utilities for market data."""
from typing import Optional, Dict, Tuple
from domain.models import Snapshot


def get_mid(snapshots: Dict[str, Dict], outcome: str) -> Optional[float]:
    """Extract mid price for outcome from snapshot dict."""
    snap = snapshots.get(outcome)
    if not snap:
        return None
    mid = snap.get("mid")
    return float(mid) if mid is not None else None


def calculate_spread(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """Calculate bid-ask spread."""
    if bid is None or ask is None:
        return None
    return abs(ask - bid)


def calculate_sum_mid(snapshots: Dict[str, Dict]) -> Optional[float]:
    """Calculate YES + NO mid price sum."""
    yes_mid = get_mid(snapshots, "YES")
    no_mid = get_mid(snapshots, "NO")
    if yes_mid is None or no_mid is None:
        return None
    return yes_mid + no_mid


def is_tradeable(
    spread: Optional[float],
    liquidity: Optional[float],
    max_spread: float,
    min_liquidity: float
) -> bool:
    """Check if market is tradeable based on spread and liquidity."""
    if spread is None or liquidity is None:
        return False
    return spread <= max_spread and liquidity >= min_liquidity
```

### utils/validation.py
```python
"""Validation utilities."""
from typing import Any, Dict


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


def validate_market_id(market_id: str) -> None:
    """Validate market ID format."""
    if not market_id or not isinstance(market_id, str):
        raise ValidationError(f"Invalid market_id: {market_id}")


def validate_snapshot(snap: Dict[str, Any]) -> None:
    """Validate snapshot data."""
    required = ["market_id", "outcome", "ts"]
    for field in required:
        if field not in snap:
            raise ValidationError(f"Missing required field: {field}")
    
    # Validate numeric fields
    for field in ["bid", "ask", "mid", "spread", "liquidity"]:
        val = snap.get(field)
        if val is not None:
            try:
                float(val)
            except (TypeError, ValueError):
                raise ValidationError(f"Invalid {field}: {val}")


def validate_signal_features(features: Dict[str, float]) -> None:
    """Validate signal features are numeric."""
    for k, v in features.items():
        if not isinstance(v, (int, float)):
            raise ValidationError(f"Feature {k} must be numeric, got {type(v)}")
```

## 2. Централизованная конфигурация

### app/config.py
```python
"""Centralized configuration with validation."""
from typing import Optional
from pydantic import BaseModel, Field, validator
from domain.enums import Mode


class AgentConfig(BaseModel):
    """Configuration for agents."""
    
    # QuantAgent
    min_liquidity: float = Field(50.0, ge=0, description="Minimum liquidity threshold")
    max_spread: float = Field(0.10, ge=0, le=1, description="Maximum spread threshold")
    
    # LogicAgent
    logic_min_delta: float = Field(0.08, ge=0, le=1, description="Minimum delta for pair arb")
    logic_max_spread: float = Field(0.06, ge=0, le=1, description="Max spread for logic trades")
    
    # ScoutAgent
    scout_min_similarity: float = Field(0.22, ge=0, le=1, description="Min title similarity")
    scout_max_group_size: int = Field(50, ge=2, description="Max markets per group")
    
    @validator("max_spread", "logic_max_spread")
    def validate_spread(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Spread must be between 0 and 1")
        return v


class DecisionConfig(BaseModel):
    """Configuration for decision engine."""
    
    arb_buy_threshold: float = Field(
        0.99, ge=0, le=1,
        description="Buy threshold for YES+NO sum (< threshold = buy signal)"
    )
    arb_close_threshold: float = Field(
        1.00, ge=0, le=2,
        description="Close threshold for YES+NO sum (>= threshold = close signal)"
    )
    min_emit_interval_sec: int = Field(
        120, ge=0,
        description="Minimum seconds between duplicate decisions"
    )
    max_spread: float = Field(0.04, ge=0, le=1)
    min_liquidity: float = Field(50.0, ge=0)
    
    @validator("arb_close_threshold")
    def validate_close_threshold(cls, v, values):
        buy = values.get("arb_buy_threshold", 0.99)
        if v <= buy:
            raise ValueError("Close threshold must be > buy threshold")
        return v


class RiskConfig(BaseModel):
    """Risk management configuration."""
    
    max_notional_total: float = Field(500.0, ge=0)
    max_notional_per_group: float = Field(250.0, ge=0)
    max_notional_per_market: float = Field(150.0, ge=0)
    min_liquidity: float = Field(50.0, ge=0)
    max_spread: float = Field(0.10, ge=0, le=1)
    max_impact_pct: float = Field(0.15, ge=0, le=1)
    
    @validator("max_notional_per_group")
    def validate_group_limit(cls, v, values):
        total = values.get("max_notional_total")
        if total and v > total:
            raise ValueError("Per-group limit cannot exceed total limit")
        return v


class DispatcherConfig(BaseModel):
    """Dispatcher loop configuration."""
    
    poll_interval_sec: int = Field(20, ge=1, description="Market data poll interval")
    reconcile_interval_sec: int = Field(60, ge=1, description="Decision reconciliation interval")
    event_batch_size: int = Field(500, ge=1, description="Max events per iteration")
    sleep_sec: float = Field(0.2, ge=0.01, description="Sleep between iterations")


class DatabaseConfig(BaseModel):
    """Database configuration."""
    
    path: str = Field("polysyndicate.db", description="SQLite database path")
    wal_mode: bool = Field(True, description="Enable WAL mode")
    timeout_sec: int = Field(30, ge=1, description="Connection timeout")
    pool_size: int = Field(5, ge=1, le=20, description="Connection pool size")


class AppConfig(BaseModel):
    """Main application configuration."""
    
    mode: Mode = Mode.DRY_RUN
    
    # API
    api_host: str = "127.0.0.1"
    api_port: int = Field(8000, ge=1024, le=65535)
    
    # Feature flags
    enable_ingest: bool = True
    enable_agents: bool = True
    enable_decision: bool = True
    enable_execution: bool = False
    
    # Sub-configs
    agent: AgentConfig = Field(default_factory=AgentConfig)
    decision: DecisionConfig = Field(default_factory=DecisionConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    dispatcher: DispatcherConfig = Field(default_factory=DispatcherConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load from environment variables with PS_ prefix."""
        from pydantic_settings import BaseSettings, SettingsConfigDict
        
        class _Settings(BaseSettings):
            model_config = SettingsConfigDict(env_prefix="PS_", env_file=".env", extra="ignore")
            
            # Flatten all fields here
            mode: Mode = Mode.DRY_RUN
            api_host: str = "127.0.0.1"
            api_port: int = 8000
            # ... etc
        
        settings = _Settings()
        return cls(**settings.model_dump())
    
    def to_dict(self) -> dict:
        """Export to dict for hashing."""
        return self.model_dump()
```

## 3. Улучшенный Repo с кэшированием

### db/cache.py
```python
"""Caching layer for database queries."""
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from cachetools import TTLCache
from dataclasses import dataclass
from domain.models import Market, Snapshot


@dataclass
class CacheStats:
    """Cache statistics."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class RepoCache:
    """Thread-safe cache for repository queries."""
    
    def __init__(
        self,
        market_ttl: int = 300,  # 5 min
        snapshot_ttl: int = 10,  # 10 sec
        max_markets: int = 1000,
        max_snapshots: int = 5000,
    ):
        self._markets = TTLCache(maxsize=max_markets, ttl=market_ttl)
        self._snapshots = TTLCache(maxsize=max_snapshots, ttl=snapshot_ttl)
        self._stats = CacheStats()
    
    def get_market(self, market_id: str) -> Optional[Market]:
        """Get cached market."""
        market = self._markets.get(market_id)
        if market:
            self._stats.hits += 1
        else:
            self._stats.misses += 1
        return market
    
    def set_market(self, market: Market) -> None:
        """Cache market."""
        self._markets[market.market_id] = market
    
    def get_snapshot(self, market_id: str, outcome: str) -> Optional[Dict[str, Any]]:
        """Get cached snapshot."""
        key = (market_id, outcome)
        snap = self._snapshots.get(key)
        if snap:
            self._stats.hits += 1
        else:
            self._stats.misses += 1
        return snap
    
    def set_snapshot(self, market_id: str, outcome: str, data: Dict[str, Any]) -> None:
        """Cache snapshot."""
        key = (market_id, outcome)
        self._snapshots[key] = data
    
    def invalidate_market(self, market_id: str) -> None:
        """Invalidate market cache."""
        self._markets.pop(market_id, None)
    
    def invalidate_snapshots(self, market_id: str) -> None:
        """Invalidate all snapshots for market."""
        keys_to_remove = [k for k in self._snapshots.keys() if k[0] == market_id]
        for k in keys_to_remove:
            self._snapshots.pop(k, None)
    
    def clear(self) -> None:
        """Clear all caches."""
        self._markets.clear()
        self._snapshots.clear()
    
    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats
```

### db/optimized_repo.py
```python
"""Optimized repository with caching and batch operations."""
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
from db.repo import Repo
from db.cache import RepoCache
from domain.models import Market, Signal
from utils.validation import validate_market_id


class OptimizedRepo(Repo):
    """Repository with caching and optimizations."""
    
    def __init__(self, db_path: str, enable_cache: bool = True):
        super().__init__(db_path)
        self._cache = RepoCache() if enable_cache else None
    
    def get_market(self, market_id: str) -> Optional[Market]:
        """Get market with caching."""
        validate_market_id(market_id)
        
        if self._cache:
            cached = self._cache.get_market(market_id)
            if cached:
                return cached
        
        market = super().get_market(market_id)
        
        if market and self._cache:
            self._cache.set_market(market)
        
        return market
    
    def get_latest_snapshots(
        self,
        market_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """Get latest snapshots with caching."""
        validate_market_id(market_id)
        
        result = {}
        cache_miss_outcomes = []
        
        # Try cache first
        if self._cache:
            for outcome in ["YES", "NO"]:
                cached = self._cache.get_snapshot(market_id, outcome)
                if cached:
                    result[outcome] = cached
                else:
                    cache_miss_outcomes.append(outcome)
        else:
            cache_miss_outcomes = ["YES", "NO"]
        
        # Fetch missing from DB
        if cache_miss_outcomes:
            with self.conn() as con:
                placeholders = ",".join("?" * len(cache_miss_outcomes))
                rows = con.execute(
                    f"""
                    SELECT DISTINCT ON (outcome)
                        outcome, bid, ask, mid, spread, liquidity, volume
                    FROM snapshots
                    WHERE market_id = ? AND outcome IN ({placeholders})
                    ORDER BY outcome, ts DESC
                    """,
                    (market_id, *cache_miss_outcomes)
                ).fetchall()
                
                for row in rows:
                    outcome = row[0]
                    snap = {
                        "bid": row[1],
                        "ask": row[2],
                        "mid": row[3],
                        "spread": row[4],
                        "liquidity": row[5],
                        "volume": row[6],
                    }
                    result[outcome] = snap
                    
                    if self._cache:
                        self._cache.set_snapshot(market_id, outcome, snap)
        
        return result
    
    def insert_signals_batch(self, signals: List[Signal]) -> int:
        """Batch insert signals."""
        if not signals:
            return 0
        
        with self.conn() as con:
            con.executemany(
                """
                INSERT INTO signals(
                    signal_id, ts, run_id, agent_id, kind,
                    scope_market_id, scope_group_key, scope_pair_key,
                    features_json, claim_json, candidates_json,
                    explain_short, explain_long
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        s.signal_id,
                        s.ts.isoformat(),
                        s.run_id,
                        s.agent_id,
                        s.kind.value,
                        s.scope_market_id,
                        s.scope_group_key,
                        s.scope_pair_key,
                        json.dumps(s.features),
                        json.dumps(s.claim),
                        json.dumps([asdict(c) for c in s.candidates]),
                        s.explain_short,
                        s.explain_long,
                    )
                    for s in signals
                ]
            )
            return len(signals)
    
    def get_cache_stats(self) -> Optional[Dict[str, Any]]:
        """Get cache statistics."""
        if not self._cache:
            return None
        
        stats = self._cache.get_stats()
        return {
            "hits": stats.hits,
            "misses": stats.misses,
            "hit_rate": stats.hit_rate,
        }
```

## 4. Улучшенный агент базового класса

### agents/enhanced_base.py
```python
"""Enhanced base agent with error handling and metrics."""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
from contextlib import contextmanager
from time import perf_counter

from domain.models import Signal
from utils.time import now_utc


@dataclass
class AgentMetrics:
    """Agent performance metrics."""
    agent_id: str
    calls: int = 0
    signals_generated: int = 0
    errors: int = 0
    total_time_sec: float = 0.0
    last_run: Optional[datetime] = None
    
    @property
    def avg_time_sec(self) -> float:
        return self.total_time_sec / self.calls if self.calls > 0 else 0.0
    
    @property
    def signals_per_call(self) -> float:
        return self.signals_generated / self.calls if self.calls > 0 else 0.0


@dataclass
class AgentContext:
    """Enhanced agent context with utilities."""
    run_id: str
    now: datetime
    repo: Any
    settings: Any
    
    # Optional caches
    markets: Optional[List[Any]] = None
    latest_snapshots: Optional[Dict[str, Dict]] = None
    
    def get_market_snapshots(self, market_id: str) -> Dict[str, Dict]:
        """Get snapshots for market (cached)."""
        if self.latest_snapshots and market_id in self.latest_snapshots:
            return self.latest_snapshots[market_id]
        
        if hasattr(self.repo, "get_latest_snapshots"):
            return self.repo.get_latest_snapshots(market_id)
        
        return {}


class EnhancedAgent(ABC):
    """Enhanced base agent with built-in metrics and error handling."""
    
    agent_id: str = "base"
    
    def __init__(self):
        self._metrics = AgentMetrics(agent_id=self.agent_id)
        self._logger = logging.getLogger(f"agent.{self.agent_id}")
    
    @abstractmethod
    def _propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        """Internal propose implementation."""
        pass
    
    def propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        """Propose signals with error handling and metrics."""
        start = perf_counter()
        signals = []
        
        try:
            self._metrics.calls += 1
            self._metrics.last_run = ctx.now
            
            signals = self._propose(ctx, market_id)
            
            self._metrics.signals_generated += len(signals)
            
        except Exception as e:
            self._metrics.errors += 1
            self._logger.exception(f"Agent {self.agent_id} failed: {e}")
            # Don't re-raise, let caller handle
        
        finally:
            elapsed = perf_counter() - start
            self._metrics.total_time_sec += elapsed
        
        return signals
    
    def get_metrics(self) -> AgentMetrics:
        """Get agent metrics."""
        return self._metrics
    
    @contextmanager
    def _timed_section(self, name: str):
        """Context manager for timing code sections."""
        start = perf_counter()
        try:
            yield
        finally:
            elapsed = perf_counter() - start
            self._logger.debug(f"{name} took {elapsed:.3f}s")
```

Продолжение в следующем файле...
