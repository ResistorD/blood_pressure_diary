"""Enhanced Auditor Agent for data quality monitoring."""
from __future__ import annotations

import uuid
from typing import List, Optional

from agents.enhanced_base import EnhancedAgent, AgentContext
from domain.enums import SignalKind
from domain.models import Signal
from utils.pricing import get_mid
from utils.logging import warn_exc


class AuditorAgent(EnhancedAgent):
    """Data quality monitoring agent."""
    agent_id = "auditor.v2"

    def _propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        """Check data quality."""
        signals = []
        markets = ctx.list_markets(limit=100)
        
        for market in markets[:20]:  # Check first 20
            if market_id and market.market_id != market_id:
                continue
            
            try:
                snapshots = ctx.get_market_snapshots(market.market_id)
                if not snapshots:
                    signals.append(Signal(
                        signal_id=str(uuid.uuid4()),
                        ts=ctx.now,
                        run_id=ctx.run_id,
                        agent_id=self.agent_id,
                        kind=SignalKind.ANOMALY,
                        scope_market_id=market.market_id,
                        features={},
                        claim={"type": "no_data"},
                        candidates=[],
                        explain_short=f"No data for {market.market_id}",
                        explain_long=f"Market {market.market_id} missing snapshot data",
                    ))
                    continue
                
                # Check invalid prices
                yes_mid = get_mid(snapshots, "YES")
                if yes_mid and (yes_mid < 0 or yes_mid > 1):
                    signals.append(Signal(
                        signal_id=str(uuid.uuid4()),
                        ts=ctx.now,
                        run_id=ctx.run_id,
                        agent_id=self.agent_id,
                        kind=SignalKind.ANOMALY,
                        scope_market_id=market.market_id,
                        features={"yes_mid": yes_mid},
                        claim={"type": "invalid_price"},
                        candidates=[],
                        explain_short=f"Invalid price: {yes_mid}",
                        explain_long=f"Invalid YES price in {market.market_id}: {yes_mid}",
                    ))
            except Exception:
                warn_exc(self._logger, "auditor snapshot check failed", market_id=market.market_id)
        
        return signals
