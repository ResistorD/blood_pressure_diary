from __future__ import annotations

from types import SimpleNamespace

from app.runtime_config import admin_token_configured, resolve_admin_token, validate_runtime_settings
from app.runtime_env import bootstrap_env


def test_profile_bootstrap_loads_base_and_profile_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.runtime_env._BOOTSTRAP", None)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("PS_APP_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "live")

    root = tmp_path
    (root / ".env").write_text("PS_MODE=DRY_RUN\n", encoding="utf-8")
    (root / ".env.live").write_text("LIVE_DRY_RUN=0\n", encoding="utf-8")

    out = bootstrap_env(project_root=root)

    assert out.profile == "live"
    assert str(root / ".env") in out.loaded_files
    assert str(root / ".env.live") in out.loaded_files


def test_startup_validation_flags_incoherent_live_stage0(monkeypatch) -> None:
    # Keep validation deterministic regardless of local .env in workspace.
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    settings = SimpleNamespace(
        runtime_profile="live",
        execution_mode="live_stage0",
        enable_execution=True,
        live_dry_run=True,
        live_max_notional=0.0,
        live_max_orders_per_day=0,
        risk=SimpleNamespace(max_notional_total=0.0),
        admin_token="",
        private_key="",
        polymarket_key="",
        polymarket_api_url="",
    )

    out = validate_runtime_settings(settings, execution_mode_raw="live_stage0", paper_fixed_notional=0.0)

    assert out["ok"] is False
    assert "ADMIN_TOKEN is required for LIVE_STAGE0" in out["errors"]
    assert "PRIVATE_KEY is required for LIVE_STAGE0" in out["errors"]
    assert "LIVE_CREDENTIAL_BOOTSTRAP_FAILED" in out["errors"]


def test_admin_token_detection_prefers_settings_value(monkeypatch) -> None:
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    settings = SimpleNamespace(admin_token="from-settings")

    assert admin_token_configured(settings) is True
    assert resolve_admin_token(settings) == "from-settings"


def test_live_readiness_detection_uses_unified_settings_path(monkeypatch) -> None:
    monkeypatch.delenv("PRIVATE_KEY", raising=False)
    monkeypatch.delenv("POLYMARKET_KEY", raising=False)
    monkeypatch.delenv("POLYMARKET_API_URL", raising=False)

    settings = SimpleNamespace(
        runtime_profile="live",
        execution_mode="live_stage0",
        enable_execution=True,
        live_dry_run=False,
        live_max_notional=5.0,
        live_max_orders_per_day=2,
        admin_token="admin",
        private_key="pk",
        polymarket_key="pm",
        polymarket_secret="sec",
        polymarket_passphrase="pp",
        polymarket_api_url="https://api.example",
        risk=SimpleNamespace(max_notional_total=100.0),
    )

    out = validate_runtime_settings(settings, execution_mode_raw="live_stage0", paper_fixed_notional=10.0)

    assert out["ok"] is True
    assert out["live_requirements"]["private_key_configured"] is True
    assert out["live_requirements"]["polymarket_key_configured"] is True
    assert out["live_requirements"]["api_url_configured"] is True
    assert out["live_requirements"]["executor_buildable"] is True
