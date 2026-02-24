from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import os

from execution.executor import Executor
from app.runtime_config import load_runtime_config


@dataclass
class LiveGuard:
    max_notional: float
    max_orders_per_day: int
    dry_run: bool


class ExecutorPolymarketCLOB(Executor):
    """Skeleton executor for Polymarket CLOB (no real trading wired)."""

    def __init__(self) -> None:
        _cfg, runtime = load_runtime_config()
        self._guard = LiveGuard(
            max_notional=float(getattr(runtime, "live_max_notional", 0.0) or 0.0),
            max_orders_per_day=int(getattr(runtime, "live_max_orders_per_day", 0) or 0),
            dry_run=bool(getattr(runtime, "live_dry_run", True)),
        )
        self._execution_mode = str(getattr(runtime, "execution_mode", "paper")).lower()
        self._orders_today = 0
        self._orders_day = datetime.now(timezone.utc).date()

        # Placeholders for future live integration. Do not store real keys in repo.
        self._polymarket_key = (os.getenv("POLYMARKET_KEY") or "").strip()
        self._private_key = (os.getenv("PRIVATE_KEY") or "").strip()
        self._api_url = (os.getenv("POLYMARKET_API_URL") or "").strip()

    def _roll_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._orders_day:
            self._orders_day = today
            self._orders_today = 0

    def _guard_live(self, notional: float) -> None:
        if self._execution_mode != "live":
            raise RuntimeError("Execution mode is not live")
        if self._guard.dry_run:
            raise RuntimeError("Live dry-run guard is enabled")
        if not self._polymarket_key:
            raise RuntimeError("POLYMARKET_KEY is not configured")
        if not self._private_key:
            raise RuntimeError("PRIVATE_KEY is not configured")
        if self._guard.max_notional <= 0:
            raise RuntimeError("Live max notional guard is not configured")
        if notional > self._guard.max_notional:
            raise RuntimeError("Live max notional exceeded")
        self._roll_day()
        if self._guard.max_orders_per_day <= 0:
            raise RuntimeError("Live max orders per day guard is not configured")
        if self._orders_today >= self._guard.max_orders_per_day:
            raise RuntimeError("Live max orders per day exceeded")

    def place_order(self, market_id: str, outcome: str, side: str, qty: float, limit_price: float) -> str:
        notional = float(qty) * float(limit_price)
        self._guard_live(notional)
        self._orders_today += 1
        raise NotImplementedError("Polymarket CLOB executor is not implemented")

    def cancel_order(self, order_id: str) -> None:
        if self._execution_mode != "live":
            raise RuntimeError("Execution mode is not live")
        raise NotImplementedError("Polymarket CLOB executor is not implemented")
