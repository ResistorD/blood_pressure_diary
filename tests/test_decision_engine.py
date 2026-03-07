import logging
from datetime import datetime, timezone

from decision.engine import Decision, DecisionEngineV0


def test_import_decision_engine():
    assert DecisionEngineV0 is not None


class _FakeRepo:
    def __init__(self):
        self.last = None
        self.inserts = []
        self.settings = {}

    def get_last_decision_v0(self, market_id: str):
        if self.last is None:
            return None
        return self.last

    def insert_decision_v0(self, **kwargs):
        self.inserts.append(dict(kwargs))
        self.last = (
            kwargs.get("ts", ""),
            kwargs.get("action", ""),
            kwargs.get("status", ""),
            kwargs.get("reason", ""),
            kwargs.get("reason_json", None),
        )

    def get_setting(self, key: str, default=None):
        return self.settings.get(key, default)


def test_case_lifecycle_summary_emitted_for_write_and_dedup(caplog):
    repo = _FakeRepo()
    engine = DecisionEngineV0(repo, min_emit_interval_sec=120)
    engine._case_obs_emit_every = 1
    now = datetime(2026, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    decision = Decision(market_id="m1", action="HOLD", status="OK", reason="NO_SIGNAL")

    with caplog.at_level(logging.INFO, logger="decision.engine"):
        wrote = engine._maybe_write(
            run_id="run-1",
            now=now,
            d=decision,
            paused=False,
            has_yes=True,
            has_no=False,
        )
        deduped = engine._maybe_write(
            run_id="run-1",
            now=now,
            d=decision,
            paused=False,
            has_yes=True,
            has_no=False,
        )

    assert wrote == 1
    assert deduped == 0
    assert len(repo.inserts) == 1

    lines = [r.getMessage() for r in caplog.records if "CASE_LIFECYCLE_SUMMARY" in r.getMessage()]
    assert len(lines) >= 2
    assert any("risk_kind=NONE" in line and "kill_kind=NONE" in line for line in lines)
    assert any("freshness_gate=NONE" in line for line in lines)
    assert any("dedup=0" in line and "dedup_kind=NONE" in line and "written=1" in line for line in lines)
    assert any("dedup=1" in line and "dedup_kind=HOLD_SPAM" in line and "written=0" in line for line in lines)
    assert any("same_as_previous_decision=0" in line and "noop_decision=1" in line for line in lines)
    assert any("same_as_previous_decision=1" in line and "noop_decision=1" in line for line in lines)
    obs = [r.getMessage() for r in caplog.records if "CASE_OBS_SUMMARY" in r.getMessage()]
    assert len(obs) >= 2
    assert any("total=1" in line and "written=1" in line and "dedup=0" in line and "none=1" in line for line in obs)
    assert any("total=2" in line and "written=1" in line and "dedup=1" in line and "hold_spam=1" in line for line in obs)
    quality = [r.getMessage() for r in caplog.records if "DECISION_QUALITY_SUMMARY" in r.getMessage()]
    assert len(quality) >= 2
    assert any("total=1" in line and "same_decision=0" in line and "noop=1" in line and "writes=1" in line for line in quality)
    assert any("total=2" in line and "same_decision=1" in line and "noop=2" in line and "writes=1" in line and "dedup=1" in line for line in quality)


def test_case_lifecycle_summary_risk_kind_for_blocked(caplog):
    repo = _FakeRepo()
    engine = DecisionEngineV0(repo, min_emit_interval_sec=120)
    engine._case_obs_emit_every = 1
    now = datetime(2026, 3, 6, 12, 5, 0, tzinfo=timezone.utc)
    decision = Decision(
        market_id="m-risk",
        action="HOLD",
        status="BLOCKED",
        reason="RISK: synthetic risk block",
        risk_kind="RISK_CONSTRAINT_SIGNAL",
    )

    with caplog.at_level(logging.INFO, logger="decision.engine"):
        wrote = engine._maybe_write(
            run_id="run-risk",
            now=now,
            d=decision,
            paused=False,
            has_yes=False,
            has_no=False,
        )

    assert wrote == 1
    lines = [r.getMessage() for r in caplog.records if "CASE_LIFECYCLE_SUMMARY" in r.getMessage()]
    assert len(lines) >= 1
    assert any("risk_block=1" in line and "risk_kind=RISK_CONSTRAINT_SIGNAL" in line and "kill_kind=NONE" in line for line in lines)


def test_case_lifecycle_summary_kill_kind_manual_for_kill_switch(caplog):
    repo = _FakeRepo()
    repo.settings["kill_switch_reason"] = "OPERATOR: manual toggle"
    engine = DecisionEngineV0(repo, min_emit_interval_sec=120)
    engine._case_obs_emit_every = 1
    now = datetime(2026, 3, 6, 12, 7, 0, tzinfo=timezone.utc)
    decision = Decision(
        market_id="m-kill",
        action="HOLD",
        status="BLOCKED",
        reason="KILL: kill-switch включён",
        risk_kind="KILL_SWITCH",
    )

    with caplog.at_level(logging.INFO, logger="decision.engine"):
        wrote = engine._maybe_write(
            run_id="run-kill-manual",
            now=now,
            d=decision,
            paused=False,
            has_yes=False,
            has_no=False,
        )

    assert wrote == 1
    lines = [r.getMessage() for r in caplog.records if "CASE_LIFECYCLE_SUMMARY" in r.getMessage()]
    assert any("risk_kind=KILL_SWITCH" in line and "kill_kind=MANUAL" in line for line in lines)


def test_case_lifecycle_summary_kill_kind_auto_limit_market_already_open(caplog):
    repo = _FakeRepo()
    repo.settings["kill_switch_reason"] = "AUTO: уже есть открытая paper-позиция по рынку"
    engine = DecisionEngineV0(repo, min_emit_interval_sec=120)
    engine._case_obs_emit_every = 1
    now = datetime(2026, 3, 6, 12, 8, 0, tzinfo=timezone.utc)
    decision = Decision(
        market_id="m-kill-auto",
        action="HOLD",
        status="BLOCKED",
        reason="KILL: kill-switch включён",
        risk_kind="KILL_SWITCH",
    )

    with caplog.at_level(logging.INFO, logger="decision.engine"):
        wrote = engine._maybe_write(
            run_id="run-kill-auto",
            now=now,
            d=decision,
            paused=False,
            has_yes=False,
            has_no=False,
        )

    assert wrote == 1
    lines = [r.getMessage() for r in caplog.records if "CASE_LIFECYCLE_SUMMARY" in r.getMessage()]
    assert any("risk_kind=KILL_SWITCH" in line and "kill_kind=AUTO_LIMIT_MARKET_ALREADY_OPEN" in line for line in lines)


def test_case_lifecycle_summary_freshness_gate_open_blocked_warn(caplog):
    repo = _FakeRepo()
    engine = DecisionEngineV0(repo, min_emit_interval_sec=120)
    engine._case_obs_emit_every = 1
    now = datetime(2026, 3, 6, 12, 9, 0, tzinfo=timezone.utc)
    decision = Decision(
        market_id="m-fresh",
        action="HOLD",
        status="OK",
        reason="FRESHNESS_WARN_OPEN_BLOCKED",
    )

    with caplog.at_level(logging.INFO, logger="decision.engine"):
        wrote = engine._maybe_write(
            run_id="run-fresh",
            now=now,
            d=decision,
            paused=False,
            has_yes=False,
            has_no=False,
        )

    assert wrote == 1
    lines = [r.getMessage() for r in caplog.records if "CASE_LIFECYCLE_SUMMARY" in r.getMessage()]
    assert any("freshness_gate=OPEN_BLOCKED_WARN" in line for line in lines)
