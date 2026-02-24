from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from domain.enums import Mode, SignalKind
from domain.models import Market, Run, Signal


def _ensure_run(repo, run_id: str = "run-mn"):
    run = Run(
        run_id=run_id,
        started_at=datetime.now(timezone.utc),
        mode=Mode.DRY_RUN,
        config_hash="cfg",
        git_hash="git",
    )
    repo.insert_run(run)
    return run


def test_paper_pnl_timeseries_and_tradeability_metrics(repo):
    run = _ensure_run(repo)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    repo.insert_market(Market(market_id="m_block", slug="m_block", title="blocked", group_key="g1"))
    repo.insert_market(Market(market_id="m_open", slug="m_open", title="open", group_key="g1"))

    repo.insert_decision_v0(
        decision_id=str(uuid.uuid4()),
        ts=now,
        run_id=run.run_id,
        market_id="m_block",
        action="HOLD",
        status="OK",
        reason="Не торгуем",
        reason_json=json.dumps({"type": "NOT_TRADEABLE", "flags": ["stale"]}),
        payload_json="{}",
    )
    repo.insert_decision_v0(
        decision_id=str(uuid.uuid4()),
        ts=now,
        run_id=run.run_id,
        market_id="m_open",
        action="PAPER_BUY_BOTH",
        status="OK",
        reason="open",
        payload_json="{}",
    )

    repo.paper_buy(run_id=run.run_id, market_id="m_open", outcome="YES", qty=1.0, price=0.40)
    repo.paper_close(run_id=run.run_id, market_id="m_open", outcome="YES", price=0.55)

    ts = repo.get_paper_pnl_timeseries(limit=50)
    assert len(ts) >= 1
    assert ts[-1]["cumulative_pnl"] > 0

    fm = repo.get_tradeability_metrics(hours=24)
    assert fm["tradeable_cases"] >= 1
    assert fm["blocked_cases"] >= 1
    assert fm["opened_cases"] >= 1
    assert fm["opened_from_tradeable"] >= 1


def test_case_narrative_chain(repo):
    run = _ensure_run(repo, run_id="run-narr")
    now = datetime.now(timezone.utc)
    market_id = "m_narr"
    repo.insert_market(Market(market_id=market_id, slug=market_id, title="narr", group_key="g2"))

    scout = Signal(
        signal_id=str(uuid.uuid4()),
        ts=now,
        run_id=run.run_id,
        agent_id="scout.v2",
        kind=SignalKind.PAIR_ARB,
        scope_market_id=market_id,
        scope_group_key="g2",
        explain_short="scout saw relation",
    )
    logic = Signal(
        signal_id=str(uuid.uuid4()),
        ts=now,
        run_id=run.run_id,
        agent_id="logic.v2",
        kind=SignalKind.IMPLICATION,
        scope_market_id=market_id,
        scope_group_key="g2",
        explain_short="logic confirmed implication",
    )
    repo.insert_signal(scout)
    repo.insert_signal(logic)

    repo.insert_decision_v0(
        decision_id=str(uuid.uuid4()),
        ts=now.isoformat(timespec="seconds"),
        run_id=run.run_id,
        market_id=market_id,
        action="HOLD",
        status="BLOCKED",
        reason="LIMIT: blocked by risk",
        payload_json="{}",
    )
    repo.paper_buy(run_id=run.run_id, market_id=market_id, outcome="YES", qty=1.0, price=0.45)

    n = repo.get_case_narrative(market_id, minutes=240)
    assert n["scout"] is not None
    assert n["logic"] is not None
    assert n["decision"] is not None
    assert "risk" in n
