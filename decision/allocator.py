from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class Allocation:
    market_id: str
    action: str
    size_usd: float
    reason: str

class Allocator:
    """Turns policy outputs into concrete allocations under risk limits.
    Placeholder for a later, richer bankroll / exposure model.
    """

    def allocate(self, desired: list[Allocation], bankroll_usd: float) -> list[Allocation]:
        # naive: pass-through
        return desired
