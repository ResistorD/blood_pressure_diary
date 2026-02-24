from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class Fill:
    ts: datetime
    market_id: str
    outcome: str
    side: str     # BUY / SELL
    qty: float
    price: float
    fee: float = 0.0
    note: str = ""

class Executor(ABC):
    """Real trading executor (not implemented yet)."""

    @abstractmethod
    def place_order(self, market_id: str, outcome: str, side: str, qty: float, limit_price: float) -> str:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> None:
        ...
