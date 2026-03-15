from __future__ import annotations

import os
from hashlib import sha256
from dataclasses import dataclass, field
from typing import Any

from app.config import AppConfig, AppSettings
from app.runtime_env import detect_profile, normalize_profile
from utils.logging import get_logger, warn_exc

logger = get_logger("app.runtime_config")
_BOOTSTRAP_CACHE: dict[str, dict[str, Any]] = {}
_BOOTSTRAP_CREDS: dict[str, dict[str, str]] = {}


@dataclass
class RuntimeSettings:
    """Unified runtime settings facade used by dispatchers and API bootstraps."""

    _config: AppConfig | AppSettings
    mode: Any
    runtime_profile: str
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
    admin_token: str = field(repr=False, default="")
    private_key: str = field(repr=False, default="")
    polymarket_key: str = field(repr=False, default="")
    polymarket_secret: str = field(repr=False, default="")
    polymarket_passphrase: str = field(repr=False, default="")
    polymarket_api_url: str = ""
    polymarket_chain_id: int = 137
    polymarket_signature_type: int = 0
    polymarket_funder: str = ""
    live_max_notional: float = 0.0
    live_max_orders_per_day: int = 0
    live_dry_run: bool = True
    dispatcher_tick_sec: float = 1.0
    db_flush_sec: float = 3.0
    deprioritize_mode: str = "ui"
    deprioritize_min_weight: float = 0.05
    risk: Any = None
    agent: Any = None
    decision: Any = None
    startup_validation: dict[str, Any] = field(default_factory=dict)

    def config_hash(self) -> str:
        return self._config.config_hash()


def _resolve_secret(settings: Any, *names: str) -> str:
    for name in names:
        v = str(getattr(settings, name, "") or "").strip()
        if v:
            return v
    env_map = {
        "admin_token": ("ADMIN_TOKEN", "PS_ADMIN_TOKEN"),
        "private_key": ("PRIVATE_KEY", "PS_PRIVATE_KEY"),
        "polymarket_key": ("POLYMARKET_KEY", "PS_POLYMARKET_KEY"),
        "polymarket_secret": ("POLYMARKET_SECRET", "PS_POLYMARKET_SECRET", "CLOB_SECRET", "PS_CLOB_SECRET"),
        "polymarket_passphrase": (
            "POLYMARKET_PASSPHRASE",
            "PS_POLYMARKET_PASSPHRASE",
            "CLOB_PASSPHRASE",
            "PS_CLOB_PASSPHRASE",
        ),
        "polymarket_funder": ("POLYMARKET_FUNDER", "PS_POLYMARKET_FUNDER"),
        "polymarket_api_url": ("POLYMARKET_API_URL", "PS_POLYMARKET_API_URL"),
    }
    for name in names:
        for env_name in env_map.get(name, ()):  # pragma: no branch
            v = str(os.getenv(env_name) or "").strip()
            if v:
                return v
    return ""


def _bootstrap_cache_key(
    *,
    private_key: str,
    host: str,
    chain_id: int,
    signature_type: int,
    funder: str,
    has_static_bundle: bool,
) -> str:
    payload = "|".join(
        [
            private_key,
            host,
            str(chain_id),
            str(signature_type),
            funder,
            "1" if has_static_bundle else "0",
        ]
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _extract_cred_value(creds: Any, *keys: str) -> str:
    for key in keys:
        if isinstance(creds, dict):
            v = creds.get(key)
        else:
            v = getattr(creds, key, None)
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _derive_api_credentials_via_sdk(
    *,
    host: str,
    private_key: str,
    chain_id: int,
    signature_type: int,
    funder: str,
) -> dict[str, str]:
    from py_clob_client.client import ClobClient

    errors: list[str] = []
    client = None
    kwargs = {
        "host": host,
        "key": private_key,
        "chain_id": chain_id,
        "signature_type": signature_type,
    }
    if funder:
        kwargs["funder"] = funder
    ctor_attempts = [
        lambda: ClobClient(**kwargs),
        lambda: ClobClient(host, private_key, chain_id),
        lambda: ClobClient(host=host, key=private_key, chain_id=chain_id),
    ]
    for builder in ctor_attempts:
        try:
            client = builder()
            break
        except Exception as e:
            errors.append(type(e).__name__)
    if client is None:
        raise RuntimeError(f"ClobClient init failed ({','.join(errors[:2]) or 'unknown'})")

    derive_methods = [
        "create_or_derive_api_creds",
        "create_or_derive_api_key",
        "createOrDeriveApiKey",
    ]
    creds = None
    for method_name in derive_methods:
        fn = getattr(client, method_name, None)
        if not callable(fn):
            continue
        creds = fn()
        if creds is not None:
            break
    if creds is None:
        raise RuntimeError("No supported API credential derivation method found")

    api_key = _extract_cred_value(creds, "api_key", "apiKey", "key")
    api_secret = _extract_cred_value(creds, "api_secret", "secret")
    api_passphrase = _extract_cred_value(creds, "api_passphrase", "passphrase")
    if not api_key or not api_secret or not api_passphrase:
        raise RuntimeError("Derived credentials are incomplete")
    return {"api_key": api_key, "api_secret": api_secret, "api_passphrase": api_passphrase}


def _paper_fixed_notional_value() -> float:
    raw = os.getenv("PS_PAPER_FIXED_NOTIONAL", os.getenv("PAPER_FIXED_NOTIONAL", "10.0"))
    try:
        value = float(raw)
    except Exception:
        return 0.0
    return value if value > 0 else 0.0


def resolve_runtime_profile(settings: Any | None = None) -> str:
    raw = str(getattr(settings, "runtime_profile", "") or "").strip()
    if raw:
        return normalize_profile(raw)
    profile, _source = detect_profile(os.environ)
    return profile


def resolve_admin_token(settings: Any | None = None) -> str:
    return _resolve_secret(settings or object(), "admin_token")


def admin_token_configured(settings: Any | None = None) -> bool:
    return bool(resolve_admin_token(settings))


def resolve_live_secret_state(settings: Any | None = None) -> dict[str, Any]:
    st = settings or object()
    private_key = _resolve_secret(st, "private_key")
    polymarket_key = _resolve_secret(st, "polymarket_key")
    polymarket_secret = _resolve_secret(st, "polymarket_secret")
    polymarket_passphrase = _resolve_secret(st, "polymarket_passphrase")
    polymarket_api_url = _resolve_secret(st, "polymarket_api_url")
    return {
        "private_key_configured": bool(private_key),
        "polymarket_key_configured": bool(polymarket_key),
        "polymarket_secret_configured": bool(polymarket_secret),
        "polymarket_passphrase_configured": bool(polymarket_passphrase),
        "api_url_configured": bool(polymarket_api_url),
    }


def _derive_signer_address_from_private_key(private_key: str) -> str:
    pk = str(private_key or "").strip()
    if not pk:
        return ""
    try:
        from eth_account import Account

        addr = Account.from_key(pk).address
        return str(addr or "").strip()
    except Exception:
        return ""


def resolve_trading_identity(settings: Any | None = None) -> dict[str, Any]:
    st = settings or object()
    private_key = _resolve_secret(st, "private_key")
    funder = _resolve_secret(st, "polymarket_funder")
    try:
        signature_type = int(getattr(st, "polymarket_signature_type", 0) or 0)
    except Exception:
        signature_type = 0
    try:
        chain_id = int(getattr(st, "polymarket_chain_id", 137) or 137)
    except Exception:
        chain_id = 137
    signer_address = _derive_signer_address_from_private_key(private_key)
    effective_funder_address = str(funder or signer_address or "").strip()
    return {
        "signer_address": signer_address,
        "funder_address": str(funder or "").strip(),
        "effective_funder_address": effective_funder_address,
        "account_type": "EOA" if signature_type == 0 else "NON_EOA",
        "signature_type": signature_type,
        "chain_id": chain_id,
    }


def bootstrap_live_credentials(settings: Any | None = None) -> dict[str, Any]:
    st = settings or object()
    private_key = _resolve_secret(st, "private_key")
    polymarket_key = _resolve_secret(st, "polymarket_key")
    polymarket_secret = _resolve_secret(st, "polymarket_secret")
    polymarket_passphrase = _resolve_secret(st, "polymarket_passphrase")
    polymarket_api_url = _resolve_secret(st, "polymarket_api_url")
    try:
        chain_id = int(getattr(st, "polymarket_chain_id", 137) or 137)
    except Exception:
        chain_id = 137
    try:
        signature_type = int(getattr(st, "polymarket_signature_type", 0) or 0)
    except Exception:
        signature_type = 0
    funder = _resolve_secret(st, "polymarket_funder")

    missing: list[str] = []
    warnings: list[str] = []
    safe_error = ""
    mode = "none"

    if not private_key:
        missing.append("PRIVATE_KEY")
    if not polymarket_api_url:
        missing.append("POLYMARKET_API_URL")

    bundle_fields = {
        "POLYMARKET_KEY": bool(polymarket_key),
        "POLYMARKET_SECRET": bool(polymarket_secret),
        "POLYMARKET_PASSPHRASE": bool(polymarket_passphrase),
    }
    present_bundle = [k for k, v in bundle_fields.items() if v]
    full_bundle = all(bundle_fields.values())

    if signature_type != 0 and not funder:
        missing.append("POLYMARKET_FUNDER")
        safe_error = "Non-EOA signature type requires POLYMARKET_FUNDER"

    if full_bundle and not safe_error:
        mode = "api_key_bundle"
    elif present_bundle and not safe_error:
        mode = "bundle_incomplete"
        for field_name, is_set in bundle_fields.items():
            if not is_set:
                missing.append(field_name)
        if not safe_error:
            safe_error = "Incomplete API key bundle; provide POLYMARKET_KEY, POLYMARKET_SECRET, POLYMARKET_PASSPHRASE"
    elif not safe_error:
        mode = "derived_sdk"

    has_static_bundle = mode == "api_key_bundle"
    cache_key = _bootstrap_cache_key(
        private_key=private_key,
        host=polymarket_api_url,
        chain_id=chain_id,
        signature_type=signature_type,
        funder=funder,
        has_static_bundle=has_static_bundle,
    )
    if cache_key in _BOOTSTRAP_CACHE:
        cached = dict(_BOOTSTRAP_CACHE[cache_key])
        if settings is not None:
            setattr(settings, "_live_api_creds", _BOOTSTRAP_CREDS.get(cache_key))
        return cached

    if mode == "api_key_bundle":
        _BOOTSTRAP_CREDS[cache_key] = {
            "api_key": polymarket_key,
            "api_secret": polymarket_secret,
            "api_passphrase": polymarket_passphrase,
        }
    elif mode == "derived_sdk" and not safe_error and not missing:
        try:
            derived = _derive_api_credentials_via_sdk(
                host=polymarket_api_url,
                private_key=private_key,
                chain_id=chain_id,
                signature_type=signature_type,
                funder=funder,
            )
            _BOOTSTRAP_CREDS[cache_key] = derived
            mode = "derived_sdk"
        except ImportError:
            missing.append("PY_CLOB_CLIENT")
            safe_error = "py-clob-client is not installed"
        except Exception as e:
            safe_error = f"SDK credential derivation failed: {type(e).__name__}"

    success = (
        len(missing) == 0
        and not safe_error
        and cache_key in _BOOTSTRAP_CREDS
        and mode in {"api_key_bundle", "derived_sdk"}
    )

    if settings is not None:
        setattr(settings, "_live_api_creds", _BOOTSTRAP_CREDS.get(cache_key))

    return {
        "attempted": True,
        "success": success,
        "mode": mode,
        "missing": missing,
        "warnings": warnings,
        "safe_error": safe_error,
        "account_type": "EOA" if signature_type == 0 else "NON_EOA",
        "signature_type": signature_type,
        "chain_id": chain_id,
        "funder_configured": bool(funder),
        "private_key_configured": bool(private_key),
        "polymarket_key_configured": bool(polymarket_key),
        "polymarket_secret_configured": bool(polymarket_secret),
        "polymarket_passphrase_configured": bool(polymarket_passphrase),
        "api_url_configured": bool(polymarket_api_url),
    }
    _BOOTSTRAP_CACHE[cache_key] = dict(result)
    return result


def validate_runtime_settings(
    settings: Any,
    *,
    execution_mode_raw: str | None = None,
    paper_fixed_notional: float = 0.0,
) -> dict[str, Any]:
    profile = resolve_runtime_profile(settings)
    mode_raw = str(execution_mode_raw or getattr(settings, "execution_mode", "paper") or "paper").strip().lower()
    execution_mode = "live_stage0" if mode_raw == "live_stage0" else "paper"
    secrets = resolve_live_secret_state(settings)
    trading_identity = resolve_trading_identity(settings)
    credential_bootstrap = bootstrap_live_credentials(settings)
    admin_configured = admin_token_configured(settings)

    warnings: list[str] = []
    errors: list[str] = []

    enable_execution = bool(getattr(settings, "enable_execution", False))
    live_dry_run = bool(getattr(settings, "live_dry_run", True))
    live_max_notional = float(getattr(settings, "live_max_notional", 0.0) or 0.0)
    live_max_orders_per_day = int(getattr(settings, "live_max_orders_per_day", 0) or 0)
    risk_cfg = getattr(settings, "risk", None)
    max_total_notional = float(getattr(risk_cfg, "max_notional_total", 0.0) or 0.0)
    paper_fixed_notional_v = float(paper_fixed_notional or 0.0)

    if profile in {"stage", "live"} and not admin_configured:
        warnings.append("ADMIN_TOKEN missing for stage/live profile")

    if execution_mode == "live_stage0" and profile != "live":
        warnings.append("LIVE_STAGE0 active while APP_ENV is not live")
    if profile == "live" and execution_mode != "live_stage0":
        warnings.append("APP_ENV=live but EXECUTION_MODE is not LIVE_STAGE0")

    if execution_mode == "live_stage0":
        if not admin_configured:
            errors.append("ADMIN_TOKEN is required for LIVE_STAGE0")
        if not enable_execution:
            errors.append("ENABLE_EXECUTION must be enabled for LIVE_STAGE0")
        if not secrets["private_key_configured"]:
            errors.append("PRIVATE_KEY is required for LIVE_STAGE0")
        if not secrets["api_url_configured"]:
            errors.append("POLYMARKET_API_URL is required for LIVE_STAGE0")
        if not bool(credential_bootstrap.get("success")):
            errors.append("LIVE_CREDENTIAL_BOOTSTRAP_FAILED")
        if live_dry_run:
            errors.append("LIVE_DRY_RUN must be false for LIVE_STAGE0")
        if live_max_notional <= 0:
            errors.append("LIVE_MAX_NOTIONAL must be > 0 for LIVE_STAGE0")
        if live_max_orders_per_day <= 0:
            errors.append("LIVE_MAX_ORDERS_PER_DAY must be > 0 for LIVE_STAGE0")
        if max_total_notional <= 0:
            errors.append("RISK_MAX_NOTIONAL_TOTAL must be > 0 for LIVE_STAGE0")
        if paper_fixed_notional_v <= 0:
            errors.append("PAPER_FIXED_NOTIONAL must be > 0 for LIVE_STAGE0")

    if live_max_notional > 0 and max_total_notional > 0 and live_max_notional > max_total_notional:
        warnings.append("LIVE_MAX_NOTIONAL exceeds RISK_MAX_NOTIONAL_TOTAL")

    live_missing: list[str] = []
    if execution_mode != "live_stage0":
        live_missing.append("EXECUTION_MODE_NOT_LIVE_STAGE0")
    if not enable_execution:
        live_missing.append("ENABLE_EXECUTION")
    if not secrets["private_key_configured"]:
        live_missing.append("PRIVATE_KEY")
    if not secrets["api_url_configured"]:
        live_missing.append("POLYMARKET_API_URL")
    for item in credential_bootstrap.get("missing", []) or []:
        if item not in live_missing:
            live_missing.append(item)
    if live_dry_run:
        live_missing.append("LIVE_DRY_RUN_DISABLED_REQUIRED")
    if live_max_notional <= 0.0:
        live_missing.append("LIVE_MAX_NOTIONAL")
    if live_max_orders_per_day <= 0:
        live_missing.append("LIVE_MAX_ORDERS_PER_DAY")
    if max_total_notional <= 0.0:
        live_missing.append("RISK_MAX_NOTIONAL_TOTAL")
    if paper_fixed_notional_v <= 0.0:
        live_missing.append("PAPER_FIXED_NOTIONAL")

    executor_buildable = bool(
        execution_mode == "live_stage0"
        and enable_execution
        and bool(credential_bootstrap.get("success"))
        and not live_dry_run
        and live_max_notional > 0.0
        and live_max_orders_per_day > 0
        and max_total_notional > 0.0
        and paper_fixed_notional_v > 0.0
    )

    return {
        "ok": len(errors) == 0,
        "profile": profile,
        "execution_mode": execution_mode,
        "warnings": warnings,
        "errors": errors,
        "admin_token_configured": admin_configured,
        "live_requirements": {
            "execution_mode_live_stage0": execution_mode == "live_stage0",
            "execution_enabled": enable_execution,
            "dry_run": live_dry_run,
            "executor_buildable": executor_buildable,
            "credential_bootstrap_attempted": bool(credential_bootstrap.get("attempted")),
            "credential_bootstrap_success": bool(credential_bootstrap.get("success")),
            "credential_bootstrap_mode": str(credential_bootstrap.get("mode") or "none"),
            "credential_bootstrap_error": str(credential_bootstrap.get("safe_error") or ""),
            "credential_account_type": str(credential_bootstrap.get("account_type") or "EOA"),
            "credential_signature_type": int(credential_bootstrap.get("signature_type", 0) or 0),
            "credential_chain_id": int(credential_bootstrap.get("chain_id", 137) or 137),
            "credential_funder_configured": bool(credential_bootstrap.get("funder_configured")),
            **secrets,
        },
        "live_credential_bootstrap": credential_bootstrap,
        "trading_identity": trading_identity,
        "live_missing": live_missing,
        "stage0_limits": {
            "max_notional_per_order": live_max_notional,
            "max_total_notional": max_total_notional,
            "paper_fixed_notional": paper_fixed_notional_v,
        },
    }


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
        settings = RuntimeSettings(
            _config=config,
            mode=config.mode,
            runtime_profile=resolve_runtime_profile(config),
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
            admin_token=_resolve_secret(config, "admin_token"),
            private_key=_resolve_secret(config, "private_key"),
            polymarket_key=_resolve_secret(config, "polymarket_key"),
            polymarket_secret=_resolve_secret(config, "polymarket_secret"),
            polymarket_passphrase=_resolve_secret(config, "polymarket_passphrase"),
            polymarket_api_url=_resolve_secret(config, "polymarket_api_url"),
            polymarket_chain_id=int(getattr(config, "polymarket_chain_id", 137) or 137),
            polymarket_signature_type=int(getattr(config, "polymarket_signature_type", 0) or 0),
            polymarket_funder=_resolve_secret(config, "polymarket_funder"),
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
        settings.startup_validation = validate_runtime_settings(
            settings,
            paper_fixed_notional=_paper_fixed_notional_value(),
        )
        return settings

    settings = RuntimeSettings(
        _config=config,
        mode=config.mode,
        runtime_profile=resolve_runtime_profile(config),
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
        admin_token=_resolve_secret(config, "admin_token"),
        private_key=_resolve_secret(config, "private_key"),
        polymarket_key=_resolve_secret(config, "polymarket_key"),
        polymarket_secret=_resolve_secret(config, "polymarket_secret"),
        polymarket_passphrase=_resolve_secret(config, "polymarket_passphrase"),
        polymarket_api_url=_resolve_secret(config, "polymarket_api_url"),
        polymarket_chain_id=int(getattr(config, "polymarket_chain_id", 137) or 137),
        polymarket_signature_type=int(getattr(config, "polymarket_signature_type", 0) or 0),
        polymarket_funder=_resolve_secret(config, "polymarket_funder"),
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
    settings.startup_validation = validate_runtime_settings(
        settings,
        paper_fixed_notional=_paper_fixed_notional_value(),
    )
    return settings
