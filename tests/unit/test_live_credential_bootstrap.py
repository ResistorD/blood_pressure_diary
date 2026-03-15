from __future__ import annotations

from types import SimpleNamespace

from app.runtime_config import bootstrap_live_credentials, validate_runtime_settings


def _settings(**kwargs):
    base = dict(
        runtime_profile="live",
        execution_mode="live_stage0",
        enable_execution=True,
        live_dry_run=False,
        live_max_notional=10.0,
        live_max_orders_per_day=2,
        admin_token="admin",
        private_key="pk",
        polymarket_key="api-key",
        polymarket_secret="",
        polymarket_passphrase="",
        polymarket_api_url="https://api.example",
        risk=SimpleNamespace(max_notional_total=200.0),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_bootstrap_ready_from_config_inputs(monkeypatch) -> None:
    monkeypatch.setattr("app.runtime_config._BOOTSTRAP_CACHE", {})
    monkeypatch.setattr("app.runtime_config._BOOTSTRAP_CREDS", {})
    monkeypatch.setattr(
        "app.runtime_config._derive_api_credentials_via_sdk",
        lambda **_kwargs: {
            "api_key": "derived-key",
            "api_secret": "derived-secret",
            "api_passphrase": "derived-passphrase",
        },
    )
    settings = _settings(polymarket_key="", polymarket_secret="", polymarket_passphrase="")
    state = bootstrap_live_credentials(settings)
    assert state["attempted"] is True
    assert state["success"] is True
    assert state["mode"] == "derived_sdk"
    assert state["missing"] == []
    assert getattr(settings, "_live_api_creds", {}) == {
        "api_key": "derived-key",
        "api_secret": "derived-secret",
        "api_passphrase": "derived-passphrase",
    }


def test_bootstrap_ready_from_static_bundle() -> None:
    state = bootstrap_live_credentials(_settings(polymarket_secret="sec", polymarket_passphrase="pp"))
    assert state["attempted"] is True
    assert state["success"] is True
    assert state["mode"] == "api_key_bundle"
    assert state["missing"] == []


def test_bootstrap_missing_private_key() -> None:
    state = bootstrap_live_credentials(_settings(private_key=""))
    assert state["success"] is False
    assert "PRIVATE_KEY" in state["missing"]


def test_bootstrap_missing_api_url() -> None:
    state = bootstrap_live_credentials(_settings(polymarket_api_url=""))
    assert state["success"] is False
    assert "POLYMARKET_API_URL" in state["missing"]


def test_bootstrap_failure_is_surfaced_safely(monkeypatch) -> None:
    monkeypatch.setattr("app.runtime_config._BOOTSTRAP_CACHE", {})
    monkeypatch.setattr("app.runtime_config._BOOTSTRAP_CREDS", {})
    monkeypatch.setattr(
        "app.runtime_config._derive_api_credentials_via_sdk",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    diag = validate_runtime_settings(
        _settings(polymarket_key="", polymarket_secret="", polymarket_passphrase=""),
        execution_mode_raw="live_stage0",
        paper_fixed_notional=10.0,
    )
    bootstrap = diag["live_credential_bootstrap"]
    assert bootstrap["success"] is False
    assert "SDK credential derivation failed" in (bootstrap["safe_error"] or "")


def test_diagnostics_do_not_expose_secrets() -> None:
    secret_private = "SECRET_PRIVATE_KEY_VALUE"
    secret_key = "SECRET_POLYMARKET_KEY_VALUE"
    secret_secret = "SECRET_POLYMARKET_SECRET_VALUE"
    diag = validate_runtime_settings(
        _settings(
            private_key=secret_private,
            polymarket_key=secret_key,
            polymarket_secret=secret_secret,
            polymarket_passphrase="SECRET_PASSPHRASE_VALUE",
        ),
        execution_mode_raw="live_stage0",
        paper_fixed_notional=10.0,
    )
    payload = str(diag)
    assert secret_private not in payload
    assert secret_key not in payload
    assert secret_secret not in payload
