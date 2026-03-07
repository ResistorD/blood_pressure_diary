from api.http import build_case_decision_why, build_case_reason_summary


def test_build_case_decision_why_warn_open_blocked() -> None:
    latest = {
        "status": "OK",
        "reason": "FRESHNESS_WARN_OPEN_BLOCKED",
    }
    runtime_pipe = {
        "decision_mode": "SAFE",
        "open_blocked_by_freshness": 1,
        "freshness_reason": "FRESHNESS_WARN_OPEN_BLOCKED",
    }
    out = build_case_decision_why(latest, runtime_pipe, kill_switch_reason="")
    assert out["decision_status"] == "OK"
    assert out["risk_kind"] == "NONE"
    assert out["kill_kind"] == "NONE"
    assert out["freshness_gate"] == "OPEN_BLOCKED_WARN"
    assert out["freshness_reason"] == "FRESHNESS_WARN_OPEN_BLOCKED"
    assert out["decision_mode"] == "SAFE"
    assert out["open_blocked_by_freshness"] == 1


def test_build_case_decision_why_halted_stop() -> None:
    latest = {
        "status": "BLOCKED",
        "reason": "FRESHNESS_STOP_HALTED",
    }
    out = build_case_decision_why(latest, {"decision_mode": "HALTED"}, kill_switch_reason="")
    assert out["freshness_gate"] == "HALTED_STOP"
    assert out["freshness_reason"] == "FRESHNESS_STOP_HALTED"
    assert out["decision_mode"] == "HALTED"


def test_build_case_decision_why_kill_switch_auto_source() -> None:
    latest = {
        "status": "BLOCKED",
        "reason": "KILL: kill-switch включён",
    }
    out = build_case_decision_why(
        latest,
        {"decision_mode": "FULL", "open_blocked_by_freshness": 0, "freshness_reason": "NONE"},
        kill_switch_reason="AUTO: исчерпан общий лимит капитала (paper)",
    )
    assert out["risk_kind"] == "KILL_SWITCH"
    assert out["kill_kind"] == "AUTO_LIMIT_MAX_NOTIONAL_TOTAL"
    assert out["freshness_gate"] == "NONE"


def test_build_case_reason_summary_priority_kill() -> None:
    out = build_case_reason_summary(
        {
            "kill_kind": "AUTO_LIMIT_MAX_NOTIONAL_TOTAL",
            "risk_kind": "KILL_SWITCH",
            "freshness_gate": "NONE",
            "freshness_reason": "NONE",
            "decision_status": "BLOCKED",
            "decision_reason": "KILL: kill-switch",
        }
    )
    assert out["primary"] == "KILL"
    assert out["secondary"] == "AUTO_LIMIT_MAX_NOTIONAL_TOTAL"


def test_build_case_reason_summary_priority_freshness() -> None:
    out = build_case_reason_summary(
        {
            "kill_kind": "NONE",
            "risk_kind": "NONE",
            "freshness_gate": "OPEN_BLOCKED_WARN",
            "freshness_reason": "FRESHNESS_WARN_OPEN_BLOCKED",
            "decision_status": "OK",
            "decision_reason": "FRESHNESS_WARN_OPEN_BLOCKED",
        }
    )
    assert out["primary"] == "FRESHNESS"
    assert out["secondary"] == "OPEN_BLOCKED_WARN"


def test_build_case_reason_summary_fallback_normal() -> None:
    out = build_case_reason_summary(
        {
            "kill_kind": "NONE",
            "risk_kind": "NONE",
            "freshness_gate": "NONE",
            "freshness_reason": "NONE",
            "decision_status": "OK",
            "decision_reason": "TOP_SCOUT_CANDIDATE",
        }
    )
    assert out["primary"] == "NORMAL"
    assert out["secondary"] == "TOP_SCOUT_CANDIDATE"
