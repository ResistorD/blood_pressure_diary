from __future__ import annotations

import uuid
from typing import List, Optional

from agents.enhanced_base import EnhancedAgent, AgentContext
from domain.enums import SignalKind
from domain.models import Signal
from utils.pricing import get_mid


class QuantAgent(EnhancedAgent):
    """Quantitative quality checks agent with enhanced error handling."""
    
    agent_id = "quant.v2"

    def __init__(self, min_liquidity: float = 50.0, max_spread: float = 0.10):
        super().__init__()
        self.min_liquidity = float(min_liquidity)
        self.max_spread = float(max_spread)

    def _propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        if not market_id:
            return []

        snaps = ctx.get_market_snapshots(market_id)
        if not snaps:
            return []

        out: List[Signal] = []

        # 1) Risk constraints: low liquidity / high spread per outcome
        for outcome, d in snaps.items():
            liq = d.get("liquidity")
            spr = d.get("spread")

            if liq is not None and float(liq) < self.min_liquidity:
                out.append(
                    Signal(
                        signal_id=str(uuid.uuid4()),
                        ts=ctx.now,
                        run_id=ctx.run_id,
                        agent_id=self.agent_id,
                        kind=SignalKind.RISK_CONSTRAINT,
                        scope_market_id=market_id,
                        features={"liquidity": float(liq), "min_liquidity": self.min_liquidity},
                        claim={"type": "min_liquidity", "outcome": outcome},
                        explain_short=f"Liquidity low: {market_id}/{outcome} liq={float(liq):.1f} < {self.min_liquidity:.1f}",
                        explain_long="Risk constraint: thin books increase slippage and self-impact.",
                    )
                )

            if spr is not None and float(spr) > self.max_spread:
                out.append(
                    Signal(
                        signal_id=str(uuid.uuid4()),
                        ts=ctx.now,
                        run_id=ctx.run_id,
                        agent_id=self.agent_id,
                        kind=SignalKind.RISK_CONSTRAINT,
                        scope_market_id=market_id,
                        features={"spread": float(spr), "max_spread": self.max_spread},
                        claim={"type": "max_spread", "outcome": outcome},
                        explain_short=f"Spread high: {market_id}/{outcome} spr={float(spr):.3f} > {self.max_spread:.3f}",
                        explain_long="Risk constraint: wide spreads eat edge and make fills expensive.",
                    )
                )

        # 2) Partition check: YES(mid) + NO(mid) should be ~ 1
        yes_mid = get_mid(snaps, "YES")
        no_mid = get_mid(snaps, "NO")
        if yes_mid is not None and no_mid is not None:
            s = float(yes_mid) + float(no_mid)
            if s < 0.95 or s > 1.05:
                out.append(
                    Signal(
                        signal_id=str(uuid.uuid4()),
                        ts=ctx.now,
                        run_id=ctx.run_id,
                        agent_id=self.agent_id,
                        kind=SignalKind.QUALITY_ALERT,
                        scope_market_id=market_id,
                        features={"sum_mid": s, "yes_mid": float(yes_mid), "no_mid": float(no_mid)},
                        claim={"type": "partition_sum", "expected_range": [0.95, 1.05]},
                        explain_short=f"Partition off: {market_id} YES+NO(mid)={s:.3f} (Y={float(yes_mid):.3f}, N={float(no_mid):.3f})",
                        explain_long="If YES+NO deviates from 1, either data is stale or pricing is inconsistent (potential arb/alert).",
                    )
                )

        return out
