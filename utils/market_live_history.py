from __future__ import annotations

from collections import deque
from statistics import median
from typing import Any


class MarketLiveHistory:
    def __init__(self, window: int = 10):
        self.window = max(1, int(window or 10))
        self.history: dict[str, deque[dict[str, Any]]] = {}

    def update(
        self,
        market_id: str,
        valid_book: bool,
        missing_book: bool,
        boundary_book: bool,
        spread: float | None,
    ) -> None:
        key = str(market_id or "").strip()
        if not key:
            return
        bucket = self.history.get(key)
        if bucket is None or bucket.maxlen != self.window:
            prev = list(bucket or [])
            bucket = deque(prev[-self.window :], maxlen=self.window)
            self.history[key] = bucket
        bucket.append(
            {
                "valid_book": bool(valid_book),
                "missing_book": bool(missing_book),
                "boundary_book": bool(boundary_book),
                "spread": float(spread) if spread is not None else None,
            }
        )

    def metrics(self, market_id: str) -> dict[str, float | int | None] | None:
        key = str(market_id or "").strip()
        if not key:
            return None
        bucket = self.history.get(key)
        if not bucket:
            return None
        rows = list(bucket)
        samples = len(rows)
        if samples <= 0:
            return None
        spreads = [float(row["spread"]) for row in rows if row.get("spread") is not None]
        return {
            "valid_ratio": float(sum(1 for row in rows if row.get("valid_book")) / samples),
            "missing_ratio": float(sum(1 for row in rows if row.get("missing_book")) / samples),
            "boundary_ratio": float(sum(1 for row in rows if row.get("boundary_book")) / samples),
            "median_spread": float(median(spreads)) if spreads else None,
            "samples": int(samples),
        }
