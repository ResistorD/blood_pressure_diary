from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from agents.enhanced_base import AgentContext
from app.config import AppConfig
from app.runtime_config import to_runtime_settings
from db.agent_provider import RepoAgentDataProvider
from domain.enums import DecisionType
from domain.enums import Mode
from domain.enums import SignalKind
from domain.models import Decision, Market, Run, Signal, Snapshot


def test_runtime_settings_from_app_config():
    cfg = AppConfig()
    cfg.database.path = "test.db"
    cfg.dispatcher.poll_interval_sec = 11
    rs = to_runtime_settings(cfg)
    assert rs.db_path == "test.db"
    assert rs.poll_interval_sec == 11
    assert rs.host == cfg.api_host


def test_agent_context_prefers_data_provider_over_repo():
    @dataclass
    class StubProvider:
        def list_markets(self, limit: int = 500):
            return [{"market_id": "m1"}]

        def get_latest_snapshots(self, market_id: str):
            return {"YES": {"mid": 0.5}}

        def list_open_positions(self):
            return [{"market_id": "m1", "outcome": "YES", "notional": 10.0}]

    class RepoWithDifferentData:
        def list_markets(self, limit: int = 500):
            return [{"market_id": "repo"}]

        def get_latest_snapshots(self, market_id: str):
            return {"YES": {"mid": 0.1}}

    ctx = AgentContext(
        run_id="r1",
        now=datetime.now(timezone.utc),
        repo=RepoWithDifferentData(),
        settings=None,
        data_provider=StubProvider(),
    )
    assert ctx.list_markets()[0]["market_id"] == "m1"
    assert ctx.get_market_snapshots("m1")["YES"]["mid"] == 0.5
    assert ctx.get_open_positions()[0]["notional"] == 10.0


def test_repo_agent_provider_open_positions(repo):
    provider = RepoAgentDataProvider(repo)
    out = provider.list_open_positions()
    assert isinstance(out, list)


def test_repo_exposes_modular_repositories(repo):
    assert hasattr(repo, "markets")
    assert hasattr(repo, "runs")
    assert hasattr(repo, "snapshots")
    assert hasattr(repo, "signals")
    assert hasattr(repo, "decisions")
    assert hasattr(repo, "paper")
    assert hasattr(repo, "paper_analytics")
    assert hasattr(repo, "paper_queries")
    assert hasattr(repo, "paper_exec")
    assert hasattr(repo, "events")
    assert hasattr(repo, "settings")
    assert hasattr(repo, "read_models")
    assert hasattr(repo, "clusters")

    markets = repo.markets.list_markets(limit=5)
    assert isinstance(markets, list)


def test_paper_module_matches_legacy_open_positions(repo):
    provider = RepoAgentDataProvider(repo)
    via_provider = provider.list_open_positions()
    via_module = repo.paper.list_open_positions()
    assert via_provider == via_module


def test_market_module_upsert_and_get(repo):
    m = Market(market_id="arch-m1", slug="arch-m1", title="Arch Market", group_key="g-arch")
    repo.markets.upsert_market(m)
    got = repo.get_market("arch-m1")
    assert got is not None
    assert got.market_id == "arch-m1"
    listed = repo.list_markets(limit=50)
    assert any(x.market_id == "arch-m1" for x in listed)


def test_signal_module_insert_and_count(repo):
    before = repo.count_signals()
    repo.insert_run(
        Run(
            run_id="run-arch",
            started_at=datetime.now(timezone.utc),
            mode=Mode.DRY_RUN,
            config_hash="cfg",
            git_hash="git",
        )
    )
    repo.markets.upsert_market(
        Market(market_id="arch-m1", slug="arch-m1", title="Arch Market", group_key="g-arch")
    )
    s = Signal(
        signal_id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc),
        run_id="run-arch",
        agent_id="arch.test",
        kind=SignalKind.QUALITY_ALERT,
        scope_market_id="arch-m1",
        explain_short="arch signal",
    )
    repo.insert_signal(s)
    after = repo.count_signals()
    assert after == before + 1
    recent = repo.list_recent_signals(limit=5)
    assert isinstance(recent, list)
    filtered = repo.list_recent_signals_filtered(limit=5, agent="arch.test")
    assert isinstance(filtered, list)
    assert repo.count_signals_filtered(agent="arch.test") >= 1


def test_decision_module_filtered_list_and_count(repo, test_run, test_market):
    repo.insert_decision_v0(
        decision_id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        run_id=test_run.run_id,
        market_id=test_market.market_id,
        action="HOLD",
        status="OK",
        reason="arch decision",
        payload_json="{}",
    )
    rows = repo.list_recent_decisions_v0_filtered(limit=10, market_id=test_market.market_id)
    assert isinstance(rows, list)
    assert repo.count_decisions_v0_filtered(market_id=test_market.market_id) >= 1


def test_decision_domain_module_insert_and_count(repo, test_run):
    before = repo.count_decisions()
    d = Decision(
        decision_id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc),
        run_id=test_run.run_id,
        type=DecisionType.ENTER,
        plan={"k": "v"},
        risk={"r": 1},
        explain_short="domain decision",
    )
    repo.insert_decision_domain(d)
    assert repo.count_decisions() == before + 1


def test_paper_module_pending_and_marking(repo, test_run, test_market):
    cmd_id = f"{uuid.uuid4()}:YES:BUY"
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ok = repo.enqueue_paper_command(
        command_id=cmd_id,
        created_at=created_at,
        run_id=test_run.run_id,
        market_id=test_market.market_id,
        outcome="YES",
        cmd="BUY",
        qty=1.0,
        price_mode="MID",
        source_decision_id="d-test",
    )
    assert ok is True
    pending = repo.list_pending_paper_commands(limit=10)
    assert any(r["command_id"] == cmd_id for r in pending)

    repo.mark_paper_command_executed(cmd_id, created_at)
    pending2 = repo.list_pending_paper_commands(limit=10)
    assert all(r["command_id"] != cmd_id for r in pending2)


def test_paper_module_recent_for_market(repo, test_run, test_market):
    cmd_id = f"{uuid.uuid4()}:NO:CLOSE"
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    repo.enqueue_paper_command(
        command_id=cmd_id,
        created_at=created_at,
        run_id=test_run.run_id,
        market_id=test_market.market_id,
        outcome="NO",
        cmd="CLOSE",
        qty=1.0,
        price_mode="MID",
        source_decision_id="d-test-2",
    )
    rows = repo.list_recent_paper_queue_for_market(test_market.market_id, limit=10)
    assert isinstance(rows, list)
    assert len(rows) >= 1


def test_cluster_module_smoke(repo):
    out = repo.get_cluster_details("missing-group", limit_markets=10)
    assert isinstance(out, dict)
    assert out["group_key"] == "missing-group"
    assert isinstance(out.get("markets"), list)


def test_settings_and_events_modules(repo):
    repo.set_setting("arch.key", "value-1")
    assert repo.get_setting("arch.key") == "value-1"
    assert repo.settings.get("arch.key") == "value-1"

    repo.set_paused(True)
    assert repo.is_paused() is True
    assert repo.settings.is_paused() is True
    toggled = repo.toggle_paused()
    assert toggled is False

    repo.log_event(
        ts=datetime.now(timezone.utc),
        level="INFO",
        component="arch",
        message="event smoke",
        payload={"k": "v"},
    )
    with repo.conn() as con:
        row = con.execute(
            "SELECT component, message FROM events_log WHERE component='arch' ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["message"] == "event smoke"


def test_snapshot_batch_latest(repo, test_market):
    now = datetime.now(timezone.utc)
    repo.insert_snapshot(
        Snapshot(
            ts=now,
            market_id=test_market.market_id,
            outcome="YES",
            bid=0.49,
            ask=0.51,
            mid=0.50,
            spread=0.02,
            liquidity=100.0,
        )
    )
    repo.insert_snapshot(
        Snapshot(
            ts=now,
            market_id=test_market.market_id,
            outcome="NO",
            bid=0.47,
            ask=0.53,
            mid=0.50,
            spread=0.06,
            liquidity=90.0,
        )
    )
    data = repo.get_latest_snapshots_batch([test_market.market_id])
    assert test_market.market_id in data
    assert "YES" in data[test_market.market_id]
    assert "NO" in data[test_market.market_id]


def test_events_batch_logging(repo):
    now = datetime.now(timezone.utc)
    written = repo.log_events_batch(
        [
            {
                "ts": now,
                "level": "INFO",
                "component": "batch",
                "message": "m1",
                "payload": {"i": 1},
            },
            {
                "ts": now,
                "level": "INFO",
                "component": "batch",
                "message": "m2",
                "payload": {"i": 2},
            },
        ]
    )
    assert written == 2
    with repo.conn() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM events_log WHERE component='batch'").fetchone()
    assert int(row["n"]) >= 2
