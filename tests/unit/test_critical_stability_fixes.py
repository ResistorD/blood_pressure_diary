from __future__ import annotations

import uuid
from datetime import datetime, timezone

from dispatcher.bus import EventBus
from dispatcher.events import Timer


def test_repo_uses_wal_mode(repo):
    with repo.conn() as con:
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


def test_insert_decision_v0_atomically_enqueues_paper_commands(repo, test_run, test_market):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    decision_id = str(uuid.uuid4())

    repo.insert_decision_v0(
        decision_id=decision_id,
        ts=ts,
        run_id=test_run.run_id,
        market_id=test_market.market_id,
        action="PAPER_BUY_BOTH",
        status="OK",
        reason="paper open",
        payload_json="{}",
    )

    with repo.conn() as con:
        d = con.execute(
            "SELECT decision_id FROM decisions_v0 WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        rows = con.execute(
            """
            SELECT command_id, outcome, cmd, source_decision_id
            FROM paper_queue
            WHERE source_decision_id = ?
            ORDER BY outcome ASC
            """,
            (decision_id,),
        ).fetchall()

    assert d is not None
    assert len(rows) == 2
    assert {r["outcome"] for r in rows} == {"YES", "NO"}
    assert {r["cmd"] for r in rows} == {"BUY"}


def test_event_bus_is_always_bounded():
    bus = EventBus(maxlen=None)
    for i in range(7000):
        bus.publish(Timer(ts=datetime.now(timezone.utc), purpose=f"p{i}"))

    assert bus.size() == 5000
    assert bus.dropped() == 2000
