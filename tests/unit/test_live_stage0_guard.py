from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app.main import build_executor
from execution.polymarket_executor import ExecutorPolymarketCLOB


def test_build_executor_defaults_to_paper() -> None:
    settings = SimpleNamespace(execution_mode="paper")
    assert build_executor(settings) is None


def test_live_executor_rejects_without_live_stage0(monkeypatch) -> None:
    runtime = SimpleNamespace(
        execution_mode="paper",
        live_max_notional=10.0,
        live_max_orders_per_day=1,
        live_dry_run=False,
    )
    monkeypatch.setattr("execution.polymarket_executor.load_runtime_config", lambda: (None, runtime))
    monkeypatch.setenv("POLYMARKET_KEY", "k")
    monkeypatch.setenv("POLYMARKET_SECRET", "s")
    monkeypatch.setenv("POLYMARKET_PASSPHRASE", "pp")
    monkeypatch.setenv("PRIVATE_KEY", "p")
    monkeypatch.setenv("POLYMARKET_API_URL", "https://api.example")

    ex = ExecutorPolymarketCLOB()
    with pytest.raises(RuntimeError, match="LIVE_STAGE0"):
        ex.place_order(market_id="m1", outcome="YES", side="BUY", qty=1.0, limit_price=0.5)


def test_live_stage0_place_order_success(monkeypatch, caplog) -> None:
    runtime = SimpleNamespace(
        execution_mode="live_stage0",
        live_max_notional=10.0,
        live_max_orders_per_day=2,
        live_dry_run=False,
        polymarket_api_url="https://api.example",
        polymarket_chain_id=137,
        polymarket_signature_type=0,
        polymarket_funder="0xFunder",
        private_key="pk",
    )
    runtime._live_api_creds = {
        "api_key": "api-key",
        "api_secret": "api-secret",
        "api_passphrase": "api-passphrase",
    }
    monkeypatch.setattr("execution.polymarket_executor.load_runtime_config", lambda: (None, runtime))
    monkeypatch.setattr(
        "execution.polymarket_executor.bootstrap_live_credentials",
        lambda _runtime: {"success": True, "safe_error": "", "missing": []},
    )

    class _Client:
        def create_and_post_order(self, order):  # noqa: ANN001
            assert order.token_id == "token-yes-1"
            assert order.side == "BUY"
            assert order.size == 1.0
            assert order.price == 0.5
            return {"orderID": "ord-123", "status": "live"}

    monkeypatch.setattr("execution.polymarket_executor.ExecutorPolymarketCLOB._build_trading_client", lambda self: _Client())

    ex = ExecutorPolymarketCLOB()
    with caplog.at_level(logging.INFO, logger="execution.polymarket_executor"):
        order_id = ex.place_order(market_id="token-yes-1", outcome="YES", side="BUY", qty=1.0, limit_price=0.5)
    assert order_id == "ord-123"
    assert ex._orders_today == 1
    assert any("LIVE_ORDER_SUBMIT_ATTEMPT" in r.getMessage() for r in caplog.records)
    assert any("effective_funder_address=0xFunder" in r.getMessage() for r in caplog.records)
    assert any("signer_address=" in r.getMessage() for r in caplog.records)
    assert any("LIVE_ORDER_SUBMIT_SUCCESS" in r.getMessage() for r in caplog.records)


def test_live_stage0_human_limit_ttl_triggers_cancel(monkeypatch, caplog) -> None:
    runtime = SimpleNamespace(
        execution_mode="live_stage0",
        live_max_notional=10.0,
        live_max_orders_per_day=2,
        live_dry_run=False,
        polymarket_api_url="https://api.example",
        polymarket_chain_id=137,
        polymarket_signature_type=0,
        polymarket_funder="0xFunder",
        private_key="pk",
    )
    runtime._live_api_creds = {
        "api_key": "api-key",
        "api_secret": "api-secret",
        "api_passphrase": "api-passphrase",
    }
    monkeypatch.setattr("execution.polymarket_executor.load_runtime_config", lambda: (None, runtime))
    monkeypatch.setattr(
        "execution.polymarket_executor.bootstrap_live_credentials",
        lambda _runtime: {"success": True, "safe_error": "", "missing": []},
    )
    monkeypatch.setattr("execution.polymarket_executor.time.sleep", lambda _ttl: None)

    class _ImmediateThread:
        def __init__(self, *, target, args, name, daemon):  # noqa: ANN001
            self._target = target
            self._args = args

        def start(self) -> None:
            self._target(*self._args)

    monkeypatch.setattr("execution.polymarket_executor.threading.Thread", _ImmediateThread)

    class _Client:
        def __init__(self) -> None:
            self.cancelled = []

        def create_and_post_order(self, order):  # noqa: ANN001
            return {"orderID": "ord-123", "status": "live"}

        def get_order(self, order_id):  # noqa: ANN001
            return {"orderID": order_id, "status": "open"}

        def cancel_order(self, order_id):  # noqa: ANN001
            self.cancelled.append(order_id)
            return {"orderID": order_id, "status": "cancelled"}

    client = _Client()
    monkeypatch.setattr("execution.polymarket_executor.ExecutorPolymarketCLOB._build_trading_client", lambda self: client)

    ex = ExecutorPolymarketCLOB()
    with caplog.at_level(logging.INFO, logger="execution.polymarket_executor"):
        order_id = ex.place_order(
            market_id="token-yes-1",
            outcome="YES",
            side="BUY",
            qty=6.0,
            limit_price=0.5,
            ttl_seconds=5.0,
            execution_style="human_limit",
            metadata={"market_id": "1001", "token_id": "token-yes-1", "single_leg_smoke_mode": 1},
        )

    assert order_id == "ord-123"
    assert client.cancelled == ["ord-123"]
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "HUMAN_ORDER_PLACE_ATTEMPT" in payload
    assert "HUMAN_ORDER_PLACE_OK" in payload
    assert "HUMAN_ORDER_TTL_EXPIRED" in payload
    assert "HUMAN_ORDER_CANCEL_ATTEMPT" in payload
    assert "HUMAN_ORDER_CANCEL_OK" in payload


def test_live_stage0_place_order_submission_failure_is_safe(monkeypatch, caplog) -> None:
    secret_value = "VERY_SECRET_API_VALUE"
    runtime = SimpleNamespace(
        execution_mode="live_stage0",
        live_max_notional=10.0,
        live_max_orders_per_day=2,
        live_dry_run=False,
        polymarket_api_url="https://api.example",
        polymarket_chain_id=137,
        polymarket_signature_type=0,
        polymarket_funder="",
        private_key="pk",
    )
    runtime._live_api_creds = {
        "api_key": secret_value,
        "api_secret": "api-secret",
        "api_passphrase": "api-passphrase",
    }
    monkeypatch.setattr("execution.polymarket_executor.load_runtime_config", lambda: (None, runtime))
    monkeypatch.setattr(
        "execution.polymarket_executor.bootstrap_live_credentials",
        lambda _runtime: {"success": True, "safe_error": "", "missing": []},
    )

    class _Client:
        def create_and_post_order(self, _order):  # noqa: ANN001
            raise RuntimeError(f"upstream failed api_key={secret_value}")

    monkeypatch.setattr("execution.polymarket_executor.ExecutorPolymarketCLOB._build_trading_client", lambda self: _Client())

    ex = ExecutorPolymarketCLOB()
    with caplog.at_level(logging.INFO, logger="execution.polymarket_executor"):
        with pytest.raises(RuntimeError, match="Live order submission failed: RuntimeError"):
            ex.place_order(market_id="token-yes-1", outcome="YES", side="BUY", qty=1.0, limit_price=0.5)
    assert ex._orders_today == 0
    assert any("LIVE_ORDER_SUBMIT_FAILED" in r.getMessage() for r in caplog.records)
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert secret_value not in payload


def test_live_stage0_place_order_surfaces_polyapi_details_safely(monkeypatch, caplog) -> None:
    secret_value = "SUPER_SECRET_TOKEN"
    runtime = SimpleNamespace(
        execution_mode="live_stage0",
        live_max_notional=10.0,
        live_max_orders_per_day=2,
        live_dry_run=False,
        polymarket_api_url="https://api.example",
        polymarket_chain_id=137,
        polymarket_signature_type=0,
        polymarket_funder="",
        private_key="pk",
    )
    runtime._live_api_creds = {
        "api_key": secret_value,
        "api_secret": "api-secret",
        "api_passphrase": "api-passphrase",
    }
    monkeypatch.setattr("execution.polymarket_executor.load_runtime_config", lambda: (None, runtime))
    monkeypatch.setattr(
        "execution.polymarket_executor.bootstrap_live_credentials",
        lambda _runtime: {"success": True, "safe_error": "", "missing": []},
    )

    class PolyApiException(Exception):
        def __init__(self):
            super().__init__(f"Order rejected api_key={secret_value}")
            self.status_code = 400
            self.body = f'{{"error":"insufficient liquidity","api_key":"{secret_value}"}}'

    class _Client:
        def create_and_post_order(self, _order):  # noqa: ANN001
            raise PolyApiException()

    monkeypatch.setattr("execution.polymarket_executor.ExecutorPolymarketCLOB._build_trading_client", lambda self: _Client())

    ex = ExecutorPolymarketCLOB()
    with caplog.at_level(logging.INFO, logger="execution.polymarket_executor"):
        with pytest.raises(RuntimeError) as ei:
            ex.place_order(market_id="token-yes-1", outcome="YES", side="BUY", qty=1.0, limit_price=0.5)

    err_msg = str(ei.value)
    assert "PolyApiException" in err_msg
    assert "status_code=400" in err_msg
    assert "insufficient liquidity" in err_msg
    assert secret_value not in err_msg
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "LIVE_ORDER_SUBMIT_FAILED" in payload
    assert "status_code=400" in payload
    assert "insufficient liquidity" in payload
    assert secret_value not in payload


@pytest.mark.parametrize(
    ("execution_mode", "live_dry_run", "bootstrap_success", "expected"),
    [
        ("paper", False, True, "LIVE_STAGE0"),
        ("live_stage0", True, True, "dry-run"),
        ("live_stage0", False, False, "bootstrap failed"),
    ],
)
def test_live_stage0_place_order_gating(monkeypatch, execution_mode, live_dry_run, bootstrap_success, expected) -> None:
    runtime = SimpleNamespace(
        execution_mode=execution_mode,
        live_max_notional=10.0,
        live_max_orders_per_day=2,
        live_dry_run=live_dry_run,
        polymarket_api_url="https://api.example",
        polymarket_chain_id=137,
        polymarket_signature_type=0,
        polymarket_funder="",
        private_key="pk",
    )
    runtime._live_api_creds = {
        "api_key": "api-key",
        "api_secret": "api-secret",
        "api_passphrase": "api-passphrase",
    }
    monkeypatch.setattr("execution.polymarket_executor.load_runtime_config", lambda: (None, runtime))
    monkeypatch.setattr(
        "execution.polymarket_executor.bootstrap_live_credentials",
        lambda _runtime: {
            "success": bootstrap_success,
            "safe_error": "sdk failure" if not bootstrap_success else "",
            "missing": ["PRIVATE_KEY"] if not bootstrap_success else [],
        },
    )

    ex = ExecutorPolymarketCLOB()
    with pytest.raises(RuntimeError, match=expected):
        ex.place_order(market_id="token-yes-1", outcome="YES", side="BUY", qty=1.0, limit_price=0.5)
