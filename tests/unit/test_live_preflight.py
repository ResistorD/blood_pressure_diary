from __future__ import annotations

from types import SimpleNamespace

from api.http import _build_live_preflight


def _settings(
    execution_mode: str,
    live_max_notional: float,
    max_total_notional: float = 500.0,
    *,
    enable_execution: bool = True,
    live_dry_run: bool = False,
    live_max_orders_per_day: int = 1,
):
    return SimpleNamespace(
        execution_mode=execution_mode,
        live_max_notional=live_max_notional,
        enable_execution=enable_execution,
        live_dry_run=live_dry_run,
        live_max_orders_per_day=live_max_orders_per_day,
        risk=SimpleNamespace(max_notional_total=max_total_notional),
    )


def test_preflight_paper_mode_not_ready() -> None:
    out = _build_live_preflight(
        settings=_settings("paper", 5.0),
        execution_mode_raw="paper",
        executor_present=False,
        admin_token_raw="token",
        paper_fixed_notional=10.0,
    )
    assert out["execution_mode"] == "PAPER"
    assert out["live_executor"] is False
    assert out["ready_for_live"] is False
    assert "live_requirements" in out
    assert "live_missing" in out


def test_preflight_live_stage0_without_admin_token_not_ready() -> None:
    out = _build_live_preflight(
        settings=_settings("live_stage0", 5.0),
        execution_mode_raw="live_stage0",
        executor_present=True,
        admin_token_raw="",
        paper_fixed_notional=10.0,
    )
    assert out["execution_mode"] == "LIVE_STAGE0"
    assert out["live_executor"] is True
    assert out["admin_token_protected"] is False
    assert out["ready_for_live"] is False


def test_preflight_live_stage0_with_token_and_limits_ready() -> None:
    settings = _settings("live_stage0", 7.5, max_total_notional=300.0)
    settings.private_key = "0x59c6995e998f97a5a0044966f0945386cf4ce0f7f7f5e63fce6f2fd4f8e8d8f6"
    settings.polymarket_funder = "0xFunder"
    settings.polymarket_signature_type = 0
    settings.polymarket_chain_id = 137
    out = _build_live_preflight(
        settings=settings,
        execution_mode_raw="live_stage0",
        executor_present=True,
        admin_token_raw="token",
        paper_fixed_notional=12.0,
        private_key_configured=True,
        polymarket_key_configured=True,
        api_url_configured=True,
        execution_enabled=True,
        dry_run=False,
    )
    assert out["execution_mode"] == "LIVE_STAGE0"
    assert out["live_executor"] is True
    assert out["admin_token_protected"] is True
    assert out["stage0_limits"]["max_notional_per_order"] == 7.5
    assert out["stage0_limits"]["max_total_notional"] == 300.0
    assert out["stage0_limits"]["paper_fixed_notional"] == 12.0
    assert out["live_requirements"]["executor_buildable"] is True
    assert out["live_missing"] == []
    assert out["ready_for_live"] is True
    assert "trading_identity" in out
    assert "signer_address" in out
    assert out["effective_funder_address"] == "0xFunder"


def test_preflight_live_executor_detection() -> None:
    out = _build_live_preflight(
        settings=_settings("live_stage0", 5.0),
        execution_mode_raw="live_stage0",
        executor_present=False,
        admin_token_raw="token",
        paper_fixed_notional=10.0,
    )
    assert out["execution_mode"] == "LIVE_STAGE0"
    assert out["live_executor"] is False
    assert out["ready_for_live"] is False


def test_preflight_does_not_expose_secret_values() -> None:
    secret_pk = "SECRET_PRIVATE_KEY_VALUE"
    secret_pm = "SECRET_POLYMARKET_KEY_VALUE"
    out = _build_live_preflight(
        settings=_settings("live_stage0", 7.5),
        execution_mode_raw="live_stage0",
        executor_present=True,
        admin_token_raw="token",
        paper_fixed_notional=12.0,
        private_key_configured=bool(secret_pk),
        polymarket_key_configured=bool(secret_pm),
        api_url_configured=True,
        execution_enabled=True,
        dry_run=False,
    )
    payload = str(out)
    assert secret_pk not in payload
    assert secret_pm not in payload
