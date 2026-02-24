from __future__ import annotations

from datetime import datetime, timedelta, timezone

from domain.enums import Mode, SignalKind
from domain.models import Market, Run, Signal, Snapshot


def _mk_market(mid: str, group_key: str) -> Market:
    return Market(market_id=mid, slug=mid, title=f"Market {mid}", group_key=group_key)


def _mk_signal(
    *,
    ts: datetime,
    run_id: str,
    signal_id: str,
    kind: SignalKind,
    market_id: str,
    group_key: str,
    pair_key: str,
    features: dict,
    claim: dict,
) -> Signal:
    return Signal(
        signal_id=signal_id,
        ts=ts,
        run_id=run_id,
        agent_id="test.agent",
        kind=kind,
        scope_market_id=market_id,
        scope_group_key=group_key,
        scope_pair_key=pair_key,
        features=features,
        claim=claim,
        candidates=[],
        explain_short="edge",
        explain_long="edge-long",
    )


def test_cluster_graph_edges_and_neighbors(repo):
    now = datetime.now(timezone.utc)
    run = Run(run_id="run-cg", started_at=now, mode=Mode.DRY_RUN, config_hash="x", git_hash="y")
    repo.insert_run(run)

    gk = "g-cluster"
    m1 = _mk_market("m1", gk)
    m2 = _mk_market("m2", gk)
    m3 = _mk_market("m3", gk)
    repo.insert_market(m1)
    repo.insert_market(m2)
    repo.insert_market(m3)

    snaps = [
        Snapshot(ts=now, market_id="m1", outcome="YES", mid=0.55, spread=0.03, liquidity=100.0),
        Snapshot(ts=now, market_id="m1", outcome="NO", mid=0.45, spread=0.03, liquidity=120.0),
        Snapshot(ts=now, market_id="m2", outcome="YES", mid=0.51, spread=0.02, liquidity=90.0),
        Snapshot(ts=now, market_id="m2", outcome="NO", mid=0.49, spread=0.02, liquidity=95.0),
        Snapshot(ts=now, market_id="m3", outcome="YES", mid=0.70, spread=0.04, liquidity=70.0),
        Snapshot(ts=now, market_id="m3", outcome="NO", mid=0.30, spread=0.04, liquidity=75.0),
    ]
    repo.insert_snapshots(snaps)

    s1 = _mk_signal(
        ts=now,
        run_id=run.run_id,
        signal_id="s1",
        kind=SignalKind.PAIR_ARB,
        market_id="m1",
        group_key=gk,
        pair_key="m1::m2",
        features={"similarity": 0.82},
        claim={"market_a": {"id": "m1"}, "market_b": {"id": "m2"}},
    )
    s2 = _mk_signal(
        ts=now + timedelta(seconds=1),
        run_id=run.run_id,
        signal_id="s2",
        kind=SignalKind.ANOMALY,
        market_id="m1",
        group_key=gk,
        pair_key="m1::m3",
        features={"violation": 0.35},
        claim={"market_a": {"id": "m1"}, "market_b": {"id": "m3"}},
    )
    repo.insert_signal(s1)
    repo.insert_signal(s2)

    d_closest = repo.get_cluster_details_v2(gk, selected_market_id="m1", neighbor_sort="closest")
    assert d_closest["cluster_stats"]["markets_count"] == 3
    assert d_closest["cluster_stats"]["edges_count"] == 2
    assert len(d_closest["edges"]) == 2
    assert d_closest["neighbors"][0]["market_id"] == "m2"

    d_conflict = repo.get_cluster_details_v2(gk, selected_market_id="m1", neighbor_sort="conflict")
    assert d_conflict["neighbors"][0]["market_id"] == "m3"
