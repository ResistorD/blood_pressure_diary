from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class PolicyDecision:
    action: str          # e.g. HOLD / ENTER_YES / ENTER_NO / EXIT
    size_usd: float      # intended notional
    reason: str
    confidence: float = 0.0

class Policy:
    """Interface for strategies/policies that turn signals/market state into actions."""

    policy_id: str = "policy.base"

    def decide(self, market_id: str) -> Optional[PolicyDecision]:
        return None
