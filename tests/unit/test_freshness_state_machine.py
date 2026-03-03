from dispatcher.freshness import STATE_OK, STATE_STOP, STATE_WARN, compute_state


def test_transitions_with_hysteresis() -> None:
    warn_s = 2.5
    stop_s = 7.0
    h = 0.5

    s = compute_state(prev_state=STATE_OK, age_s=2.6, warn_s=warn_s, stop_s=stop_s, hysteresis_s=h)
    assert s == STATE_WARN

    s = compute_state(prev_state=s, age_s=7.1, warn_s=warn_s, stop_s=stop_s, hysteresis_s=h)
    assert s == STATE_STOP

    s = compute_state(prev_state=s, age_s=6.6, warn_s=warn_s, stop_s=stop_s, hysteresis_s=h)
    assert s == STATE_STOP

    s = compute_state(prev_state=s, age_s=6.5, warn_s=warn_s, stop_s=stop_s, hysteresis_s=h)
    assert s == STATE_WARN

    s = compute_state(prev_state=s, age_s=2.0, warn_s=warn_s, stop_s=stop_s, hysteresis_s=h)
    assert s == STATE_OK


def test_initial_state_no_forced_transition() -> None:
    assert compute_state(prev_state=None, age_s=1.0, warn_s=2.5, stop_s=7.0) == STATE_OK
    assert compute_state(prev_state=None, age_s=3.0, warn_s=2.5, stop_s=7.0) == STATE_WARN
    assert compute_state(prev_state=None, age_s=None, warn_s=2.5, stop_s=7.0) == STATE_STOP
