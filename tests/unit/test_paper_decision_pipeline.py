from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import logging
from typing import Any

from dispatcher.paper_decision_pipeline import run_paper_pipeline


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _FakeConn:
    def __init__(self, repo: "_FakeRepo"):
        self._repo = repo

    def execute(self, _sql: str, _params: Any = None) -> _FakeCursor:
        if self._repo.latest_row is not None:
            return _FakeCursor([self._repo.latest_row])
        return _FakeCursor(list(self._repo.pool_rows))


class _FakeRepo:
    def __init__(self) -> None:
        self.latest_row: dict[str, Any] | None = None
        self.pool_rows: list[dict[str, Any]] = []
        self.inserted: list[dict[str, Any]] = []

    @contextmanager
    def conn(self):
        yield _FakeConn(self)

    def insert_decision_v0(self, **kwargs) -> None:
        self.inserted.append(kwargs)


def test_run_paper_pipeline_stale_signal_guard_new_stale_new(monkeypatch):
    monkeypatch.setenv("PS_PAPER_MIN_SIMILARITY", "0.0")
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
        "features_json": '{"similarity": 0.31}',
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
        "features_json": '{"similarity": 0.30}',
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
        "features_json": '{"similarity": 0.30}',
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
        "features_json": '{"similarity": 0.35}',
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


def test_similarity_ranking_beats_latest_ts(monkeypatch):
    monkeypatch.setenv("PS_PAPER_MIN_SIMILARITY", "0.0")
    monkeypatch.setenv("PS_PAPER_SCOUT_POOL_N", "20")
    repo = _FakeRepo()
    ctx = {"run_id": "run-test", "last_signature": "", "last_consumed_scout_key": "", "last_consumed_opportunity_key": ""}
    repo.pool_rows = [
        {
            "signal_rowid": 201,
            "signal_ts": "2026-03-06T10:01:00+00:00",
            "market_id": "m_old_best",
            "features_json": '{"similarity": 0.90}',
            "claim_json": "{}",
        },
        {
            "signal_rowid": 202,
            "signal_ts": "2026-03-06T10:02:00+00:00",
            "market_id": "m_latest_weaker",
            "features_json": '{"similarity": 0.40}',
            "claim_json": "{}",
        },
    ]
    out = run_paper_pipeline(repo=repo, freshness_state={"overall": "OK"}, context=ctx)
    assert out["paper_action"] == "OPEN"
    assert out["paper_reason"] == "TOP_SCOUT_CANDIDATE"
    assert out["consumed_key"] == "rowid:201"
    assert out["candidate_similarity"] == 0.9


def test_ts_tiebreak_when_similarity_equal(monkeypatch):
    monkeypatch.setenv("PS_PAPER_MIN_SIMILARITY", "0.0")
    repo = _FakeRepo()
    ctx = {"run_id": "run-test", "last_signature": "", "last_consumed_scout_key": "", "last_consumed_opportunity_key": ""}
    repo.pool_rows = [
        {
            "signal_rowid": 301,
            "signal_ts": "2026-03-06T10:01:00+00:00",
            "market_id": "m_old",
            "features_json": '{"similarity": 0.70}',
            "claim_json": "{}",
        },
        {
            "signal_rowid": 302,
            "signal_ts": "2026-03-06T10:02:00+00:00",
            "market_id": "m_new",
            "features_json": '{"similarity": 0.70}',
            "claim_json": "{}",
        },
    ]
    out = run_paper_pipeline(repo=repo, freshness_state={"overall": "OK"}, context=ctx)
    assert out["paper_action"] == "OPEN"
    assert out["consumed_key"] == "rowid:302"


def test_below_threshold_yields_no_candidates_above_threshold(monkeypatch):
    monkeypatch.setenv("PS_PAPER_MIN_SIMILARITY", "0.80")
    repo = _FakeRepo()
    ctx = {"run_id": "run-test", "last_signature": "", "last_consumed_scout_key": "", "last_consumed_opportunity_key": ""}
    repo.pool_rows = [
        {
            "signal_rowid": 401,
            "signal_ts": "2026-03-06T10:02:00+00:00",
            "market_id": "m1",
            "features_json": '{"similarity": 0.50}',
            "claim_json": "{}",
        }
    ]
    out = run_paper_pipeline(repo=repo, freshness_state={"overall": "OK"}, context=ctx)
    assert out["paper_action"] == "HOLD"
    assert out["paper_reason"] == "NO_CANDIDATES_ABOVE_THRESHOLD"
    assert out["candidate_pool_size"] == 1
    assert out["candidate_min_similarity"] == 0.8


def test_invalid_similarity_does_not_crash_and_loses(monkeypatch):
    monkeypatch.setenv("PS_PAPER_MIN_SIMILARITY", "0.20")
    repo = _FakeRepo()
    ctx = {"run_id": "run-test", "last_signature": "", "last_consumed_scout_key": "", "last_consumed_opportunity_key": ""}
    repo.pool_rows = [
        {
            "signal_rowid": 501,
            "signal_ts": "2026-03-06T10:03:00+00:00",
            "market_id": "m_bad",
            "features_json": '{"similarity":"oops"}',
            "claim_json": "{}",
        },
        {
            "signal_rowid": 502,
            "signal_ts": "2026-03-06T10:02:00+00:00",
            "market_id": "m_good",
            "features_json": '{"similarity":0.55}',
            "claim_json": "{}",
        },
    ]
    out = run_paper_pipeline(repo=repo, freshness_state={"overall": "OK"}, context=ctx)
    assert out["paper_action"] == "OPEN"
    assert out["consumed_key"] == "rowid:502"


def test_mm_decision_when_no_arb(monkeypatch):
    monkeypatch.setenv("PS_ARB_THRESHOLD", "0.80")
    monkeypatch.setenv("PS_MM_THRESHOLD", "0.20")
    repo = _FakeRepo()
    ctx = {
        "run_id": "run-test",
        "last_signature": "",
        "last_consumed_scout_key": "",
        "last_consumed_opportunity_key": "",
        "cluster_mode": "NONE",
    }
    repo.pool_rows = [
        {
            "signal_rowid": 601,
            "signal_ts": "2026-03-12T10:00:00+00:00",
            "market_id": "m-mm",
            "features_json": '{"mm_score": 0.48}',
            "claim_json": '{"strategy":"MM","type":"market_making","opportunity_key":"mm:m-mm","bid":0.40,"ask":0.46,"mid":0.43,"spread":0.06,"bid_size":12,"ask_size":8,"liquidity":8,"mm_score":0.48}',
        }
    ]

    out = run_paper_pipeline(repo=repo, freshness_state={"overall": "OK"}, context=ctx)

    assert out["paper_action"] == "OPEN"
    assert out["paper_reason"] == "TOP_MM_CANDIDATE"
    assert out["paper_strategy"] == "MM"
    assert out["strategy_action"] == "OPEN_MM"
    assert out["cluster_mode"] == "MM"
    assert out["mm_score"] == 0.48


def test_mm_decision_uses_ps_mm_min_ev_alias(monkeypatch):
    monkeypatch.setenv("PS_ARB_THRESHOLD", "0.80")
    monkeypatch.delenv("PS_MM_THRESHOLD", raising=False)
    monkeypatch.setenv("PS_MM_MIN_EV", "-0.001")
    repo = _FakeRepo()
    ctx = {
        "run_id": "run-test",
        "last_signature": "",
        "last_consumed_scout_key": "",
        "last_consumed_opportunity_key": "",
        "cluster_mode": "NONE",
    }
    repo.pool_rows = [
        {
            "signal_rowid": 601,
            "signal_ts": "2026-03-12T10:00:00+00:00",
            "market_id": "m-mm",
            "features_json": '{"mm_score": 0.01}',
            "claim_json": '{"strategy":"MM","type":"market_making","opportunity_key":"mm:m-mm","bid":0.40,"ask":0.46,"mid":0.43,"spread":0.06,"bid_size":12,"ask_size":8,"liquidity":8,"mm_score":0.01}',
        }
    ]

    out = run_paper_pipeline(repo=repo, freshness_state={"overall": "OK"}, context=ctx)

    assert out["paper_action"] == "OPEN"
    assert out["paper_reason"] == "TOP_MM_CANDIDATE"


def test_mm_decision_preserves_one_sided_payload(monkeypatch):
    monkeypatch.setenv("PS_ARB_THRESHOLD", "0.80")
    monkeypatch.setenv("PS_MM_THRESHOLD", "0.20")
    repo = _FakeRepo()
    ctx = {
        "run_id": "run-test",
        "last_signature": "",
        "last_consumed_scout_key": "",
        "last_consumed_opportunity_key": "",
        "cluster_mode": "NONE",
    }
    repo.pool_rows = [
        {
            "signal_rowid": 602,
            "signal_ts": "2026-03-12T10:00:00+00:00",
            "market_id": "m-mm-one-sided",
            "features_json": '{"mm_score": 0.40}',
            "claim_json": '{"strategy":"MM","type":"market_making","opportunity_key":"mm:m-mm-one-sided","bid":null,"ask":0.46,"mid":0.435,"spread":0.05,"bid_size":0,"ask_size":8,"liquidity":8,"mm_score":0.40,"quote_mode":"ASK_ONLY","post_side":"BUY"}',
        }
    ]

    out = run_paper_pipeline(repo=repo, freshness_state={"overall": "OK"}, context=ctx)

    assert out["paper_action"] == "OPEN"
    assert out["mm_quote_mode"] == "ASK_ONLY"
    assert out["mm_post_side"] == "BUY"


def test_mm_candidate_found_decision_rejected_logs(monkeypatch, caplog):
    monkeypatch.setenv("PS_ARB_THRESHOLD", "0.80")
    monkeypatch.setenv("PS_MM_THRESHOLD", "0.50")
    repo = _FakeRepo()
    ctx = {
        "run_id": "run-test",
        "last_signature": "",
        "last_consumed_scout_key": "",
        "last_consumed_opportunity_key": "",
        "cluster_mode": "NONE",
    }
    repo.pool_rows = [
        {
            "signal_rowid": 650,
            "signal_ts": "2026-03-12T10:00:00+00:00",
            "market_id": "m-mm",
            "features_json": '{"mm_score": 0.48}',
            "claim_json": '{"strategy":"MM","type":"market_making","opportunity_key":"mm:m-mm","bid":0.40,"ask":0.46,"mid":0.43,"spread":0.06,"bid_size":12,"ask_size":8,"liquidity":8,"mm_score":0.48}',
        }
    ]

    with caplog.at_level(logging.INFO, logger="dispatcher.paper_decision_pipeline"):
        out = run_paper_pipeline(repo=repo, freshness_state={"overall": "OK"}, context=ctx)

    assert out["paper_action"] == "HOLD"
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_DECISION_REJECTED market_id=m-mm" in payload
    assert "reject_reason=MM_SCORE_BELOW_THRESHOLD" in payload


def test_mm_decision_when_no_arb_logs_accept(monkeypatch, caplog):
    monkeypatch.setenv("PS_ARB_THRESHOLD", "0.80")
    monkeypatch.setenv("PS_MM_THRESHOLD", "0.20")
    repo = _FakeRepo()
    ctx = {
        "run_id": "run-test",
        "last_signature": "",
        "last_consumed_scout_key": "",
        "last_consumed_opportunity_key": "",
        "cluster_mode": "NONE",
    }
    repo.pool_rows = [
        {
            "signal_rowid": 651,
            "signal_ts": "2026-03-12T10:00:00+00:00",
            "market_id": "m-mm",
            "features_json": '{"mm_score": 0.48}',
            "claim_json": '{"strategy":"MM","type":"market_making","opportunity_key":"mm:m-mm","bid":0.40,"ask":0.46,"mid":0.43,"spread":0.06,"bid_size":12,"ask_size":8,"liquidity":8,"mm_score":0.48}',
        }
    ]

    with caplog.at_level(logging.INFO, logger="dispatcher.paper_decision_pipeline"):
        out = run_paper_pipeline(repo=repo, freshness_state={"overall": "OK"}, context=ctx)

    assert out["paper_action"] == "OPEN"
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_DECISION_ACCEPTED market_id=m-mm" in payload


def test_mm_cluster_mode_blocked_by_arb(monkeypatch):
    monkeypatch.setenv("PS_ARB_THRESHOLD", "0.80")
    monkeypatch.setenv("PS_MM_THRESHOLD", "0.20")
    repo = _FakeRepo()
    ctx = {
        "run_id": "run-test",
        "last_signature": "",
        "last_consumed_scout_key": "",
        "last_consumed_opportunity_key": "",
        "cluster_mode": "ARB",
    }
    repo.pool_rows = [
        {
            "signal_rowid": 701,
            "signal_ts": "2026-03-12T10:00:00+00:00",
            "market_id": "m-mm",
            "features_json": '{"mm_score": 0.48}',
            "claim_json": '{"strategy":"MM","type":"market_making","opportunity_key":"mm:m-mm","bid":0.40,"ask":0.46,"mid":0.43,"spread":0.06,"bid_size":12,"ask_size":8,"liquidity":8,"mm_score":0.48}',
        }
    ]

    out = run_paper_pipeline(repo=repo, freshness_state={"overall": "OK"}, context=ctx)

    assert out["paper_action"] == "HOLD"
    assert out["paper_reason"] == "MM_BLOCKED_BY_ARB_CLUSTER"
    assert out["cluster_mode"] == "ARB"
