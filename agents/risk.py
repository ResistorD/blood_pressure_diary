"""Enhanced Risk Agent with portfolio-level risk management."""
from __future__ import annotations

import uuid
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from agents.enhanced_base import EnhancedAgent, AgentContext
from domain.enums import SignalKind
from domain.models import Signal
from utils.validation import validate_positive


@dataclass
class RiskLimits:
    """Risk limits configuration."""
    max_notional_total: float = 500.0
    max_notional_per_group: float = 250.0
    max_notional_per_market: float = 150.0
    max_concentration: float = 0.30
    min_diversification: int = 3


class RiskAgent(EnhancedAgent):
    """Portfolio risk management agent."""
    agent_id = "risk.v2"

    def __init__(self, limits: Optional[RiskLimits] = None):
        super().__init__()
        self.limits = limits or RiskLimits()

    def _propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        """Check portfolio-level risk constraints."""
        positions = self._get_positions(ctx)
        if not positions:
            return []
        
        signals = []
        signals.extend(self._check_total_exposure(positions, ctx))
        signals.extend(self._check_concentration(positions, ctx))
        
        return signals

    def _get_positions(self, ctx: AgentContext) -> List[Dict[str, Any]]:
        """Get current positions."""
        return list(ctx.get_open_positions())

    def _check_total_exposure(self, positions: List[Dict], ctx: AgentContext) -> List[Signal]:
        """Check total exposure."""
        total = sum(p["notional"] for p in positions)
        if total > self.limits.max_notional_total:
            return [Signal(
                signal_id=str(uuid.uuid4()),
                ts=ctx.now,
                run_id=ctx.run_id,
                agent_id=self.agent_id,
                kind=SignalKind.RISK_CONSTRAINT,
                features={"total": total, "limit": self.limits.max_notional_total},
                claim={"type": "risk", "severity": "HIGH"},
                candidates=[],
                explain_short=f"Total exposure ${total:.0f} exceeds limit ${self.limits.max_notional_total:.0f}",
                explain_long=f"Portfolio exposure is ${total:.2f}, which exceeds the limit of ${self.limits.max_notional_total:.2f}. Reduce positions.",
            )]
        return []

    def _check_concentration(self, positions: List[Dict], ctx: AgentContext) -> List[Signal]:
        """Check concentration."""
        if not positions:
            return []
        total = sum(p["notional"] for p in positions)
        signals = []
        for p in positions:
            concentration = p["notional"] / total
            if concentration > self.limits.max_concentration:
                signals.append(Signal(
                    signal_id=str(uuid.uuid4()),
                    ts=ctx.now,
                    run_id=ctx.run_id,
                    agent_id=self.agent_id,
                    kind=SignalKind.RISK_CONSTRAINT,
                    scope_market_id=p["market_id"],
                    features={"concentration": concentration},
                    claim={"type": "concentration"},
                    candidates=[],
                    explain_short=f"Position {p['market_id']} is {concentration:.0%} of portfolio",
                    explain_long=f"Concentration in {p['market_id']} is {concentration:.1%}, exceeds {self.limits.max_concentration:.0%} limit",
                ))
        return signals
