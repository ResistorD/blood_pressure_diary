from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

from agents.enhanced_base import EnhancedAgent, AgentContext
from domain.enums import SignalKind
from domain.models import CandidateAction, Market, Signal, Violation
from utils.pricing import get_mid
from utils.validation import validate_market_id


class LogicAgent(EnhancedAgent):
    """Enhanced logic constraint checker with multiple strategies.
    
    Detects violations in:
    - Implication constraints (A → B)
    - Mutex constraints (not both A and B)
    - Parity constraints (A + B ≈ 1)
    - Threshold violations
    
    Generates actionable trade recommendations based on violations.
    """
    agent_id = "logic.v2"

    def __init__(
        self,
        min_delta: float = 0.08,
        max_spread: float = 0.06,
        min_edge: float = 0.05,
    ):
        super().__init__()
        self.min_delta = float(min_delta)
        self.max_spread = float(max_spread)
        self.min_edge = float(min_edge)

    def _propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        """Check logical constraints across related markets."""
        
        # Get markets
        markets: List[Market] = ctx.list_markets(limit=500)
        if not markets:
            return []

        if market_id is not None:
            validate_market_id(market_id)
            markets = [m for m in markets if m.market_id == market_id or m.slug == market_id]

        # Group by group_key for constraint checking
        by_group: Dict[str, List[Market]] = {}
        for m in markets:
            if m.group_key:
                by_group.setdefault(m.group_key, []).append(m)

        # Check constraints
        signals: List[Signal] = []
        for gk, ms in by_group.items():
            if len(ms) < 2:
                continue
            
            # Check various constraint types
            signals.extend(self._check_parity_constraints(ms, gk, ctx))
            signals.extend(self._check_implication_constraints(ms, gk, ctx))
            signals.extend(self._check_mutex_constraints(ms, gk, ctx))
            signals.extend(self._check_threshold_violations(ms, gk, ctx))

        return signals

    def _check_parity_constraints(
        self,
        markets: List[Market],
        group_key: str,
        ctx: AgentContext
    ) -> List[Signal]:
        """Check YES + NO ≈ 1 for binary markets."""
        signals: List[Signal] = []
        
        for market in markets:
            snapshots = ctx.get_market_snapshots(market.market_id)
            if not snapshots:
                continue
            
            yes_mid = get_mid(snapshots, "YES")
            no_mid = get_mid(snapshots, "NO")
            
            if yes_mid is None or no_mid is None:
                continue
            
            parity_sum = yes_mid + no_mid
            deviation = abs(parity_sum - 1.0)
            
            # Significant deviation indicates arb opportunity
            if deviation > 0.05:  # 5% threshold
                violation = Violation(
                    constraint_kind="PARITY",
                    lhs=f"{market.market_id}:YES",
                    rhs=f"{market.market_id}:NO",
                    lhs_prob=yes_mid,
                    rhs_prob=no_mid,
                    violation=deviation,
                    explain=f"YES({yes_mid:.3f}) + NO({no_mid:.3f}) = {parity_sum:.3f} (expected: 1.0)"
                )
                
                # Determine trade direction
                if parity_sum < 1.0:
                    # Prices too low - buy both
                    action = "BUY_BOTH"
                    edge = 1.0 - parity_sum
                else:
                    # Prices too high - short both (or wait)
                    action = "WAIT"  # Can't easily short on Polymarket
                    edge = parity_sum - 1.0
                
                if edge >= self.min_edge:
                    signal = self._create_violation_signal(
                        market, violation, action, edge, group_key, ctx
                    )
                    signals.append(signal)
        
        return signals

    def _check_implication_constraints(
        self,
        markets: List[Market],
        group_key: str,
        ctx: AgentContext
    ) -> List[Signal]:
        """Check implication constraints: if A then B (P(A) <= P(B))."""
        signals: List[Signal] = []
        
        # Look for implied relationships in titles
        implications = self._find_implications(markets)
        
        for (antecedent, consequent) in implications:
            snapshots_a = ctx.get_market_snapshots(antecedent.market_id)
            snapshots_b = ctx.get_market_snapshots(consequent.market_id)
            
            if not snapshots_a or not snapshots_b:
                continue
            
            prob_a = get_mid(snapshots_a, "YES")
            prob_b = get_mid(snapshots_b, "YES")
            
            if prob_a is None or prob_b is None:
                continue
            
            # If A implies B, then P(A) should be <= P(B)
            if prob_a > prob_b:
                violation_amount = prob_a - prob_b
                
                if violation_amount > self.min_delta:
                    violation = Violation(
                        constraint_kind="IMPLICATION",
                        lhs=antecedent.title,
                        rhs=consequent.title,
                        lhs_prob=prob_a,
                        rhs_prob=prob_b,
                        violation=violation_amount,
                        explain=f"'{antecedent.title}' implies '{consequent.title}', but P(A)={prob_a:.3f} > P(B)={prob_b:.3f}"
                    )
                    
                    # Trade: buy B (underpriced) or sell A (overpriced)
                    signal = self._create_implication_signal(
                        antecedent, consequent, violation, group_key, ctx
                    )
                    signals.append(signal)
        
        return signals

    def _check_mutex_constraints(
        self,
        markets: List[Market],
        group_key: str,
        ctx: AgentContext
    ) -> List[Signal]:
        """Check mutually exclusive constraints: P(A) + P(B) <= 1."""
        signals: List[Signal] = []
        
        # Find mutex pairs
        mutex_pairs = self._find_mutex_pairs(markets)
        
        for (market_a, market_b) in mutex_pairs:
            snapshots_a = ctx.get_market_snapshots(market_a.market_id)
            snapshots_b = ctx.get_market_snapshots(market_b.market_id)
            
            if not snapshots_a or not snapshots_b:
                continue
            
            prob_a = get_mid(snapshots_a, "YES")
            prob_b = get_mid(snapshots_b, "YES")
            
            if prob_a is None or prob_b is None:
                continue
            
            prob_sum = prob_a + prob_b
            
            # Mutex: sum should be <= 1
            if prob_sum > 1.0 + 0.05:  # 5% tolerance
                violation_amount = prob_sum - 1.0
                
                violation = Violation(
                    constraint_kind="MUTEX",
                    lhs=market_a.title,
                    rhs=market_b.title,
                    lhs_prob=prob_a,
                    rhs_prob=prob_b,
                    violation=violation_amount,
                    explain=f"Mutually exclusive events: P(A)={prob_a:.3f} + P(B)={prob_b:.3f} = {prob_sum:.3f} > 1.0"
                )
                
                signal = self._create_mutex_signal(
                    market_a, market_b, violation, group_key, ctx
                )
                signals.append(signal)
        
        return signals

    def _check_threshold_violations(
        self,
        markets: List[Market],
        group_key: str,
        ctx: AgentContext
    ) -> List[Signal]:
        """Check threshold-based violations (e.g., above X, below Y)."""
        signals: List[Signal] = []
        
        # Find threshold pairs
        threshold_pairs = self._find_threshold_pairs(markets)
        
        for (lower_market, upper_market, threshold_type) in threshold_pairs:
            snapshots_l = ctx.get_market_snapshots(lower_market.market_id)
            snapshots_u = ctx.get_market_snapshots(upper_market.market_id)
            
            if not snapshots_l or not snapshots_u:
                continue
            
            prob_lower = get_mid(snapshots_l, "YES")
            prob_upper = get_mid(snapshots_u, "YES")
            
            if prob_lower is None or prob_upper is None:
                continue
            
            # Lower threshold should have higher probability
            if prob_upper > prob_lower:
                violation_amount = prob_upper - prob_lower
                
                if violation_amount > self.min_delta:
                    violation = Violation(
                        constraint_kind="THRESHOLD",
                        lhs=lower_market.title,
                        rhs=upper_market.title,
                        lhs_prob=prob_lower,
                        rhs_prob=prob_upper,
                        violation=violation_amount,
                        explain=f"Lower threshold should be more likely: P(lower)={prob_lower:.3f} < P(upper)={prob_upper:.3f}"
                    )
                    
                    signal = self._create_threshold_signal(
                        lower_market, upper_market, violation, threshold_type, group_key, ctx
                    )
                    signals.append(signal)
        
        return signals

    def _find_implications(self, markets: List[Market]) -> List[Tuple[Market, Market]]:
        """Find implication relationships between markets."""
        implications: List[Tuple[Market, Market]] = []
        
        for i, market_a in enumerate(markets):
            for market_b in markets[i+1:]:
                title_a = market_a.title.lower()
                title_b = market_b.title.lower()
                
                # Simple heuristics for implications
                # "X wins election" implies "X is candidate"
                # "Price above $100" implies "Price above $50"
                
                if "wins" in title_a and "candidate" in title_b:
                    implications.append((market_a, market_b))
                elif "candidate" in title_a and "wins" in title_b:
                    implications.append((market_b, market_a))
        
        return implications

    def _find_mutex_pairs(self, markets: List[Market]) -> List[Tuple[Market, Market]]:
        """Find mutually exclusive market pairs."""
        mutex_pairs: List[Tuple[Market, Market]] = []
        
        for i, market_a in enumerate(markets):
            for market_b in markets[i+1:]:
                title_a = market_a.title.lower()
                title_b = market_b.title.lower()
                
                # Look for exclusive outcomes
                exclusive_patterns = [
                    ("wins", "loses"),
                    ("republican wins", "democrat wins"),
                    ("increase", "decrease"),
                    ("above", "below"),
                ]
                
                for pattern_a, pattern_b in exclusive_patterns:
                    if pattern_a in title_a and pattern_b in title_b:
                        mutex_pairs.append((market_a, market_b))
                    elif pattern_b in title_a and pattern_a in title_b:
                        mutex_pairs.append((market_a, market_b))
        
        return mutex_pairs

    def _find_threshold_pairs(self, markets: List[Market]) -> List[Tuple[Market, Market, str]]:
        """Find threshold relationship pairs."""
        # Not used in canonical V0 pipeline.
        # Kept for experimental threshold-based logic.
        return []

    def _create_violation_signal(
        self,
        market: Market,
        violation: Violation,
        action: str,
        edge: float,
        group_key: str,
        ctx: AgentContext
    ) -> Signal:
        """Create signal for constraint violation."""
        
        candidates = [
            CandidateAction(
                action=action,
                market_id=market.market_id,
                outcome="YES",
                side="BUY" if "BUY" in action else "HOLD",
                score=edge,
                notional_hint=100.0 if edge > 0.10 else 50.0,
                details={"violation": violation.__dict__}
            )
        ]
        
        return Signal(
            signal_id=str(uuid.uuid4()),
            ts=ctx.now,
            run_id=ctx.run_id,
            agent_id=self.agent_id,
            kind=SignalKind.PAIR_ARB,
            scope_market_id=market.market_id,
            scope_group_key=group_key,
            features={
                "edge": edge,
                "violation": violation.violation,
                "constraint_type": violation.constraint_kind,
            },
            claim={
                "type": "constraint_violation",
                "violation": violation.__dict__,
            },
            candidates=candidates,
            explain_short=f"{violation.constraint_kind} violation: {edge:.2%} edge",
            explain_long=violation.explain,
        )

    def _create_implication_signal(
        self,
        antecedent: Market,
        consequent: Market,
        violation: Violation,
        group_key: str,
        ctx: AgentContext
    ) -> Signal:
        """Create signal for implication violation."""
        
        edge = violation.violation
        
        candidates = [
            CandidateAction(
                action="BUY",
                market_id=consequent.market_id,
                outcome="YES",
                side="BUY",
                score=edge,
                notional_hint=100.0,
                details={"reason": "underpriced_consequent"}
            ),
        ]
        
        return Signal(
            signal_id=str(uuid.uuid4()),
            ts=ctx.now,
            run_id=ctx.run_id,
            agent_id=self.agent_id,
            kind=SignalKind.IMPLICATION,
            scope_market_id=consequent.market_id,
            scope_group_key=group_key,
            features={"edge": edge, "violation": violation.violation},
            claim={"type": "implication_violation", "violation": violation.__dict__},
            candidates=candidates,
            explain_short=f"Implication violated: {edge:.2%} edge",
            explain_long=violation.explain,
        )

    def _create_mutex_signal(
        self,
        market_a: Market,
        market_b: Market,
        violation: Violation,
        group_key: str,
        ctx: AgentContext
    ) -> Signal:
        """Create signal for mutex violation."""
        
        return Signal(
            signal_id=str(uuid.uuid4()),
            ts=ctx.now,
            run_id=ctx.run_id,
            agent_id=self.agent_id,
            kind=SignalKind.ANOMALY,
            scope_market_id=market_a.market_id,
            scope_group_key=group_key,
            features={"violation": violation.violation},
            claim={"type": "mutex_violation", "violation": violation.__dict__},
            candidates=[],
            explain_short=f"Mutex violated: sum={violation.lhs_prob + violation.rhs_prob:.2%}",
            explain_long=violation.explain,
        )

    def _create_threshold_signal(
        self,
        lower_market: Market,
        upper_market: Market,
        violation: Violation,
        threshold_type: str,
        group_key: str,
        ctx: AgentContext
    ) -> Signal:
        """Create signal for threshold violation."""
        
        return Signal(
            signal_id=str(uuid.uuid4()),
            ts=ctx.now,
            run_id=ctx.run_id,
            agent_id=self.agent_id,
            kind=SignalKind.ANOMALY,
            scope_market_id=lower_market.market_id,
            scope_group_key=group_key,
            features={"violation": violation.violation},
            claim={"type": "threshold_violation", "violation": violation.__dict__},
            candidates=[],
            explain_short=f"Threshold violated: {violation.violation:.2%}",
            explain_long=violation.explain,
        )
