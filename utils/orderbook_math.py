from __future__ import annotations

from typing import Dict, List, Tuple
import math


def calc_depth(levels: List[Dict[str, float]], mid: float, pct: float, side: str) -> float:
    """USD depth within +/- pct from mid for a side.

    side: "ask" or "bid"
    levels: [{"price": float, "size": float}, ...]
    """
    if not levels or mid <= 0:
        return 0.0
    upper = mid * (1.0 + pct)
    lower = mid * (1.0 - pct)
    total = 0.0
    for lvl in levels:
        px = float(lvl["price"])
        sz = float(lvl["size"])
        if sz <= 0:
            continue
        if side == "ask":
            if px > upper or px < mid:
                continue
        else:
            if px < lower or px > mid:
                continue
        total += px * sz
    return total


def calc_vwap_fill(
    levels: List[Dict[str, float]],
    size_shares: float,
    *,
    side: str = "ask",
) -> Dict[str, object]:
    """VWAP fill simulation over levels.

    side: "ask" (buy) or "bid" (sell/close)
    returns: {"filled": float, "vwap": float|None, "levels_used": [{"price","shares"}]}
    """
    if not levels or size_shares <= 0:
        return {"filled": 0.0, "vwap": None, "levels_used": []}
    lvls = sorted(levels, key=lambda x: x["price"], reverse=(side == "bid"))
    left = float(size_shares)
    cost = 0.0
    filled = 0.0
    used: List[Dict[str, float]] = []
    for lvl in lvls:
        if left <= 0:
            break
        px = float(lvl["price"])
        sz = float(lvl["size"])
        if sz <= 0:
            continue
        take = min(left, sz)
        cost += px * take
        filled += take
        used.append({"price": px, "shares": take})
        left -= take
    vwap = (cost / filled) if filled > 0 else None
    return {"filled": filled, "vwap": vwap, "levels_used": used}


def calc_book_warnings(book_age_s: float | None, *, threshold_sec: float = 15.0) -> List[str]:
    warnings: List[str] = []
    if book_age_s is not None and book_age_s > float(threshold_sec):
        warnings.append("STALE_BOOK")
    return warnings


def calc_preview_warnings(
    *,
    size_shares: float | None,
    book_present: bool,
    filled_shares: float | None,
    book_age_s: float | None,
    top_of_book: bool,
    stale_threshold_sec: float = 15.0,
) -> List[str]:
    warnings: List[str] = []
    if size_shares is None:
        warnings.append("SIZE_MISSING")
    if book_present:
        warnings.extend(calc_book_warnings(book_age_s, threshold_sec=stale_threshold_sec))
        if size_shares is not None and filled_shares is not None and filled_shares < float(size_shares):
            warnings.append("INSUFFICIENT_DEPTH")
    else:
        warnings.append("NO_ORDERBOOK")
    if top_of_book:
        warnings.append("TOP_OF_BOOK_ONLY")
    return warnings


def calc_max_safe_size(
    levels: List[Dict[str, float]],
    mid: float | None,
    max_slip_bps: float,
    *,
    side: str = "buy",
) -> int:
    """Max size with slip_bps <= max_slip_bps, based on VWAP.

    side: "buy" (asks) or "sell" (bids)
    returns integer shares (floor). 0 if none.
    """
    if not levels or mid is None or mid <= 0:
        return 0
    lvls = sorted(levels, key=lambda x: x["price"], reverse=(side == "sell"))
    total_cost = 0.0
    filled = 0.0
    max_ok = 0.0
    for lvl in lvls:
        px = float(lvl["price"])
        sz = float(lvl["size"])
        if sz <= 0:
            continue
        total_cost += px * sz
        filled += sz
        vwap = total_cost / filled if filled > 0 else None
        if vwap is None:
            continue
        if side == "buy":
            slip_bps = ((vwap - mid) / mid) * 10000.0
        else:
            slip_bps = ((mid - vwap) / mid) * 10000.0
        if slip_bps <= max_slip_bps:
            max_ok = filled
        else:
            break
    return int(math.floor(max_ok))
