"""Pricing utilities for market data calculations."""
from __future__ import annotations

from typing import Optional, Dict, Any


def get_mid(snapshots: Dict[str, Dict[str, Any]], outcome: str) -> Optional[float]:
    """Extract mid price for outcome from snapshot dictionary.
    
    Args:
        snapshots: Dictionary mapping outcome -> snapshot data
        outcome: Outcome to get mid price for (e.g., "YES", "NO")
        
    Returns:
        Mid price as float, or None if not available
        
    Example:
        >>> snaps = {"YES": {"mid": 0.65}, "NO": {"mid": 0.35}}
        >>> get_mid(snaps, "YES")
        0.65
    """
    snap = snapshots.get(outcome)
    if not snap:
        return None
    mid = snap.get("mid")
    return float(mid) if mid is not None else None


def get_bid(snapshots: Dict[str, Dict[str, Any]], outcome: str) -> Optional[float]:
    """Extract bid price for outcome."""
    snap = snapshots.get(outcome)
    if not snap:
        return None
    bid = snap.get("bid")
    return float(bid) if bid is not None else None


def get_ask(snapshots: Dict[str, Dict[str, Any]], outcome: str) -> Optional[float]:
    """Extract ask price for outcome."""
    snap = snapshots.get(outcome)
    if not snap:
        return None
    ask = snap.get("ask")
    return float(ask) if ask is not None else None


def calculate_spread(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """Calculate bid-ask spread.
    
    Args:
        bid: Bid price
        ask: Ask price
        
    Returns:
        Absolute spread (ask - bid), or None if either is missing
        
    Example:
        >>> calculate_spread(0.60, 0.65)
        0.05
    """
    if bid is None or ask is None:
        return None
    return round(abs(ask - bid), 10)


def calculate_sum_mid(snapshots: Dict[str, Dict[str, Any]]) -> Optional[float]:
    """Calculate YES + NO mid price sum.
    
    For binary prediction markets, YES + NO should approximately equal 1.0.
    Deviations can indicate arbitrage opportunities or data issues.
    
    Args:
        snapshots: Dictionary mapping outcome -> snapshot data
        
    Returns:
        Sum of YES and NO mid prices, or None if either is missing
        
    Example:
        >>> snaps = {"YES": {"mid": 0.65}, "NO": {"mid": 0.35}}
        >>> calculate_sum_mid(snaps)
        1.0
    """
    yes_mid = get_mid(snapshots, "YES")
    no_mid = get_mid(snapshots, "NO")
    if yes_mid is None or no_mid is None:
        return None
    return yes_mid + no_mid


def is_tradeable(
    spread: Optional[float],
    liquidity: Optional[float],
    max_spread: float,
    min_liquidity: float
) -> bool:
    """Check if market is tradeable based on spread and liquidity constraints.
    
    Args:
        spread: Current bid-ask spread
        liquidity: Available liquidity
        max_spread: Maximum acceptable spread
        min_liquidity: Minimum required liquidity
        
    Returns:
        True if market meets tradeability criteria
        
    Example:
        >>> is_tradeable(0.03, 100.0, 0.05, 50.0)
        True
        >>> is_tradeable(0.10, 100.0, 0.05, 50.0)
        False
    """
    if spread is None or liquidity is None:
        return False
    return spread <= max_spread and liquidity >= min_liquidity


def calculate_implied_prob(mid: Optional[float]) -> Optional[float]:
    """Calculate implied probability from mid price.
    
    Args:
        mid: Mid price (0 to 1)
        
    Returns:
        Implied probability (same as mid for binary markets)
    """
    if mid is None:
        return None
    return float(mid)


def calculate_edge(
    fair_prob: float,
    market_price: float,
    side: str = "BUY"
) -> float:
    """Calculate trading edge.
    
    Args:
        fair_prob: Our estimated fair probability
        market_price: Current market price
        side: "BUY" or "SELL"
        
    Returns:
        Expected edge (positive = profitable)
        
    Example:
        >>> calculate_edge(0.70, 0.60, "BUY")
        0.1
    """
    if side.upper() == "BUY":
        return round(fair_prob - market_price, 10)
    else:  # SELL
        return round(market_price - fair_prob, 10)
