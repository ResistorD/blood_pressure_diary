def test_lifecycle_state():
    from decision.lifecycle import LifecycleState
    s = LifecycleState(state="FLAT")
    assert s.state == "FLAT"
