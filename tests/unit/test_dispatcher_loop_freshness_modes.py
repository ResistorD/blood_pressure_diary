from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

from dispatcher.events import Timer
from dispatcher.loop import (
    DECISION_MODE_FULL,
    DECISION_MODE_HALTED,
    DECISION_MODE_SAFE,
    MainLoop,
)
from domain.enums import SignalKind
from domain.models import Signal


class _DecisionEngineStub:
    def __init__(self) -> None:
        self.calls = 0
        self._risk_gate = None

    def reconcile(self, _run_id: str) -> int:
        self.calls += 1
        return 1


def _mk_loop(overall: str) -> MainLoop:
    loop = MainLoop.__new__(MainLoop)
    loop.settings = SimpleNamespace(
        enable_agents=False,
        execution_mode="paper",
        live_exec_style="human_limit",
        paper_fixed_notional=3.0,
        live_max_notional=10.0,
        risk=SimpleNamespace(max_notional_total=100.0),
    )
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
    loop.repo = SimpleNamespace(get_latest_orderbook_snapshot=lambda _market_id: None)
    loop._ctx = lambda _now: None
    loop._run_slow_agents = lambda _ctx: None
    loop._events = []
    loop._queue_event = lambda **kwargs: loop._events.append(kwargs)
    loop._iter_pipe = {"paper_action": "HOLD"}
    loop._live_stage0_last_submit_signature = ""
    loop._live_stage0_untradeable_suppression = {}
    return loop


class _ExecutorStub:
    def __init__(self) -> None:
        self.calls = []
        self.mm_probe_stats = {"placed": 0, "filled": 0, "canceled": 0}

    def place_order(
        self,
        market_id: str,
        outcome: str,
        side: str,
        qty: float,
        limit_price: float,
        **kwargs,
    ) -> str:
        self.calls.append(
            {
                "market_id": market_id,
                "outcome": outcome,
                "side": side,
                "qty": float(qty),
                "limit_price": float(limit_price),
                "kwargs": kwargs,
            }
        )
        if str(((kwargs or {}).get("metadata") or {}).get("strategy") or "").upper() == "MM":
            self.mm_probe_stats["placed"] = int(self.mm_probe_stats.get("placed", 0) or 0) + 1
        return "ord-1"

    def get_mm_probe_stats(self) -> dict[str, int]:
        return dict(self.mm_probe_stats)


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


def test_live_stage0_pipeline_open_triggers_submit(monkeypatch) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "direct"
    loop.settings.paper_fixed_notional = 1.0
    loop.executor = _ExecutorStub()
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|1001",
    }
    loop._latest_snapshots_by_outcome = lambda _market_id: {"YES": {"ask": 0.4, "mid": 0.39}}
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setattr("dispatcher.loop.reconcile_paper", lambda _repo, _run_id: 0)

    loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert loop.decision_engine.calls == 1
    assert len(loop.executor.calls) == 1
    call = loop.executor.calls[0]
    assert call["market_id"] == "tok-1001-YES"
    assert call["outcome"] == "YES"
    assert call["side"] == "BUY"
    assert call["qty"] > 0.0
    assert call["limit_price"] == 0.4


def test_live_stage0_price_lookup_is_case_insensitive_for_outcome(monkeypatch) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "direct"
    loop.settings.paper_fixed_notional = 1.0
    loop.executor = _ExecutorStub()
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|1001",
    }
    loop._latest_snapshots_by_outcome = lambda _market_id: {"Yes": {"ask": 0.35, "mid": 0.34}}
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setattr("dispatcher.loop.reconcile_paper", lambda _repo, _run_id: 0)

    loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert len(loop.executor.calls) == 1
    assert loop.executor.calls[0]["limit_price"] == 0.35


def test_live_stage0_qty_respects_min_submit_notional_floor(monkeypatch) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "direct"
    loop.settings.paper_fixed_notional = 1.0
    loop.executor = _ExecutorStub()
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|1001",
    }
    loop._latest_snapshots_by_outcome = lambda _market_id: {"YES": {"ask": 0.999, "mid": 0.999}}
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setenv("PS_LIVE_STAGE0_MIN_SUBMIT_NOTIONAL", "1.05")
    monkeypatch.setattr("dispatcher.loop.reconcile_paper", lambda _repo, _run_id: 0)

    loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert len(loop.executor.calls) == 1
    call = loop.executor.calls[0]
    assert (call["qty"] * call["limit_price"]) >= 1.05


def test_live_stage0_pipeline_open_dedup_suppresses_repeat(monkeypatch) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "direct"
    loop.settings.paper_fixed_notional = 1.0
    loop.executor = _ExecutorStub()
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|1001",
    }
    loop._latest_snapshots_by_outcome = lambda _market_id: {"YES": {"ask": 0.25, "mid": 0.24}}
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setattr("dispatcher.loop.reconcile_paper", lambda _repo, _run_id: 0)

    loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))
    loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert len(loop.executor.calls) == 1


def test_live_stage0_unlocks_same_opportunity_hold_before_first_submit() -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop._live_stage0_last_submit_signature = ""
    loop._iter_pipe = {"paper_action": "HOLD", "paper_reason": "SAME_OPPORTUNITY_SKIPPED"}
    loop._paper_pipeline_ctx = {
        "last_signature": "OPEN|TOP_SCOUT_CANDIDATE|1001",
        "last_consumed_scout_key": "rowid:42",
        "last_consumed_opportunity_key": "opp-1",
    }

    loop._maybe_release_stage0_candidate_suppression()

    assert loop._paper_pipeline_ctx["last_signature"] == ""
    assert loop._paper_pipeline_ctx["last_consumed_scout_key"] == ""
    assert loop._paper_pipeline_ctx["last_consumed_opportunity_key"] == ""


def test_live_stage0_does_not_unlock_after_successful_submit() -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop._live_stage0_last_submit_signature = "OPEN|TOP_SCOUT_CANDIDATE|1001"
    loop._iter_pipe = {"paper_action": "HOLD", "paper_reason": "STALE_CANDIDATE_SKIPPED"}
    loop._paper_pipeline_ctx = {
        "last_signature": "OPEN|TOP_SCOUT_CANDIDATE|1001",
        "last_consumed_scout_key": "rowid:42",
        "last_consumed_opportunity_key": "opp-1",
    }

    loop._maybe_release_stage0_candidate_suppression()

    assert loop._paper_pipeline_ctx["last_signature"] == "OPEN|TOP_SCOUT_CANDIDATE|1001"
    assert loop._paper_pipeline_ctx["last_consumed_scout_key"] == "rowid:42"
    assert loop._paper_pipeline_ctx["last_consumed_opportunity_key"] == "opp-1"


def test_live_stage0_human_limit_places_passive_limit_with_ttl(monkeypatch) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop.settings.paper_fixed_notional = 3.0
    loop.executor = _ExecutorStub()
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|1001",
    }
    loop._latest_snapshots_by_outcome = lambda _market_id: {
        "YES": {"bid": 0.40, "ask": 0.405, "mid": 0.4025, "spread": 0.005, "liquidity": 50.0}
    }
    loop.repo = SimpleNamespace(
        get_latest_orderbook_snapshot=lambda _market_id: {
            "best_bid": 0.40,
            "best_ask": 0.405,
            "mid": 0.4025,
            "asks_json": '[{"price":0.405,"size":20},{"price":0.406,"size":20}]',
        }
    )
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setenv("PS_LIVE_HUMAN_MIN_NOTIONAL", "2.0")
    monkeypatch.setenv("PS_LIVE_HUMAN_TTL_SEC", "9")
    monkeypatch.setattr("dispatcher.loop.reconcile_paper", lambda _repo, _run_id: 0)

    loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert len(loop.executor.calls) == 1
    call = loop.executor.calls[0]
    assert call["market_id"] == "tok-1001-YES"
    assert call["limit_price"] == 0.404
    assert call["qty"] > 0.0
    assert call["kwargs"]["execution_style"] == "human_limit"
    assert call["kwargs"]["ttl_seconds"] == 9.0


def test_live_stage0_human_limit_upscales_notional_below_floor(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop.settings.paper_fixed_notional = 1.0
    loop.executor = _ExecutorStub()
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|1001",
    }
    loop._latest_snapshots_by_outcome = lambda _market_id: {
        "YES": {"bid": 0.40, "ask": 0.405, "mid": 0.4025, "spread": 0.005, "liquidity": 50.0}
    }
    loop.repo = SimpleNamespace(
        get_latest_orderbook_snapshot=lambda _market_id: {
            "best_bid": 0.40,
            "best_ask": 0.405,
            "mid": 0.4025,
            "asks_json": '[{"price":0.405,"size":20},{"price":0.406,"size":20}]',
        }
    )
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setenv("PS_LIVE_HUMAN_MIN_NOTIONAL", "2.0")
    monkeypatch.setattr("dispatcher.loop.reconcile_paper", lambda _repo, _run_id: 0)

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert len(loop.executor.calls) == 1
    call = loop.executor.calls[0]
    assert math.isclose(call["qty"] * call["limit_price"], 2.0, rel_tol=0.0, abs_tol=1e-9)
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "HUMAN_LIMIT_NOTIONAL_UPSCALED" in payload


def test_live_stage0_human_limit_skips_boundary_book_early(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop.settings.paper_fixed_notional = 3.0
    loop.executor = _ExecutorStub()
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|1001",
    }
    loop._latest_snapshots_by_outcome = lambda _market_id: {
        "YES": {"bid": 0.001, "ask": 0.999, "mid": 0.5, "spread": 0.998, "liquidity": 50.0}
    }
    loop.repo = SimpleNamespace(
        get_latest_orderbook_snapshot=lambda _market_id: {
            "best_bid": 0.001,
            "best_ask": 0.999,
            "mid": 0.5,
            "asks_json": '[{"price":0.999,"size":20}]',
        }
    )
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setattr("dispatcher.loop.reconcile_paper", lambda _repo, _run_id: 0)

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert loop.executor.calls == []
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "LIVE_STAGE0_MARKET_UNTRADEABLE" in payload
    assert "reason=BOUNDARY_BOOK" in payload
    assert "PIPE_OPEN_BRIDGE_SKIP reason=UNTRADEABLE_MARKET" in payload


def test_live_stage0_human_limit_suppresses_recent_untradeable_candidate(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop.settings.paper_fixed_notional = 3.0
    loop.executor = _ExecutorStub()
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|562003",
        "opportunity_key": "opp-562003",
    }
    loop._latest_snapshots_by_outcome = lambda _market_id: {
        "YES": {"bid": 0.001, "ask": 0.999, "mid": 0.5, "spread": 0.998, "liquidity": 50.0}
    }
    loop.repo = SimpleNamespace(
        get_latest_orderbook_snapshot=lambda _market_id: {
            "best_bid": 0.001,
            "best_ask": 0.999,
            "mid": 0.5,
            "asks_json": '[{"price":0.999,"size":20}]',
        }
    )
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    mono = iter([100.0] * 12 + [250.0] * 12)
    monkeypatch.setattr("dispatcher.loop.time.monotonic", lambda: next(mono))
    monkeypatch.setattr("dispatcher.loop.reconcile_paper", lambda _repo, _run_id: 0)

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))
        loop._handle_event(Timer(ts=datetime.now(timezone.utc), purpose="reconcile"))

    assert loop.executor.calls == []
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert payload.count("LIVE_STAGE0_MARKET_UNTRADEABLE") == 1
    assert "LIVE_STAGE0_CANDIDATE_SUPPRESSED" in payload
    assert "PIPE_OPEN_BRIDGE_SKIP reason=UNTRADEABLE_COOLDOWN" in payload
    assert "cooldown_sec=300.000" in payload


def test_live_stage0_pipe_is_downgraded_to_hold_when_untradeable_is_suppressed(monkeypatch) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|562003",
        "opportunity_key": "opp-562003",
    }
    loop._live_stage0_untradeable_suppression = {
        "opp:opp-562003": {"ts_mono": 100.0, "reason": "UNTRADEABLE_MARKET"}
    }
    monkeypatch.setattr("dispatcher.loop.time.monotonic", lambda: 150.0)

    out = loop._apply_live_stage0_untradeable_suppression_to_pipe(pipe)

    assert out["paper_action"] == "HOLD"
    assert out["paper_reason"] == "UNTRADEABLE_COOLDOWN"
    assert out["paper_source"] == "live_stage0.untradeable_cooldown"
    assert out["selected"] == 0
    assert out["open_blocked_by_untradeable_cooldown"] == 1


def test_live_stage0_falls_back_to_next_ranked_candidate_when_first_is_unusable(monkeypatch) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop.settings.paper_fixed_notional = 3.0
    loop.executor = _ExecutorStub()
    loop._latest_snapshots_by_outcome = lambda market_id: {
        "562003": {"YES": {"bid": 0.001, "ask": 0.999, "mid": 0.5, "spread": 0.998, "liquidity": 50.0}},
        "562004": {"YES": {"bid": 0.40, "ask": 0.405, "mid": 0.4025, "spread": 0.005, "liquidity": 50.0}},
    }.get(market_id, {})
    loop.repo = SimpleNamespace(
        get_latest_orderbook_snapshot=lambda market_id: {
            "562003": {"best_bid": 0.001, "best_ask": 0.999, "mid": 0.5, "asks_json": '[{"price":0.999,"size":20}]'},
            "562004": {"best_bid": 0.40, "best_ask": 0.405, "mid": 0.4025, "asks_json": '[{"price":0.405,"size":20},{"price":0.406,"size":20}]'},
        }.get(market_id)
    )
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    loop._live_stage0_ranked_candidate_pool = lambda: [
        {
            "ref_id": "562003",
            "consumed_key": "rowid:1",
            "opportunity_key": "opp-562003",
            "source": "ranked",
        },
        {
            "ref_id": "562004",
            "consumed_key": "rowid:2",
            "opportunity_key": "opp-562004",
            "source": "ranked",
        },
    ]
    pipe = {
        "cand_count": 1,
        "dec_count": 1,
        "last": "OPEN/TOP_SCOUT_CANDIDATE",
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "paper_source": "paper.test",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|562003",
        "matched_prev_signature": "",
        "selected": 1,
        "skipped_as_stale": 0,
        "consumed_key": "rowid:1",
        "opportunity_key": "opp-562003",
        "same_opportunity_as_prev": 0,
        "skipped_as_same_opportunity": 0,
        "paper_market_id": "562003",
    }

    out = loop._apply_live_stage0_candidate_fallback(pipe)
    loop._iter_pipe = out
    submitted = loop._maybe_submit_stage0_open_from_pipeline(datetime.now(timezone.utc))

    assert submitted == 1
    assert len(loop.executor.calls) == 1
    call = loop.executor.calls[0]
    assert call["market_id"] == "tok-562004-YES"
    assert call["kwargs"]["execution_style"] == "human_limit"
    assert out["paper_action"] == "OPEN"
    assert out["paper_reason"] == "TOP_SCOUT_CANDIDATE"
    assert out["paper_market_id"] == "562004"


def test_live_stage0_ranked_pool_filters_obviously_dead_candidates(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop._latest_snapshots_by_outcome = lambda market_id: {
        "562003": {"YES": {"bid": 0.001, "ask": 0.999, "mid": 0.5, "spread": 0.998, "liquidity": 50.0}},
        "562004": {"YES": {"bid": 0.40, "ask": 0.405, "mid": 0.4025, "spread": 0.005, "liquidity": 50.0}},
        "562005": {"YES": {"bid": None, "ask": None, "mid": None, "spread": None, "liquidity": 50.0}},
    }.get(market_id, {})
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"

    class _Rows:
        def __init__(self, rows):
            self._rows = rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

    class _Conn:
        def execute(self, sql, params=()):
            if "SELECT MAX(ts)" in sql:
                return _Rows([{"latest_ts": "2026-03-12T00:00:03+00:00"}])
            if "AND ts = ?" in sql:
                assert params == ("2026-03-12T00:00:03+00:00",)
                return _Rows(
                    [
                        {
                            "signal_rowid": 1,
                            "signal_ts": "2026-03-12T00:00:03+00:00",
                            "market_id": "562003",
                            "claim_json": '{"opportunity_key":"opp-562003"}',
                            "features_json": '{"similarity":0.90}',
                            "signal_origin": "signals.latest_scout_generation",
                        },
                        {
                            "signal_rowid": 2,
                            "signal_ts": "2026-03-12T00:00:03+00:00",
                            "market_id": "562004",
                            "claim_json": '{"opportunity_key":"opp-562004"}',
                            "features_json": '{"similarity":0.80}',
                            "signal_origin": "signals.latest_scout_generation",
                        },
                        {
                            "signal_rowid": 3,
                            "signal_ts": "2026-03-12T00:00:03+00:00",
                            "market_id": "562005",
                            "claim_json": '{"opportunity_key":"opp-562005"}',
                            "features_json": '{"similarity":0.70}',
                            "signal_origin": "signals.latest_scout_generation",
                        },
                    ]
                )
            raise AssertionError(sql)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    loop.repo = SimpleNamespace(
        conn=lambda: _Conn(),
        get_latest_orderbook_snapshot=lambda market_id: {
            "562003": {"best_bid": 0.001, "best_ask": 0.999, "mid": 0.5, "asks_json": '[{"price":0.999,"size":20}]'},
            "562004": {"best_bid": 0.40, "best_ask": 0.405, "mid": 0.4025, "asks_json": '[{"price":0.405,"size":20}]'},
            "562005": {"best_bid": None, "best_ask": None, "mid": None, "asks_json": "[]"},
        }.get(market_id),
    )
    monkeypatch.setenv("PS_PAPER_SCOUT_POOL_N", "10")
    monkeypatch.setenv("PS_PAPER_MIN_SIMILARITY", "0.2")

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        out = loop._live_stage0_ranked_candidate_pool()

    assert [row["ref_id"] for row in out] == ["562004"]
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert payload.count("LIVE_STAGE0_CANDIDATE_FILTERED") == 2
    assert "reason=BOUNDARY_BOOK" in payload
    assert "reason=MISSING_BOOK" in payload


def test_live_stage0_ranked_pool_uses_current_pending_scout_generation(monkeypatch) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop._latest_snapshots_by_outcome = lambda market_id: {
        "562004": {"YES": {"bid": 0.40, "ask": 0.405, "mid": 0.4025, "spread": 0.005, "liquidity": 50.0}},
        "562099": {"YES": {"bid": 0.30, "ask": 0.305, "mid": 0.3025, "spread": 0.005, "liquidity": 50.0}},
    }.get(market_id, {})
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    loop._iter_signals_buf = [
        Signal(
            signal_id=str(uuid.uuid4()),
            ts=datetime(2026, 3, 12, 0, 0, 5, tzinfo=timezone.utc),
            run_id="run-test",
            agent_id="scout.v2",
            kind=SignalKind.PAIR_ARB,
            scope_market_id="562004",
            scope_group_key="g1",
            scope_pair_key="562004::562100",
            features={"similarity": 0.81},
            claim={"opportunity_key": "opp-562004"},
            candidates=[],
            explain_short="",
            explain_long="",
        )
    ]

    class _Rows:
        def __init__(self, rows):
            self._rows = rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

    class _Conn:
        def execute(self, sql, params=()):
            if "SELECT MAX(ts)" in sql:
                return _Rows([{"latest_ts": "2026-03-12T00:00:04+00:00"}])
            if "AND ts = ?" in sql:
                assert params == ("2026-03-12T00:00:05+00:00",)
                return _Rows([])
            raise AssertionError(sql)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    loop.repo = SimpleNamespace(
        conn=lambda: _Conn(),
        get_latest_orderbook_snapshot=lambda market_id: {
            "562004": {"best_bid": 0.40, "best_ask": 0.405, "mid": 0.4025, "asks_json": '[{"price":0.405,"size":20}]'},
            "562099": {"best_bid": 0.30, "best_ask": 0.305, "mid": 0.3025, "asks_json": '[{"price":0.305,"size":20}]'},
        }.get(market_id),
    )
    monkeypatch.setenv("PS_PAPER_SCOUT_POOL_N", "10")
    monkeypatch.setenv("PS_PAPER_MIN_SIMILARITY", "0.2")

    out = loop._live_stage0_ranked_candidate_pool()

    assert [row["ref_id"] for row in out] == ["562004"]
    assert out[0]["source"] == "pending_iter_scout"


def test_live_stage0_mm_candidate_with_missing_book_is_bypassed_in_probe_mode(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop._live_stage0_current_generation_rows = lambda: [
        {
            "signal_rowid": 11,
            "signal_ts": "2026-03-12T00:00:11+00:00",
            "market_id": "562023",
            "claim_json": '{"strategy":"MM","type":"market_making","opportunity_key":"mm:562023","bid":0.40,"ask":0.46,"mid":0.43,"spread":0.06,"bid_size":12,"ask_size":8,"liquidity":8,"mm_score":0.40}',
            "features_json": '{"mm_score":0.40}',
            "signal_origin": "signals.latest_scout_generation",
        }
    ]
    loop._latest_snapshots_by_outcome = lambda _market_id: {}
    loop.repo = SimpleNamespace(get_latest_orderbook_snapshot=lambda _market_id: None)
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setenv("PS_MM_PROBE_ALLOW_UNTRADEABLE", "true")

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        out = loop._live_stage0_ranked_candidate_pool()

    assert [row["ref_id"] for row in out] == ["562023"]
    assert out[0]["mm_probe_bypass_untradeable"] == 1
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_PROBE_BYPASS_UNTRADEABLE market_id=562023" in payload
    assert "reason=MISSING_BOOK" in payload


def test_live_stage0_mm_candidate_with_missing_book_is_rejected_when_probe_disabled(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop._live_stage0_current_generation_rows = lambda: [
        {
            "signal_rowid": 12,
            "signal_ts": "2026-03-12T00:00:12+00:00",
            "market_id": "562024",
            "claim_json": '{"strategy":"MM","type":"market_making","opportunity_key":"mm:562024","bid":0.40,"ask":0.46,"mid":0.43,"spread":0.06,"bid_size":12,"ask_size":8,"liquidity":8,"mm_score":0.40}',
            "features_json": '{"mm_score":0.40}',
            "signal_origin": "signals.latest_scout_generation",
        }
    ]
    loop._latest_snapshots_by_outcome = lambda _market_id: {}
    loop.repo = SimpleNamespace(get_latest_orderbook_snapshot=lambda _market_id: None)
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.delenv("PS_MM_PROBE_ALLOW_UNTRADEABLE", raising=False)

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        out = loop._live_stage0_ranked_candidate_pool()

    assert out == []
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "LIVE_STAGE0_CANDIDATE_FILTERED" in payload
    assert "market_id=562024" in payload
    assert "reason=MISSING_BOOK" in payload


def test_live_stage0_final_open_uses_filtered_live_pool_not_raw_paper_top(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop.settings.paper_fixed_notional = 3.0
    loop.executor = _ExecutorStub()
    loop._latest_snapshots_by_outcome = lambda market_id: {
        "562003": {"YES": {"bid": 0.001, "ask": 0.999, "mid": 0.5, "spread": 0.998, "liquidity": 50.0}},
        "562004": {"YES": {"bid": 0.40, "ask": 0.405, "mid": 0.4025, "spread": 0.005, "liquidity": 50.0}},
    }.get(market_id, {})
    loop.repo = SimpleNamespace(
        get_latest_orderbook_snapshot=lambda market_id: {
            "562003": {"best_bid": 0.001, "best_ask": 0.999, "mid": 0.5, "asks_json": '[{"price":0.999,"size":20}]'},
            "562004": {"best_bid": 0.40, "best_ask": 0.405, "mid": 0.4025, "asks_json": '[{"price":0.405,"size":20},{"price":0.406,"size":20}]'},
        }.get(market_id)
    )
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    loop._live_stage0_ranked_candidate_pool = lambda: [
        {
            "ref_id": "562004",
            "consumed_key": "rowid:2",
            "opportunity_key": "opp-562004",
            "source": "ranked",
        },
    ]
    raw_pipe = {
        "cand_count": 1,
        "dec_count": 1,
        "last": "OPEN/TOP_SCOUT_CANDIDATE",
        "paper_action": "OPEN",
        "paper_reason": "TOP_SCOUT_CANDIDATE",
        "paper_source": "paper.test",
        "dedup_signature": "OPEN|TOP_SCOUT_CANDIDATE|562003",
        "matched_prev_signature": "",
        "selected": 1,
        "skipped_as_stale": 0,
        "consumed_key": "rowid:1",
        "opportunity_key": "opp-562003",
        "same_opportunity_as_prev": 0,
        "skipped_as_same_opportunity": 0,
        "paper_market_id": "562003",
    }

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        out = loop._apply_live_stage0_candidate_fallback(raw_pipe)
        loop._iter_pipe = out
        submitted = loop._maybe_submit_stage0_open_from_pipeline(datetime.now(timezone.utc))

    assert submitted == 1
    assert out["paper_action"] == "OPEN"
    assert out["paper_market_id"] == "562004"
    assert out["dedup_signature"] == "OPEN|TOP_SCOUT_CANDIDATE|562004"
    assert len(loop.executor.calls) == 1
    assert loop.executor.calls[0]["market_id"] == "tok-562004-YES"
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "LIVE_STAGE0_CANDIDATE_FALLBACK" in payload
    assert "market_id=562004" in payload


def test_open_mm_selected_path_logs_and_submits(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop.settings.paper_fixed_notional = 3.0
    loop.executor = _ExecutorStub()
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_MM_CANDIDATE",
        "paper_strategy": "MM",
        "strategy_action": "OPEN_MM",
        "dedup_signature": "OPEN|TOP_MM_CANDIDATE|562004",
        "paper_market_id": "562004",
        "mm_bid": 0.40,
        "mm_ask": 0.46,
        "mm_mid": 0.43,
        "mm_spread": 0.06,
        "mm_bid_size": 12.0,
        "mm_ask_size": 8.0,
        "mm_liquidity": 8.0,
        "mm_score": 0.48,
    }
    loop._latest_snapshots_by_outcome = lambda _market_id: {
        "YES": {"bid": 0.40, "ask": 0.46, "mid": 0.43, "spread": 0.06, "liquidity": 8.0}
    }
    loop.repo = SimpleNamespace(
        get_latest_orderbook_snapshot=lambda _market_id: {
            "best_bid": 0.40,
            "best_ask": 0.46,
            "mid": 0.43,
            "asks_json": '[{"price":0.46,"size":8}]',
        }
    )
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setattr("dispatcher.loop.reconcile_paper", lambda _repo, _run_id: 0)

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        submitted = loop._maybe_submit_stage0_open_from_pipeline(datetime.now(timezone.utc))

    assert submitted == 1
    assert len(loop.executor.calls) == 2
    assert {call["side"] for call in loop.executor.calls} == {"BUY", "SELL"}
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "OPEN_MM_SELECTED market_id=562004" in payload
    assert "MM_ORDER_PLACE market_id=562004" in payload


def test_open_mm_selected_one_sided_buy_path_and_probe_summary(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop.settings.paper_fixed_notional = 3.0
    loop.executor = _ExecutorStub()
    loop._iter_decision_diag = {
        "mm_markets_raw": 5,
        "mm_markets_eligible": 2,
        "mm_candidates_found": 1,
        "mm_decision_accepted": 1,
        "mm_orders_placed": 0,
    }
    loop._mm_probe_prev_stats = {"placed": 0, "filled": 0, "canceled": 0}
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_MM_CANDIDATE",
        "paper_strategy": "MM",
        "strategy_action": "OPEN_MM",
        "dedup_signature": "OPEN|TOP_MM_CANDIDATE|562023",
        "paper_market_id": "562023",
        "mm_bid": None,
        "mm_ask": 0.46,
        "mm_mid": 0.435,
        "mm_spread": 0.05,
        "mm_bid_size": 0.0,
        "mm_ask_size": 8.0,
        "mm_liquidity": 8.0,
        "mm_score": 0.40,
        "mm_quote_mode": "ASK_ONLY",
        "mm_post_side": "BUY",
    }
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setenv("PS_MM_MAX_SPREAD", "0.35")
    monkeypatch.setenv("PS_MM_MIN_BID", "0.001")
    monkeypatch.setenv("PS_MM_MAX_ASK", "0.999")

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        submitted = loop._maybe_submit_stage0_open_from_pipeline(datetime.now(timezone.utc))
        loop._emit_mm_probe_summary()

    assert submitted == 1
    assert len(loop.executor.calls) == 1
    assert loop.executor.calls[0]["side"] == "BUY"
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "OPEN_MM_SELECTED market_id=562023" in payload
    assert "MM_PROBE_SUMMARY raw_markets=5 eligible_markets=2 candidates=1 probe_bypass_untradeable=0 orders_attempted=1 orders_failed=0 orders_filled=0 orders_canceled=0" in payload


def test_mm_final_probe_selects_top_3_mm_candidates(caplog) -> None:
    loop = _mk_loop("OK")
    ranked = [
        {"ref_id": "m1", "strategy": "MM", "mm_score": 0.20, "mm_spread": 0.05, "mm_bid": 0.40, "mm_ask": 0.45, "mm_bid_size": 10.0, "mm_ask_size": 10.0},
        {"ref_id": "m2", "strategy": "MM", "mm_score": 0.70, "mm_spread": 0.07, "mm_bid": 0.41, "mm_ask": 0.48, "mm_bid_size": 9.0, "mm_ask_size": 8.0},
        {"ref_id": "m3", "strategy": "ARB", "score": 0.90},
        {"ref_id": "m4", "strategy": "MM", "mm_score": 0.50, "mm_spread": 0.06, "mm_bid": 0.39, "mm_ask": 0.45, "mm_bid_size": 7.0, "mm_ask_size": 7.0},
        {"ref_id": "m5", "strategy": "MM", "mm_score": 0.30, "mm_spread": 0.05, "mm_bid": 0.42, "mm_ask": 0.47, "mm_bid_size": 6.0, "mm_ask_size": 6.0},
    ]
    loop._iter_decision_diag = {}

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        selected = loop._mm_final_probe_candidates(ranked)

    assert [cand["ref_id"] for cand in selected] == ["m2", "m4", "m5"]
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert payload.count("MM_FINAL_PROBE_SELECTED") == 3


def test_mm_final_probe_decision_bypass_applies_only_when_enabled(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    loop._live_stage0_ranked_candidate_pool = lambda: [
        {
            "ref_id": "562200",
            "consumed_key": "rowid:1",
            "opportunity_key": "mm:562200",
            "source": "ranked",
            "strategy": "MM",
            "strategy_action": "OPEN_MM",
            "paper_reason": "TOP_MM_CANDIDATE",
            "mm_bid": 0.40,
            "mm_ask": 0.46,
            "mm_mid": 0.43,
            "mm_spread": 0.06,
            "mm_bid_size": 12.0,
            "mm_ask_size": 8.0,
            "mm_liquidity": 8.0,
            "mm_score": 0.48,
        }
    ]
    raw_pipe = {
        "paper_action": "HOLD",
        "paper_reason": "NO_DECISION",
        "consumed_key": "rowid:1",
        "opportunity_key": "mm:562200",
        "paper_market_id": "562200",
    }

    monkeypatch.delenv("PS_MM_FINAL_PROBE", raising=False)
    out_disabled = loop._apply_live_stage0_candidate_fallback(raw_pipe)
    assert out_disabled["paper_action"] == "HOLD"

    monkeypatch.setenv("PS_MM_FINAL_PROBE", "true")
    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        out_enabled = loop._apply_live_stage0_candidate_fallback(raw_pipe)

    assert out_enabled["paper_action"] == "OPEN"
    assert out_enabled["paper_strategy"] == "MM"
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_FINAL_PROBE_DECISION_BYPASS market_id=562200" in payload


def test_mm_final_probe_generates_one_sided_order(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.settings.execution_mode = "live_stage0"
    loop.settings.live_exec_style = "human_limit"
    loop.settings.live_max_notional = 10.0
    loop.executor = _ExecutorStub()
    loop._iter_decision_diag = {}
    loop._iter_pipe = {
        "paper_action": "OPEN",
        "paper_reason": "TOP_MM_CANDIDATE",
        "paper_strategy": "MM",
        "strategy_action": "OPEN_MM",
        "dedup_signature": "OPEN|TOP_MM_CANDIDATE|562201",
        "paper_market_id": "562201",
        "mm_bid": 0.40,
        "mm_ask": 0.46,
        "mm_mid": 0.43,
        "mm_spread": 0.06,
        "mm_bid_size": 12.0,
        "mm_ask_size": 8.0,
        "mm_liquidity": 8.0,
        "mm_score": 0.48,
        "mm_final_probe": 1,
    }
    loop._resolve_stage0_token_id = lambda market_id, outcome="YES": f"tok-{market_id}-{outcome}"
    monkeypatch.setenv("PS_MM_FINAL_PROBE", "true")

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        submitted = loop._maybe_submit_stage0_open_from_pipeline(datetime.now(timezone.utc))

    assert submitted == 1
    assert len(loop.executor.calls) == 1
    assert loop.executor.calls[0]["side"] == "BUY"
    assert loop.executor.calls[0]["kwargs"]["ttl_seconds"] == 45.0
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_FINAL_PROBE_ORDER market_id=562201 side=BUY" in payload


def test_mm_final_probe_summary_log_emitted(monkeypatch, caplog) -> None:
    loop = _mk_loop("OK")
    loop.executor = _ExecutorStub()
    loop._iter_decision_diag = {
        "mm_final_probe_candidates_seen": 5,
        "mm_final_probe_candidates_selected": 3,
        "mm_final_probe_orders_attempted": 1,
        "mm_final_probe_orders_failed": 0,
    }
    loop._mm_probe_prev_stats = {"placed": 0, "filled": 0, "canceled": 0}
    loop.executor.mm_probe_stats = {"placed": 1, "filled": 0, "canceled": 1}
    monkeypatch.setenv("PS_MM_FINAL_PROBE", "true")

    with caplog.at_level(logging.INFO, logger="dispatcher.loop"):
        loop._emit_mm_final_probe_summary()

    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_FINAL_PROBE_SUMMARY candidates_seen=5 candidates_selected=3 orders_attempted=1 orders_placed=1 orders_filled=0 orders_canceled=1 orders_failed=0" in payload
