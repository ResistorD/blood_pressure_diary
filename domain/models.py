from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .enums import DecisionType, Mode, OrderStatus, PositionState, SignalKind


@dataclass(frozen=True)
class Run:
    run_id: str
    started_at: datetime
    mode: Mode
    config_hash: str
    git_hash: str = "unknown"


@dataclass(frozen=True)
class Market:
    market_id: str
    slug: str
    title: str
    close_time: Optional[datetime] = None
    rules_hash: str = ""
    group_key: Optional[str] = None
    raw_json: str = ""


@dataclass(frozen=True)
class Snapshot:
    ts: datetime
    market_id: str
    outcome: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    spread: Optional[float] = None
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    implied_prob: Optional[float] = None


@dataclass(frozen=True)
class CandidateAction:
    # Это НЕ ордер. Это "кандидатная мысль" от агента.
    action: str  # "ENTER" | "EXIT" | "SWITCH" | ...
    market_id: str
    outcome: str
    side: str  # "YES" | "NO"
    score: float
    notional_hint: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Signal:
    signal_id: str
    ts: datetime
    run_id: str
    agent_id: str
    kind: SignalKind
    scope_market_id: Optional[str] = None
    scope_group_key: Optional[str] = None
    scope_pair_key: Optional[str] = None

    features: Dict[str, float] = field(default_factory=dict)
    claim: Dict[str, Any] = field(default_factory=dict)
    candidates: List[CandidateAction] = field(default_factory=list)

    explain_short: str = ""
    explain_long: str = ""


@dataclass(frozen=True)
class Decision:
    decision_id: str
    ts: datetime
    run_id: str
    type: DecisionType

    plan: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)

    based_on_signal_ids: List[str] = field(default_factory=list)

    next_review_at: Optional[datetime] = None
    explain_short: str = ""
    explain_long: str = ""


@dataclass(frozen=True)
class Portfolio:
    portfolio_id: str
    name: str = "default"


@dataclass(frozen=True)
class Position:
    position_id: str
    run_id: str
    portfolio_id: str
    market_id: str
    outcome: str
    side: str  # "YES"|"NO"
    target_notional: float
    filled_notional: float = 0.0
    avg_price: Optional[float] = None
    state: PositionState = PositionState.OPENING
    opened_at: Optional[datetime] = None
    last_review_at: Optional[datetime] = None
    exit_plan: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Order:
    order_id: str
    run_id: str
    portfolio_id: str
    market_id: str
    outcome: str
    side: str  # "YES"|"NO"
    price: float
    size: float
    idempotency_key: str
    status: OrderStatus = OrderStatus.NEW
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    ts: datetime
    price: float
    size: float


# -----------------------------
# PolySyndicate "Logic Layer" helpers
# These are lightweight structs used by agents (Scout/Logic) in Signal.claim.
# They don't drive execution directly yet; they are for explainability + UI.
# -----------------------------

@dataclass(frozen=True)
class CandidatePair:
    pair_key: str
    group_key: str
    market_a: str
    market_b: str
    similarity: float
    reason: str


@dataclass(frozen=True)
class Constraint:
    kind: str  # "IMPLICATION" | "MX" | "PARITY"
    lhs: str
    rhs: str
    weight: float = 1.0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Violation:
    constraint_kind: str
    lhs: str
    rhs: str
    lhs_prob: Optional[float]
    rhs_prob: Optional[float]
    violation: float  # >0 means violated by that margin
    explain: str = ""


@dataclass(frozen=True)
class TradeLeg:
    market_id: str
    outcome: str  # "YES" | "NO"
    side: str     # "BUY" | "SELL"
    limit_price: Optional[float] = None
    qty: Optional[float] = None
    note: str = ""


@dataclass(frozen=True)
class TradePlan:
    plan_id: str
    kind: str  # "PAIR_ARB" | "HEDGE" | ...
    legs: List[TradeLeg] = field(default_factory=list)
    expected_edge: float = 0.0
    explain: str = ""
