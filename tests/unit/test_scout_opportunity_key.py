from __future__ import annotations

from domain.enums import SignalKind
from agents.scout import build_scout_opportunity_key


def test_scout_opportunity_key_is_stable_for_same_logical_pair():
    k1 = build_scout_opportunity_key(
        kind=SignalKind.PAIR_ARB,
        market_a_id="m1",
        market_b_id="m2",
        group_key="G-Alpha",
        pair_type="opposite",
    )
    k2 = build_scout_opportunity_key(
        kind=SignalKind.PAIR_ARB,
        market_a_id="m2",
        market_b_id="m1",
        group_key="g-alpha",
        pair_type="Opposite",
    )
    assert k1 == k2


def test_scout_opportunity_key_changes_for_materially_different_opportunity():
    base = build_scout_opportunity_key(
        kind=SignalKind.PAIR_ARB,
        market_a_id="m1",
        market_b_id="m2",
        group_key="g-alpha",
        pair_type="opposite",
    )
    diff_pair = build_scout_opportunity_key(
        kind=SignalKind.PAIR_ARB,
        market_a_id="m1",
        market_b_id="m3",
        group_key="g-alpha",
        pair_type="opposite",
    )
    diff_type = build_scout_opportunity_key(
        kind=SignalKind.PAIR_ARB,
        market_a_id="m1",
        market_b_id="m2",
        group_key="g-alpha",
        pair_type="threshold_variation",
    )
    assert base != diff_pair
    assert base != diff_type
