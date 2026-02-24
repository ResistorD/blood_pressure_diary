"""Enhanced configuration system with full validation."""
from __future__ import annotations

import hashlib
import json
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    
    @field_validator("max_spread", "logic_max_spread")
    @classmethod
    def validate_spread(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Spread must be between 0 and 1")
        return v


class DecisionConfig(BaseModel):
    """Configuration for decision engine."""
    
    arb_buy_threshold: float = Field(
        0.99, ge=0.9, le=1.0,
        description="Buy threshold for YES+NO sum (< threshold = buy signal)"
    )
    arb_close_threshold: float = Field(
        1.00, ge=0.95, le=1.1,
        description="Close threshold for YES+NO sum (>= threshold = close signal)"
    )
    min_emit_interval_sec: int = Field(
        120, ge=0,
        description="Minimum seconds between duplicate decisions"
    )
    max_spread: float = Field(0.04, ge=0, le=1)
    min_liquidity: float = Field(50.0, ge=0)

    # --- extended tradeability checks (v2) ---
    # Market should have at least N recent snapshots to be considered "stable enough".
    min_age_snaps: int = Field(5, ge=0, description="Minimum snapshots before tradeable")

    # Volatility filter: if mid is swinging too much, avoid paper-trading (noise).
    # Metric: stdev of mid deltas over last `volatility_window` points.
    volatility_window: int = Field(12, ge=2, description="Window for volatility calc")
    max_volatility: float = Field(0.08, ge=0, le=1, description="Max allowed volatility")

    # Liquidity trend: avoid markets where liquidity is falling fast.
    liquidity_trend_window: int = Field(12, ge=2, description="Window for liquidity trend")
    min_liquidity_trend: float = Field(0.0, description="Min slope (last-first)/window")

    # --- quality flags (v2) ---
    stale_after_sec: int = Field(180, ge=1, description="Snapshot older than this is stale")
    require_two_sided_book: bool = Field(True, description="Require both bid and ask in latest book")
    thin_liquidity_factor: float = Field(
        0.5, ge=0, le=1, description="Thin if liquidity < min_liquidity * factor"
    )
    
    @model_validator(mode='after')
    def validate_thresholds(self):
        if self.arb_close_threshold <= self.arb_buy_threshold:
            raise ValueError("Close threshold must be > buy threshold")
        return self


class RiskConfig(BaseModel):
    """Risk management configuration."""
    
    max_notional_total: float = Field(500.0, ge=0)
    max_notional_per_group: float = Field(250.0, ge=0)
    max_notional_per_market: float = Field(150.0, ge=0)
    min_liquidity: float = Field(50.0, ge=0)
    max_spread: float = Field(0.10, ge=0, le=1)
    max_impact_pct: float = Field(0.15, ge=0, le=1)

    # --- paper execution limits (UI + engine) ---
    max_open_positions: int = Field(12, ge=0, description="Max concurrent open paper positions")

    # Kill-switch: if True, any new paper opens are blocked.
    # Stored in DB settings as well, but config provides a default.
    kill_switch_default: bool = Field(False, description="Default kill-switch state")

    # Capital usage guard for opening new paper positions.
    # Example: 0.85 means block new opens when 85%+ of total notional limit is used.
    max_capital_usage_pct: float = Field(0.85, ge=0, le=1)

    # Auto-kill switch: when hard limits are breached, set kill_switch=1 in DB settings.
    auto_kill_on_limit_breach: bool = Field(True)
    
    @model_validator(mode='after')
    def validate_limits(self):
        if self.max_notional_per_group > self.max_notional_total:
            raise ValueError("Per-group limit cannot exceed total limit")
        if self.max_notional_per_market > self.max_notional_per_group:
            raise ValueError("Per-market limit cannot exceed per-group limit")
        return self


class DispatcherConfig(BaseModel):
    """Dispatcher loop configuration."""
    
    poll_interval_sec: int = Field(20, ge=1, description="Market data poll interval")
    reconcile_interval_sec: int = Field(60, ge=1, description="Decision reconciliation interval")
    event_batch_size: int = Field(500, ge=1, le=10000, description="Max events per iteration")
    sleep_sec: float = Field(0.2, ge=0.01, le=5.0, description="Sleep between iterations")


class DatabaseConfig(BaseModel):
    """Database configuration."""
    
    path: str = Field("polysyndicate.db", description="SQLite database path")
    wal_mode: bool = Field(True, description="Enable WAL mode")
    timeout_sec: int = Field(30, ge=1, description="Connection timeout")
    cache_enabled: bool = Field(True, description="Enable query caching")
    cache_market_ttl: int = Field(300, ge=1, description="Market cache TTL (seconds)")
    cache_snapshot_ttl: int = Field(10, ge=1, description="Snapshot cache TTL (seconds)")


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
    taker_fee_rate: float = Field(0.0, ge=0, description="Taker fee rate")
    slippage_rate: float = Field(0.0, ge=0, description="Execution slippage rate")
    execution_mode: str = Field("paper", description="Execution mode: paper|live")
    live_max_notional: float = Field(0.0, ge=0, description="Max notional per live order")
    live_max_orders_per_day: int = Field(0, ge=0, description="Max live orders per day")
    live_dry_run: bool = Field(True, description="Dry-run guard for live execution")
    dispatcher_tick_sec: float = Field(1.0, ge=0.01, description="Main loop sleep interval")
    db_flush_sec: float = Field(3.0, ge=0, description="DB write-behind flush interval")
    deprioritize_mode: str = Field("ui", description="Deprioritize mode: off|ui|pipeline")
    deprioritize_min_weight: float = Field(0.05, ge=0.0, le=1.0, description="Minimum weight clamp")
    
    # Sub-configs
    agent: AgentConfig = Field(default_factory=AgentConfig)
    decision: DecisionConfig = Field(default_factory=DecisionConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    dispatcher: DispatcherConfig = Field(default_factory=DispatcherConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    
    def config_hash(self) -> str:
        """Generate hash of configuration for tracking."""
        payload = json.dumps(self.model_dump(), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load from environment variables with PS_ prefix."""
        class _EnvSettings(BaseSettings):
            model_config = SettingsConfigDict(
                env_prefix="PS_",
                env_file=".env",
                extra="ignore"
            )
            
            mode: Mode = Mode.DRY_RUN
            api_host: str = "127.0.0.1"
            api_port: int = 8000
            enable_ingest: bool = True
            enable_agents: bool = True
            enable_decision: bool = True
            enable_execution: bool = False
            taker_fee_rate: float = Field(0.0, validation_alias=AliasChoices("TAKER_FEE_RATE", "PS_TAKER_FEE_RATE"))
            slippage_rate: float = Field(0.0, validation_alias=AliasChoices("SLIPPAGE_RATE", "PS_SLIPPAGE_RATE"))
            execution_mode: str = Field("paper", validation_alias=AliasChoices("EXECUTION_MODE", "PS_EXECUTION_MODE"))
            live_max_notional: float = Field(0.0, validation_alias=AliasChoices("LIVE_MAX_NOTIONAL", "PS_LIVE_MAX_NOTIONAL"))
            live_max_orders_per_day: int = Field(0, validation_alias=AliasChoices("LIVE_MAX_ORDERS_PER_DAY", "PS_LIVE_MAX_ORDERS_PER_DAY"))
            live_dry_run: bool = Field(True, validation_alias=AliasChoices("LIVE_DRY_RUN", "PS_LIVE_DRY_RUN"))
            dispatcher_tick_sec: float = Field(1.0, validation_alias=AliasChoices("DISPATCHER_TICK_SEC", "PS_DISPATCHER_TICK_SEC"))
            db_flush_sec: float = Field(3.0, validation_alias=AliasChoices("DB_FLUSH_SEC", "PS_DB_FLUSH_SEC"))
            deprioritize_mode: str = Field(
                "ui",
                validation_alias=AliasChoices("DEPRIORITIZE_MODE", "PS_DEPRIORITIZE_MODE"),
            )
            deprioritize_min_weight: float = Field(
                0.05,
                validation_alias=AliasChoices("DEPRIORITIZE_MIN_WEIGHT", "PS_DEPRIORITIZE_MIN_WEIGHT"),
            )
        
        env_settings = _EnvSettings()
        return cls(**env_settings.model_dump())

    @field_validator("deprioritize_mode")
    @classmethod
    def validate_deprioritize_mode(cls, v: str) -> str:
        mode = (v or "").strip().lower()
        if mode not in {"off", "ui", "pipeline"}:
            raise ValueError("deprioritize_mode must be one of: off, ui, pipeline")
        return mode


# Backward compatibility - keep old settings structure
class LifecycleSettings(BaseModel):
    """Legacy lifecycle settings."""
    min_edge: float = 0.03
    cooldown_sec: int = 300
    switch_edge_delta: float = 0.02


class AppSettings(BaseSettings):
    """Legacy AppSettings for backward compatibility."""
    model_config = SettingsConfigDict(env_prefix="PS_", env_file=".env", extra="ignore")

    mode: Mode = Mode.DRY_RUN
    db_path: str = Field(default="polysyndicate.db")

    poll_interval_sec: int = 20
    reconcile_interval_sec: int = 60

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    risk: RiskConfig = Field(default_factory=RiskConfig)
    lifecycle: LifecycleSettings = Field(default_factory=LifecycleSettings)

    enable_ingest: bool = True
    enable_agents: bool = True
    enable_decision: bool = True
    enable_execution: bool = False
    taker_fee_rate: float = Field(default=0.0, validation_alias=AliasChoices("PS_TAKER_FEE_RATE", "TAKER_FEE_RATE"))
    slippage_rate: float = Field(default=0.0, validation_alias=AliasChoices("PS_SLIPPAGE_RATE", "SLIPPAGE_RATE"))
    execution_mode: str = Field(default="paper", validation_alias=AliasChoices("PS_EXECUTION_MODE", "EXECUTION_MODE"))
    live_max_notional: float = Field(default=0.0, validation_alias=AliasChoices("PS_LIVE_MAX_NOTIONAL", "LIVE_MAX_NOTIONAL"))
    live_max_orders_per_day: int = Field(default=0, validation_alias=AliasChoices("PS_LIVE_MAX_ORDERS_PER_DAY", "LIVE_MAX_ORDERS_PER_DAY"))
    live_dry_run: bool = Field(default=True, validation_alias=AliasChoices("PS_LIVE_DRY_RUN", "LIVE_DRY_RUN"))
    dispatcher_tick_sec: float = Field(default=1.0, validation_alias=AliasChoices("PS_DISPATCHER_TICK_SEC", "DISPATCHER_TICK_SEC"))
    db_flush_sec: float = Field(default=3.0, validation_alias=AliasChoices("PS_DB_FLUSH_SEC", "DB_FLUSH_SEC"))
    deprioritize_mode: str = Field(
        default="ui",
        validation_alias=AliasChoices("PS_DEPRIORITIZE_MODE", "DEPRIORITIZE_MODE"),
    )
    deprioritize_min_weight: float = Field(
        default=0.05,
        validation_alias=AliasChoices("PS_DEPRIORITIZE_MIN_WEIGHT", "DEPRIORITIZE_MIN_WEIGHT"),
    )

    def config_hash(self) -> str:
        payload = json.dumps(self.model_dump(), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @field_validator("deprioritize_mode")
    @classmethod
    def validate_deprioritize_mode(cls, v: str) -> str:
        mode = (v or "").strip().lower()
        if mode not in {"off", "ui", "pipeline"}:
            raise ValueError("deprioritize_mode must be one of: off, ui, pipeline")
        return mode
    
    @property
    def host(self) -> str:
        """Alias for api_host."""
        return self.api_host
    
    @property
    def port(self) -> int:
        """Alias for api_port."""
        return self.api_port
    
    @property
    def log_level(self) -> str:
        """Default log level."""
        return "info"
