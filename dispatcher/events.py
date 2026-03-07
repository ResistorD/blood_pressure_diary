from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Event:
    ts: datetime


@dataclass(frozen=True)
class MarketTick(Event):
    market_id: str


@dataclass(frozen=True)
class Timer(Event):
    purpose: str


@dataclass(frozen=True)
class Alert(Event):
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class OrderUpdate(Event):
    order_id: str
    status: str
