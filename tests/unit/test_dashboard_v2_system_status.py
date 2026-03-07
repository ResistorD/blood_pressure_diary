from types import SimpleNamespace

from api.dashboard_v2 import _build_system_status


def test_system_status_full_allowed() -> None:
    repo = SimpleNamespace(
        _runtime_freshness_state={"overall": "OK"},
        _runtime_pipeline_stats={"decision_mode": "FULL", "cand_count": 1, "dec_count": 1, "last": "OPEN/TOP"},
        _runtime_reconcile_diag={"scheduled": 1, "allowed": 1, "skip_reason": "NONE"},
    )
    out = _build_system_status(repo)
    assert out["freshness"] == "FRESHNESS_OK"
    assert out["decision_mode"] == "FULL"
    assert out["reconcile_state"] == "ALLOWED"
    assert out["open_blocked_by_freshness"] == 0


def test_system_status_safe_open_blocked() -> None:
    repo = SimpleNamespace(
        _runtime_freshness_state={"overall": "WARN"},
        _runtime_pipeline_stats={
            "decision_mode": "SAFE",
            "open_blocked_by_freshness": 1,
            "freshness_reason": "FRESHNESS_WARN_OPEN_BLOCKED",
            "cand_count": 1,
            "dec_count": 0,
            "last": "HOLD/FRESHNESS_WARN_OPEN_BLOCKED",
        },
        _runtime_reconcile_diag={"scheduled": 1, "allowed": 1, "skip_reason": "NONE"},
    )
    out = _build_system_status(repo)
    assert out["freshness"] == "FRESHNESS_WARN"
    assert out["decision_mode"] == "SAFE"
    assert out["opens_state"] == "BLOCKED_BY_FRESHNESS"
    assert out["reconcile_state"] == "ALLOWED"
    assert out["freshness_reason"] == "FRESHNESS_WARN_OPEN_BLOCKED"


def test_system_status_halted_blocked_by_freshness() -> None:
    repo = SimpleNamespace(
        _runtime_freshness_state={"overall": "STOP"},
        _runtime_pipeline_stats={"decision_mode": "HALTED", "freshness_reason": "FRESHNESS_STOP_HALTED"},
        _runtime_reconcile_diag={"scheduled": 1, "allowed": 0, "skip_reason": "FRESHNESS_STOP"},
    )
    out = _build_system_status(repo)
    assert out["freshness"] == "FRESHNESS_STOP"
    assert out["decision_mode"] == "HALTED"
    assert out["reconcile_state"] == "BLOCKED"
    assert out["reconcile_skip_reason"] == "FRESHNESS_STOP"
