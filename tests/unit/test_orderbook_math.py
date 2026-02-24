from utils.orderbook_math import calc_book_warnings, calc_depth, calc_preview_warnings, calc_vwap_fill


def test_calc_depth_range():
    levels = [
        {"price": 0.99, "size": 10},
        {"price": 1.01, "size": 5},
        {"price": 1.05, "size": 2},
    ]
    mid = 1.0
    ask_depth = calc_depth(levels, mid, 0.02, "ask")
    bid_depth = calc_depth(levels, mid, 0.02, "bid")
    assert ask_depth == 1.01 * 5
    assert bid_depth == 0.99 * 10


def test_calc_vwap_fill():
    levels = [
        {"price": 0.60, "size": 5},
        {"price": 0.62, "size": 10},
    ]
    res = calc_vwap_fill(levels, 8, side="ask")
    assert res["filled"] == 8
    assert round(res["vwap"], 6) == round(((0.60 * 5) + (0.62 * 3)) / 8, 6)
    assert len(res["levels_used"]) == 2


def test_insufficient_depth_warning():
    levels = [{"price": 0.60, "size": 2}]
    res = calc_vwap_fill(levels, 5, side="ask")
    warnings = calc_preview_warnings(
        size_shares=5,
        book_present=True,
        filled_shares=res["filled"],
        book_age_s=1,
        top_of_book=False,
    )
    assert res["filled"] == 2
    assert "INSUFFICIENT_DEPTH" in warnings


def test_stale_book_warning():
    warnings = calc_book_warnings(25, threshold_sec=15)
    assert "STALE_BOOK" in warnings


def test_size_missing_warning():
    warnings = calc_preview_warnings(
        size_shares=None,
        book_present=False,
        filled_shares=None,
        book_age_s=None,
        top_of_book=True,
    )
    assert "SIZE_MISSING" in warnings


def test_no_orderbook_warning():
    warnings = calc_preview_warnings(
        size_shares=3,
        book_present=False,
        filled_shares=None,
        book_age_s=None,
        top_of_book=True,
    )
    assert "NO_ORDERBOOK" in warnings
