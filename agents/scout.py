from __future__ import annotations

import re
import uuid
from typing import Dict, Iterable, List, Optional

from agents.enhanced_base import EnhancedAgent, AgentContext
from domain.enums import SignalKind
from domain.models import CandidateAction, Market, Signal
from utils.time import now_utc


def _tokenize(s: str) -> List[str]:
    """Tokenize string for similarity comparison."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = [t for t in s.split() if len(t) >= 3]
    return toks


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Calculate Jaccard similarity between two sets."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def _levenshtein_ratio(s1: str, s2: str) -> float:
    """Calculate Levenshtein distance ratio (0-1)."""
    if not s1 or not s2:
        return 0.0
    
    # Simple implementation
    m, n = len(s1), len(s2)
    if m > n:
        s1, s2 = s2, s1
        m, n = n, m
    
    current = range(m + 1)
    for i in range(1, n + 1):
        previous, current = current, [i] + [0] * m
        for j in range(1, m + 1):
            add, delete, change = previous[j] + 1, current[j - 1] + 1, previous[j - 1]
            if s1[j - 1] != s2[i - 1]:
                change += 1
            current[j] = min(add, delete, change)
    
    # Convert distance to similarity ratio
    max_len = max(len(s1), len(s2))
    return 1.0 - (current[m] / max_len) if max_len > 0 else 0.0


class ScoutAgent(EnhancedAgent):
    """Enhanced market similarity detector.
    
    Finds related markets using multiple signals:
    - Group key clustering
    - Title similarity (Jaccard + Levenshtein)
    - Keyword matching
    - Category detection
    
    Outputs pair recommendations for arbitrage and hedging strategies.
    """
    agent_id = "scout.v2"

    def __init__(
        self,
        min_similarity: float = 0.22,
        max_group_size: int = 50,
    ):
        super().__init__()
        self.min_similarity = float(min_similarity)
        self.max_group_size = int(max_group_size)

    def _propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        """Find related markets and generate pair signals."""
        
        # Get markets
        markets: List[Market] = ctx.list_markets(limit=500)
        if not markets:
            return []

        # Filter to specific market if requested
        if market_id is not None:
            markets = [m for m in markets if m.market_id == market_id or m.slug == market_id]

        # Group markets by similarity
        by_group = self._cluster_markets(markets)

        # Generate signals for each group
        signals: List[Signal] = []
        for gk, ms in by_group.items():
            if len(ms) < 2 or len(ms) > self.max_group_size:
                continue

            # Find pairs within group
            pairs = self._find_pairs(ms, gk, ctx)
            signals.extend(pairs)

        return signals

    def _cluster_markets(self, markets: List[Market]) -> Dict[str, List[Market]]:
        """Cluster markets by group_key or similarity."""
        by_group: Dict[str, List[Market]] = {}
        
        for m in markets:
            g = (m.group_key or "").strip()
            
            if not g:
                # Create synthetic group from title keywords
                toks = _tokenize(m.title)[:2]
                if toks:
                    g = "auto:" + "-".join(toks)
                else:
                    g = "misc"
            
            by_group.setdefault(g, []).append(m)
        
        return by_group

    def _find_pairs(
        self,
        markets: List[Market],
        group_key: str,
        ctx: AgentContext
    ) -> List[Signal]:
        """Find similar pairs within a market group."""
        signals: List[Signal] = []
        
        for i in range(len(markets)):
            for j in range(i + 1, len(markets)):
                a, b = markets[i], markets[j]
                
                # Calculate multiple similarity metrics
                title_sim_jaccard = _jaccard(_tokenize(a.title), _tokenize(b.title))
                title_sim_leven = _levenshtein_ratio(a.title.lower(), b.title.lower())
                
                # Combined similarity score
                similarity = (title_sim_jaccard + title_sim_leven) / 2.0
                
                # Boost if same group_key
                if a.group_key and b.group_key and a.group_key == b.group_key:
                    similarity = max(similarity, 0.30)
                
                if similarity < self.min_similarity:
                    continue
                
                # Generate signal for this pair
                signal = self._create_pair_signal(a, b, group_key, similarity, ctx)
                signals.append(signal)
        
        return signals

    def _create_pair_signal(
        self,
        market_a: Market,
        market_b: Market,
        group_key: str,
        similarity: float,
        ctx: AgentContext
    ) -> Signal:
        """Create a signal for a market pair."""
        
        pair_key = f"{market_a.market_id}::{market_b.market_id}"
        
        # Determine pair type
        pair_type = self._classify_pair_type(market_a, market_b)
        
        # Create candidate actions
        candidates = [
            CandidateAction(
                action="MONITOR_PAIR",
                market_id=market_a.market_id,
                outcome="YES",
                side="BUY",
                score=similarity,
                notional_hint=None,
                details={
                    "pair_market": market_b.market_id,
                    "pair_type": pair_type,
                    "similarity": similarity,
                }
            ),
        ]
        
        return Signal(
            signal_id=str(uuid.uuid4()),
            ts=ctx.now,
            run_id=ctx.run_id,
            agent_id=self.agent_id,
            kind=SignalKind.PAIR_ARB,
            scope_market_id=market_a.market_id,
            scope_group_key=market_a.group_key or group_key,
            scope_pair_key=pair_key,
            features={
                "similarity": similarity,
                "group_size": 2.0,
                "has_group_key": 1.0 if market_a.group_key else 0.0,
            },
            claim={
                "type": "market_pair",
                "pair_type": pair_type,
                "market_a": {
                    "id": market_a.market_id,
                    "title": market_a.title,
                    "slug": market_a.slug,
                },
                "market_b": {
                    "id": market_b.market_id,
                    "title": market_b.title,
                    "slug": market_b.slug,
                },
                "group_key": group_key,
            },
            candidates=candidates,
            explain_short=f"Related markets: {similarity:.0%} similar",
            explain_long=(
                f"Found related markets: '{market_a.title}' and '{market_b.title}'. "
                f"Similarity: {similarity:.1%}. "
                f"Type: {pair_type}. "
                f"Consider for arbitrage or hedging strategies."
            ),
        )

    def _classify_pair_type(self, market_a: Market, market_b: Market) -> str:
        """Classify the type of market pair."""
        
        title_a = market_a.title.lower()
        title_b = market_b.title.lower()
        
        # Check for opposing markets (yes/no, win/lose, etc.)
        opposites = [
            ("will", "will not"), ("yes", "no"), ("win", "lose"),
            ("up", "down"), ("more", "less"), ("above", "below"),
            ("increase", "decrease"), ("rise", "fall"),
        ]
        
        for word1, word2 in opposites:
            if (word1 in title_a and word2 in title_b) or (word2 in title_a and word1 in title_b):
                return "opposite"
        
        # Check for same event, different thresholds
        if any(thresh in title_a and thresh in title_b for thresh in ["above", "below", "more than", "less than", "over", "under"]):
            return "threshold_variation"
        
        # Check for time variations
        if any(time in title_a and time in title_b for time in ["2024", "2025", "2026", "january", "february", "march", "april"]):
            return "time_variation"
        
        # Default: similar markets
        return "similar"
