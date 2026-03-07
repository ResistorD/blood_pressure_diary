from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from dispatcher.paper_decision_pipeline import run_paper_pipeline


class _FakeCursor:
    def __init__(self, row: dict[str, Any] | None):
        self._row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _FakeConn:
    def __init__(self, repo: "_FakeRepo"):
        self._repo = repo

    def execute(self, _sql: str) -> _FakeCursor:
        return _FakeCursor(self._repo.latest_row)


class _FakeRepo:
    def __init__(self) -> None:
        self.latest_row: dict[str, Any] | None = None
        self.inserted: list[dict[str, Any]] = []

    @contextmanager
    def conn(self):
        yield _FakeConn(self)

    def insert_decision_v0(self, **kwargs) -> None:
        self.inserted.append(kwargs)


def test_run_paper_pipeline_stale_signal_guard_new_stale_new():
    repo = _FakeRepo()
    ctx: dict[str, Any] = {
        "run_id": "run-test",
        "last_signature": "",
        "last_consumed_scout_key": "",
        "last_consumed_opportunity_key": "",
        "now": datetime.now(timezone.utc),
    }
    freshness_ok = {"overall": "OK"}

    repo.latest_row = {
        "signal_rowid": 101,
        "signal_ts": "2026-03-06T10:00:00+00:00",
        "market_id": "m1",
        "claim_json": '{"opportunity_key":"scout|kind:pair_arb|mids:m1,m2|group:g1|ptype:opposite"}',
    }
    out1 = run_paper_pipeline(repo=repo, freshness_state=freshness_ok, context=ctx)
    assert out1["selected"] == 1
    assert out1["skipped_as_stale"] == 0
    assert out1["consumed_key"] == "rowid:101"
    assert out1["cand_count"] == 1
    assert ctx["last_consumed_scout_key"] == "rowid:101"
    assert ctx["last_consumed_opportunity_key"] == "scout|kind:pair_arb|mids:m1,m2|group:g1|ptype:opposite"
    assert out1["paper_reason"] == "TOP_SCOUT_CANDIDATE"
    assert out1["opportunity_key"] == "scout|kind:pair_arb|mids:m1,m2|group:g1|ptype:opposite"
    assert out1["same_opportunity_as_prev"] == 0
    assert out1["skipped_as_same_opportunity"] == 0
    assert out1["dedup_signature"] == "OPEN|TOP_SCOUT_CANDIDATE|m1"
    assert out1["matched_prev_signature"] == ""

    repo.latest_row = {
        "signal_rowid": 102,
        "signal_ts": "2026-03-06T10:01:00+00:00",
        "market_id": "m1",
        "claim_json": '{"opportunity_key":"scout|kind:pair_arb|mids:m1,m2|group:g1|ptype:opposite"}',
    }
    out2 = run_paper_pipeline(repo=repo, freshness_state=freshness_ok, context=ctx)
    assert out2["selected"] == 0
    assert out2["skipped_as_stale"] == 0
    assert out2["skipped_as_same_opportunity"] == 1
    assert out2["consumed_key"] == "rowid:102"
    assert out2["cand_count"] == 0
    assert out2["paper_reason"] == "SAME_OPPORTUNITY_SKIPPED"
    assert ctx["last_consumed_scout_key"] == "rowid:102"
    assert ctx["last_consumed_opportunity_key"] == "scout|kind:pair_arb|mids:m1,m2|group:g1|ptype:opposite"
    assert out2["opportunity_key"] == "scout|kind:pair_arb|mids:m1,m2|group:g1|ptype:opposite"
    assert out2["same_opportunity_as_prev"] == 1
    # Regression guard: same-opportunity suppression happens before open/dedup candidate flow.
    assert out2["dedup_signature"] == ""
    assert out2["matched_prev_signature"] == ""

    repo.latest_row = {
        "signal_rowid": 102,
        "signal_ts": "2026-03-06T10:01:00+00:00",
        "market_id": "m1",
        "claim_json": '{"opportunity_key":"scout|kind:pair_arb|mids:m1,m2|group:g1|ptype:opposite"}',
    }
    out3 = run_paper_pipeline(repo=repo, freshness_state=freshness_ok, context=ctx)
    assert out3["selected"] == 0
    assert out3["skipped_as_stale"] == 1
    assert out3["skipped_as_same_opportunity"] == 0
    assert out3["consumed_key"] == "rowid:102"
    assert out3["cand_count"] == 0
    assert out3["paper_reason"] == "STALE_CANDIDATE_SKIPPED"
    assert ctx["last_consumed_scout_key"] == "rowid:102"
    assert ctx["last_consumed_opportunity_key"] == "scout|kind:pair_arb|mids:m1,m2|group:g1|ptype:opposite"
    assert out3["opportunity_key"] == "scout|kind:pair_arb|mids:m1,m2|group:g1|ptype:opposite"
    assert out3["same_opportunity_as_prev"] == 0
    assert out3["dedup_signature"] == ""
    assert out3["matched_prev_signature"] == ""

    repo.latest_row = {
        "signal_rowid": 103,
        "signal_ts": "2026-03-06T10:02:00+00:00",
        "market_id": "m1",
        "claim_json": '{"opportunity_key":"scout|kind:pair_arb|mids:m1,m3|group:g1|ptype:opposite"}',
    }
    out4 = run_paper_pipeline(repo=repo, freshness_state=freshness_ok, context=ctx)
    assert out4["selected"] == 1
    assert out4["skipped_as_stale"] == 0
    assert out4["skipped_as_same_opportunity"] == 0
    assert out4["consumed_key"] == "rowid:103"
    assert out4["cand_count"] == 1
    assert out4["paper_reason"] == "TOP_SCOUT_CANDIDATE"
    assert ctx["last_consumed_scout_key"] == "rowid:103"
    assert ctx["last_consumed_opportunity_key"] == "scout|kind:pair_arb|mids:m1,m3|group:g1|ptype:opposite"
    assert out4["opportunity_key"] == "scout|kind:pair_arb|mids:m1,m3|group:g1|ptype:opposite"
    assert out4["same_opportunity_as_prev"] == 0
    assert out4["dedup_signature"] == "OPEN|TOP_SCOUT_CANDIDATE|m1"
    assert out4["matched_prev_signature"] == ""

    repo.latest_row = None
    out5 = run_paper_pipeline(repo=repo, freshness_state=freshness_ok, context=ctx)
    assert out5["selected"] == 0
    assert out5["skipped_as_stale"] == 0
    assert out5["skipped_as_same_opportunity"] == 0
    assert out5["consumed_key"] == ""
    assert out5["cand_count"] == 0
    assert out5["paper_reason"] == "NO_CANDIDATES"
    assert out5["opportunity_key"] == ""
    assert out5["same_opportunity_as_prev"] == 0
    assert out5["dedup_signature"] == ""
    assert out5["matched_prev_signature"] == ""
