from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import SimpleNamespace

from dispatcher.events import Timer
from dispatcher.loop import (
    DECISION_MODE_FULL,
    DECISION_MODE_HALTED,
    DECISION_MODE_SAFE,
    MainLoop,
)


class _DecisionEngineStub:
    def __init__(self) -> None:
        self.calls = 0

    def reconcile(self, _run_id: str) -> int:
        self.calls += 1
        return 1


def _mk_loop(overall: str) -> MainLoop:
    loop = MainLoop.__new__(MainLoop)
    loop.settings = SimpleNamespace(enable_agents=False)
    loop._compute_iter_freshness = lambda: {"state": {"overall": overall}}
    loop._iter_reconcile_diag = {
        "scheduled": 0,
        "allowed": 0,
        "skip_reason": "NOT_SCHEDULED",
        "decision_mode": DECISION_MODE_HALTED,
        "open_blocked_by_freshness": 0,
    }
    loop._iter_stage_ms = {"reconcile": 0.0}
    loop.decision_engine = _DecisionEngineStub()
    loop.run_id = "run-test"
    loop.repo = object()
    loop._ctx = lambda _now: None
    loop._run_slow_agents = lambda _ctx: None
    loop._events = []
    loop._queue_event = lambda **kwargs: loop._events.append(kwargs)
    return loop


def test_warn_mode_blocks_open_but_allows_hold() -> None:
    out_open, blocked_open = MainLoop._apply_paper_action_freshness_gate(
        {"paper_action": "OPEN", "paper_reason": "TOP_SCOUT_CANDIDATE", "last": "OPEN/TOP_SCOUT_CANDIDATE"},
        DECISION_MODE_SAFE,
    )
    out_hold, blocked_hold = MainLoop._apply_paper_action_freshness_gate(
        {"paper_action": "HOLD", "paper_reason": "NO_CANDIDATES", "last": "HOLD/NO_CANDIDATES"},
        DECISION_MODE_SAFE,
    )

    assert blocked_open == 1
    assert out_open["paper_action"] == "HOLD"
    assert out_open["paper_reason"] == "FRESHNESS_WARN_OPEN_BLOCKED"
    assert out_open["freshness_reason"] == "FRESHNESS_WARN_OPEN_BLOCKED"
    assert blocked_hold == 0
    assert out_hold["paper_action"] == "HOLD"
    assert out_hold["paper_reason"] == "NO_CANDIDATES"
    assert out_hold["freshness_reason"] == "NONE"


def test_stop_mode_skips_decision_execution(monkeypatch, caplog) -> None:
    loop = _mk_loop("STOP")
    called = {"paper": 0}

    def _paper_stub(_repo, _run_id):
        called["paper"] += 1
        return 0

    monkeypatch.setattr("dispatcher.loop.reconcile_paper", _paper_stub)
    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert loop.decision_engine.calls == 0
    assert called["paper"] == 0
    assert loop._iter_reconcile_diag["allowed"] == 0
    assert loop._iter_reconcile_diag["skip_reason"] == "FRESHNESS_STOP"
    assert loop._iter_reconcile_diag["decision_mode"] == DECISION_MODE_HALTED
    assert any("CASE_LIFECYCLE_SKIP_SUMMARY" in r.getMessage() for r in caplog.records)
    assert any("freshness_reason=FRESHNESS_STOP_HALTED" in r.getMessage() for r in caplog.records)


def test_ok_mode_reconcile_unchanged(monkeypatch) -> None:
    loop = _mk_loop("OK")
    called = {"paper": 0}

    def _paper_stub(_repo, _run_id):
        called["paper"] += 1
        return 0

    monkeypatch.setattr("dispatcher.loop.reconcile_paper", _paper_stub)
    loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert loop.decision_engine.calls == 1
    assert called["paper"] == 1
    assert loop._iter_reconcile_diag["allowed"] == 1
    assert loop._iter_reconcile_diag["skip_reason"] == "NONE"
    assert loop._iter_reconcile_diag["decision_mode"] == DECISION_MODE_FULL


def test_warn_mode_allows_reconcile_execution(monkeypatch) -> None:
    loop = _mk_loop("WARN")
    called = {"paper": 0}

    def _paper_stub(_repo, _run_id):
        called["paper"] += 1
        return 0

    monkeypatch.setattr("dispatcher.loop.reconcile_paper", _paper_stub)
    loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert loop.decision_engine.calls == 1
    assert called["paper"] == 1
    assert loop._iter_reconcile_diag["allowed"] == 1
    assert loop._iter_reconcile_diag["skip_reason"] == "NONE"
    assert loop._iter_reconcile_diag["decision_mode"] == DECISION_MODE_SAFE
