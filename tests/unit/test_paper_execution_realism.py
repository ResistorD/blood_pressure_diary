from __future__ import annotations

from typing import Any, Dict, List

from execution.paper_executor import execute_pending_paper


class _RepoStub:
    def __init__(self, *, quote: Dict[str, Any], cmd: str = "BUY") -> None:
        self.quote = quote
        self.cmd = cmd
        self.buy_calls: List[Dict[str, Any]] = []
        self.close_calls: List[Dict[str, Any]] = []
        self.executed: List[str] = []
        self.failed: List[Dict[str, str]] = []

    def list_pending_paper_commands(self, limit: int = 200):
        return [
            {
                "command_id": "c1",
                "created_at": "2026-03-07T00:00:00+00:00",
                "market_id": "m1",
                "outcome": "YES",
                "cmd": self.cmd,
                "qty": 1.0,
                "price_mode": "MID",
                "source_decision_id": "d1",
            }
        ]

    def get_latest_snapshots(self, market_id: str):
        return {"YES": dict(self.quote)}

    def paper_buy(self, **kwargs):
        self.buy_calls.append(kwargs)

    def paper_close(self, **kwargs):
        self.close_calls.append(kwargs)
        return {"ok": True}

    def mark_paper_command_executed(self, command_id: str, executed_at: str):
        self.executed.append(command_id)

    def mark_paper_command_failed(self, command_id: str, executed_at: str, error: str):
        self.failed.append({"command_id": command_id, "error": str(error)})


def test_open_uses_ask_when_available(monkeypatch) -> None:
    monkeypatch.setenv("PS_PAPER_FIXED_NOTIONAL", "10")
    repo = _RepoStub(quote={"ask": 0.62, "bid": 0.58, "mid": 0.60}, cmd="BUY")

    n = execute_pending_paper(repo, run_id="r1", limit=10)

    assert n == 1
    assert repo.buy_calls
    assert float(repo.buy_calls[0]["price"]) == 0.62
    assert "fill_side_source=ASK" in str(repo.buy_calls[0]["note"])


def test_close_uses_bid_when_available() -> None:
    repo = _RepoStub(quote={"ask": 0.62, "bid": 0.58, "mid": 0.60}, cmd="CLOSE")

    n = execute_pending_paper(repo, run_id="r1", limit=10)

    assert n == 1
    assert repo.close_calls
    assert float(repo.close_calls[0]["price"]) == 0.58
    assert "fill_side_source=BID" in str(repo.close_calls[0]["note"])


def test_fallback_to_mid_when_side_price_missing(monkeypatch) -> None:
    monkeypatch.setenv("PS_PAPER_FIXED_NOTIONAL", "10")
    repo = _RepoStub(quote={"ask": None, "bid": 0.58, "mid": 0.60}, cmd="BUY")

    n = execute_pending_paper(repo, run_id="r1", limit=10)

    assert n == 1
    assert float(repo.buy_calls[0]["price"]) == 0.60
    assert "fill_side_source=MID_FALLBACK" in str(repo.buy_calls[0]["note"])


def test_fixed_notional_sizing_from_fill_price(monkeypatch) -> None:
    monkeypatch.setenv("PS_PAPER_FIXED_NOTIONAL", "12")
    repo = _RepoStub(quote={"ask": 0.60, "bid": 0.58, "mid": 0.59}, cmd="BUY")

    n = execute_pending_paper(repo, run_id="r1", limit=10)

    assert n == 1
    assert float(repo.buy_calls[0]["qty"]) == 20.0  # 12 / 0.60


def test_invalid_fill_price_is_handled_safely(monkeypatch) -> None:
    monkeypatch.setenv("PS_PAPER_FIXED_NOTIONAL", "12")
    repo = _RepoStub(quote={"ask": 0.0, "bid": 0.0, "mid": 0.0}, cmd="BUY")

    n = execute_pending_paper(repo, run_id="r1", limit=10)

    assert n == 1  # command processed with deterministic fallback
    assert repo.buy_calls
    assert float(repo.buy_calls[0]["price"]) == 0.50
    assert float(repo.buy_calls[0]["qty"]) == 24.0  # 12 / 0.50
