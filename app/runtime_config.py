from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import AppConfig, AppSettings
from utils.logging import get_logger, warn_exc

logger = get_logger("app.runtime_config")


@dataclass
class RuntimeSettings:
    """Unified runtime settings facade used by dispatchers and API bootstraps."""

    _config: AppConfig | AppSettings
    mode: Any
    db_path: str
    api_host: str
    api_port: int
    host: str
    port: int
    log_level: str
    poll_interval_sec: int
    reconcile_interval_sec: int
    enable_ingest: bool
    enable_agents: bool
    enable_decision: bool
    enable_execution: bool
    taker_fee_rate: float
    slippage_rate: float
    execution_mode: str
    live_max_notional: float
    live_max_orders_per_day: int
    live_dry_run: bool
    dispatcher_tick_sec: float
    db_flush_sec: float
    deprioritize_mode: str
    deprioritize_min_weight: float
    risk: Any
    agent: Any = None
    decision: Any = None

    def config_hash(self) -> str:
        return self._config.config_hash()


def load_runtime_config() -> tuple[AppConfig | AppSettings, RuntimeSettings]:
    """Load modern AppConfig first, fallback to legacy AppSettings."""
    try:
        config: AppConfig | AppSettings = AppConfig.from_env()
    except Exception:
        warn_exc(logger, "AppConfig.from_env failed; falling back to AppSettings")
        config = AppSettings()
    return config, to_runtime_settings(config)


def to_runtime_settings(config: AppConfig | AppSettings) -> RuntimeSettings:
    if isinstance(config, AppSettings):
        return RuntimeSettings(
            _config=config,
            mode=config.mode,
            db_path=config.db_path,
            api_host=config.api_host,
            api_port=config.api_port,
            host=config.host,
            port=config.port,
            log_level=config.log_level,
            poll_interval_sec=config.poll_interval_sec,
            reconcile_interval_sec=config.reconcile_interval_sec,
            enable_ingest=config.enable_ingest,
            enable_agents=config.enable_agents,
            enable_decision=config.enable_decision,
            enable_execution=config.enable_execution,
            taker_fee_rate=getattr(config, "taker_fee_rate", 0.0),
            slippage_rate=getattr(config, "slippage_rate", 0.0),
            execution_mode=getattr(config, "execution_mode", "paper"),
            live_max_notional=getattr(config, "live_max_notional", 0.0),
            live_max_orders_per_day=getattr(config, "live_max_orders_per_day", 0),
            live_dry_run=getattr(config, "live_dry_run", True),
            dispatcher_tick_sec=getattr(config, "dispatcher_tick_sec", 1.0),
            db_flush_sec=getattr(config, "db_flush_sec", 3.0),
            deprioritize_mode=getattr(config, "deprioritize_mode", "ui"),
            deprioritize_min_weight=float(getattr(config, "deprioritize_min_weight", 0.05)),
            risk=getattr(config, "risk", None),
            agent=getattr(config, "agent", None),
            decision=getattr(config, "decision", None),
        )

    return RuntimeSettings(
        _config=config,
        mode=config.mode,
        db_path=getattr(config.database, "path", "polysyndicate.db"),
        api_host=config.api_host,
        api_port=config.api_port,
        host=config.api_host,
        port=config.api_port,
        log_level="info",
        poll_interval_sec=config.dispatcher.poll_interval_sec,
        reconcile_interval_sec=config.dispatcher.reconcile_interval_sec,
        enable_ingest=config.enable_ingest,
        enable_agents=config.enable_agents,
        enable_decision=config.enable_decision,
        enable_execution=config.enable_execution,
        taker_fee_rate=getattr(config, "taker_fee_rate", 0.0),
        slippage_rate=getattr(config, "slippage_rate", 0.0),
        execution_mode=getattr(config, "execution_mode", "paper"),
        live_max_notional=getattr(config, "live_max_notional", 0.0),
        live_max_orders_per_day=getattr(config, "live_max_orders_per_day", 0),
        live_dry_run=getattr(config, "live_dry_run", True),
        dispatcher_tick_sec=getattr(config, "dispatcher_tick_sec", 1.0),
        db_flush_sec=getattr(config, "db_flush_sec", 3.0),
        deprioritize_mode=getattr(config, "deprioritize_mode", "ui"),
        deprioritize_min_weight=float(getattr(config, "deprioritize_min_weight", 0.05)),
        risk=getattr(config, "risk", None),
        agent=getattr(config, "agent", None),
        decision=getattr(config, "decision", None),
    )
