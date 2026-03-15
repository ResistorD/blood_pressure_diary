from __future__ import annotations

from dispatcher.loop import MainLoop


def _mk_loop_guard(max_block_ms: float, last_ingest_wall_ms: float, skip_cap: int = 3) -> MainLoop:
    loop = MainLoop.__new__(MainLoop)
    loop._ingest_max_block_ms = float(max_block_ms)
    loop._last_ingest_wall_ms = float(last_ingest_wall_ms)
    loop._ingest_block_guard_skip_cap = int(skip_cap)
    loop._ingest_block_guard_skips = 0
    return loop


def test_ingest_block_guard_allows_forced_attempt_after_bounded_skips() -> None:
    loop = _mk_loop_guard(max_block_ms=100.0, last_ingest_wall_ms=250.0, skip_cap=3)

    blocked_1, reset_1 = loop._resolve_ingest_block_guard(eligible_for_ingest=True)
    blocked_2, reset_2 = loop._resolve_ingest_block_guard(eligible_for_ingest=True)
    blocked_3, reset_3 = loop._resolve_ingest_block_guard(eligible_for_ingest=True)

    assert (blocked_1, reset_1) == (True, False)
    assert (blocked_2, reset_2) == (True, False)
    assert (blocked_3, reset_3) == (False, True)
    assert loop._ingest_block_guard_skips == 0


def test_ingest_block_guard_disabled_does_not_block() -> None:
    loop = _mk_loop_guard(max_block_ms=0.0, last_ingest_wall_ms=250.0, skip_cap=3)
    blocked, reset = loop._resolve_ingest_block_guard(eligible_for_ingest=True)
    assert (blocked, reset) == (False, False)
    assert loop._ingest_block_guard_skips == 0
