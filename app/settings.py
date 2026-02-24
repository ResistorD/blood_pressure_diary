"""Settings facade.

Canonical runtime settings live in app.runtime_config (RuntimeSettings).
Legacy config models are re-exported for backward compatibility.
"""
from app.runtime_config import RuntimeSettings as Settings, load_runtime_config
from app.config import AppSettings, LifecycleSettings, RiskConfig as RiskSettings


def load_settings() -> Settings:
    """Load canonical runtime settings."""
    _config, settings = load_runtime_config()
    return settings


__all__ = ["Settings", "load_settings", "AppSettings", "LifecycleSettings", "RiskSettings"]
