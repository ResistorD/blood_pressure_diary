from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from agents.enhanced_base import EnhancedAgent, AgentContext
from domain.enums import SignalKind
from domain.models import CandidateAction, Market, Signal
from utils.market_live_history import MarketLiveHistory
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


def _norm_part(value: str | None) -> str:
    return str(value or "").strip().lower()


def build_scout_opportunity_key(
    *,
    kind: SignalKind,
    market_a_id: str,
    market_b_id: str,
    group_key: str | None,
    pair_type: str | None,
) -> str:
    """Stable logical identity for a scout pair opportunity.

    The key intentionally excludes time-varying/noisy values (timestamps, scores,
    explain text) and uses canonical market-id ordering so A/B and B/A map to
    the same logical opportunity.
    """
    mids = sorted([_norm_part(market_a_id), _norm_part(market_b_id)])
    kind_v = _norm_part(kind.value if hasattr(kind, "value") else str(kind))
    gk_v = _norm_part(group_key)
    pt_v = _norm_part(pair_type)
    return f"scout|kind:{kind_v}|mids:{mids[0]},{mids[1]}|group:{gk_v}|ptype:{pt_v}"


def build_mm_opportunity_key(*, market_id: str) -> str:
    return f"scout|kind:market_making|market:{_norm_part(market_id)}"


@dataclass(frozen=True)
class MMCandidate:
    market_id: str
    bid: Optional[float]
    ask: Optional[float]
    mid: float
    spread: float
    bid_size: float
    ask_size: float
    quote_mode: str = "TWO_SIDED"
    post_side: str = "BOTH"

    @property
    def liquidity(self) -> float:
        sizes = [float(size) for size in (self.bid_size, self.ask_size) if float(size) > 0.0]
        return min(sizes) if sizes else 0.0

    @property
    def mm_score(self) -> float:
        return float(self.spread) * float(self.liquidity)


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
        self._market_live_history = MarketLiveHistory(window=self._env_int("PS_MM_LIVE_WINDOW", 10))

    def _propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        """Find related markets and generate pair signals."""
        
        # Get markets
        markets: List[Market] = ctx.list_markets(limit=500)
        if not markets:
            return []
        dropped_invalid = 0
        filtered = []
        for m in markets:
            mid = str(m.market_id or "")
            if mid and not mid.isdigit():
                dropped_invalid += 1
                continue
            filtered.append(m)
        markets = filtered
        if dropped_invalid:
            self._logger.debug("dropped_invalid_market_id=%s", dropped_invalid)

        # Filter to specific market if requested
        if market_id is not None:
            markets = [m for m in markets if m.market_id == market_id or m.slug == market_id]

        raw_mm_markets = list(markets)
        markets = self._filter_live_stage0_eligible_markets(markets, ctx)
        mm_markets = self._filter_mm_live_eligible_markets(raw_mm_markets, ctx)

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

        signals.extend(self._find_mm_candidates(raw_mm_markets, mm_markets, ctx))

        return signals

    @staticmethod
    def _safe_float(value: object) -> Optional[float]:
        try:
            out = float(value)
        except Exception:
            return None
        if out != out:
            return None
        return out

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)) or default)
        except Exception:
            return float(default)

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)) or default)
        except Exception:
            return int(default)

    def _mm_live_history(self) -> MarketLiveHistory:
        window = max(1, self._env_int("PS_MM_LIVE_WINDOW", 10))
        history = getattr(self, "_market_live_history", None)
        if not isinstance(history, MarketLiveHistory) or int(getattr(history, "window", 0) or 0) != window:
            history = MarketLiveHistory(window=window)
            self._market_live_history = history
        return history

    def _mm_live_score_is_eligible(self, metrics: dict[str, object]) -> bool:
        samples = int(metrics.get("samples", 0) or 0)
        median_spread = self._safe_float(metrics.get("median_spread"))
        return (
            samples >= 5
            and float(metrics.get("valid_ratio", 0.0) or 0.0) >= self._env_float("PS_MM_MIN_VALID_RATIO", 0.7)
            and float(metrics.get("missing_ratio", 0.0) or 0.0) <= self._env_float("PS_MM_MAX_MISSING_RATIO", 0.2)
            and float(metrics.get("boundary_ratio", 0.0) or 0.0) <= self._env_float("PS_MM_MAX_BOUNDARY_RATIO", 0.2)
            and median_spread is not None
            and float(median_spread) <= self._env_float("PS_MM_MAX_MEDIAN_SPREAD", 0.20)
        )

    def _live_stage0_ineligible_reason(self, market_id: str, ctx: AgentContext) -> tuple[str, Optional[float], Optional[float], Optional[float]]:
        snaps = ctx.get_market_snapshots(market_id) or {}
        quote = {}
        for key, row in snaps.items():
            if str(key or "").strip().upper() == "YES" and isinstance(row, dict):
                quote = row
                break
        bid = self._safe_float((quote or {}).get("bid"))
        ask = self._safe_float((quote or {}).get("ask"))
        spread = self._safe_float((quote or {}).get("spread"))
        book = ctx.get_latest_orderbook(market_id) or {}
        book_bid = self._safe_float(book.get("best_bid"))
        book_ask = self._safe_float(book.get("best_ask"))
        ref_bid = book_bid if book_bid is not None else bid
        ref_ask = book_ask if book_ask is not None else ask
        eff_spread = spread if spread is not None and spread > 0.0 else None
        if eff_spread is None and ref_bid is not None and ref_ask is not None:
            eff_spread = ref_ask - ref_bid

        max_spread = self._env_float("PS_LIVE_HUMAN_MAX_SPREAD", 0.035)
        min_price = self._env_float("PS_LIVE_HUMAN_MIN_PRICE", 0.03)
        max_price = self._env_float("PS_LIVE_HUMAN_MAX_PRICE", 0.97)

        reason = ""
        if ref_bid is None or ref_ask is None:
            reason = "MISSING_BOOK"
        elif not (0.0 < ref_bid < ref_ask < 1.0):
            reason = "INVALID_BOOK"
        elif ref_bid <= 0.01 or ref_ask >= 0.99:
            reason = "BOUNDARY_BOOK"
        elif eff_spread is None or eff_spread <= 0.0 or eff_spread > max_spread:
            reason = "WIDE_SPREAD"
        elif ref_bid <= min_price or ref_ask >= max_price:
            reason = "BOUNDARY_BOOK"
        return reason, ref_bid, ref_ask, eff_spread

    def _filter_live_stage0_eligible_markets(self, markets: List[Market], ctx: AgentContext) -> List[Market]:
        mode = str(getattr(ctx.settings, "execution_mode", "paper") or "paper").strip().lower()
        live_exec_style = str(getattr(ctx.settings, "live_exec_style", os.getenv("PS_LIVE_EXEC_STYLE", "human_limit")) or "human_limit").strip().lower()
        if mode != "live_stage0" or live_exec_style not in {"human_limit", ""}:
            return list(markets)
        kept: List[Market] = []
        for market in markets:
            market_id = str(market.market_id or "").strip()
            if not market_id:
                continue
            reason, bid, ask, spread = self._live_stage0_ineligible_reason(market_id, ctx)
            if reason:
                self._logger.info(
                    "LIVE_STAGE0_MARKET_INELIGIBLE market_id=%s reason=%s bid=%s ask=%s spread=%s",
                    market_id,
                    reason,
                    "-" if bid is None else f"{bid:.6f}",
                    "-" if ask is None else f"{ask:.6f}",
                    "-" if spread is None else f"{spread:.6f}",
                )
                continue
            kept.append(market)
        return kept

    @staticmethod
    def _book_level_size(levels_raw: object) -> float:
        try:
            levels = json.loads(str(levels_raw or "[]"))
        except Exception:
            return 0.0
        if not isinstance(levels, list) or not levels:
            return 0.0
        level = levels[0] if isinstance(levels[0], dict) else {}
        for key in ("size", "qty", "quantity", "amount"):
            size = ScoutAgent._safe_float(level.get(key))
            if size is not None and size > 0.0:
                return float(size)
        return 0.0

    def _build_mm_candidate(self, market_id: str, ctx: AgentContext) -> Optional[MMCandidate]:
        candidate, _reason = self._build_mm_candidate_with_reason(market_id, ctx)
        return candidate

    def _build_mm_candidate_with_reason(self, market_id: str, ctx: AgentContext) -> tuple[Optional[MMCandidate], str]:
        book = ctx.get_latest_orderbook(market_id) or {}
        has_book = bool(book)
        bid = self._safe_float(book.get("best_bid"))
        ask = self._safe_float(book.get("best_ask"))
        bid_size = self._book_level_size(book.get("bids_json"))
        ask_size = self._book_level_size(book.get("asks_json"))
        if not has_book or (bid is None and ask is None):
            return None, "MISSING_BOOK"
        min_bid = self._env_float("PS_MM_MIN_BID", 0.001)
        max_ask = self._env_float("PS_MM_MAX_ASK", 0.999)
        max_spread = self._env_float("PS_MM_MAX_SPREAD", 0.5)
        probe_spread = min(max_spread, max(0.02, 0.05))
        if bid is not None and ask is not None:
            if not (0.0 < bid < ask < 1.0):
                return None, "INVALID_BOOK"
            if bid <= min_bid or ask >= max_ask:
                return None, "BOUNDARY_BOOK"
            spread = float(ask) - float(bid)
            mid = (float(bid) + float(ask)) / 2.0
            if spread < 0.02 or spread > max_spread:
                return None, "WIDE_SPREAD"
            if bid_size <= 0.0 or ask_size <= 0.0:
                return None, "INSUFFICIENT_SIZE"
            return MMCandidate(
                market_id=market_id,
                bid=float(bid),
                ask=float(ask),
                mid=float(mid),
                spread=float(spread),
                bid_size=float(bid_size),
                ask_size=float(ask_size),
                quote_mode="TWO_SIDED",
                post_side="BOTH",
            ), ""
        if ask is not None:
            if not (0.0 < ask < 1.0):
                return None, "INVALID_BOOK"
            if ask >= max_ask:
                return None, "BOUNDARY_BOOK"
            if ask_size <= 0.0:
                return None, "INSUFFICIENT_SIZE"
            mid = max(0.001, float(ask) - (probe_spread / 2.0))
            return MMCandidate(
                market_id=market_id,
                bid=None,
                ask=float(ask),
                mid=float(mid),
                spread=float(probe_spread),
                bid_size=0.0,
                ask_size=float(ask_size),
                quote_mode="ASK_ONLY",
                post_side="BUY",
            ), ""
        if bid is not None:
            if not (0.0 < bid < 1.0):
                return None, "INVALID_BOOK"
            if bid <= min_bid:
                return None, "BOUNDARY_BOOK"
            if bid_size <= 0.0:
                return None, "INSUFFICIENT_SIZE"
            mid = min(0.999, float(bid) + (probe_spread / 2.0))
            return MMCandidate(
                market_id=market_id,
                bid=float(bid),
                ask=None,
                mid=float(mid),
                spread=float(probe_spread),
                bid_size=float(bid_size),
                ask_size=0.0,
                quote_mode="BID_ONLY",
                post_side="SELL",
            ), ""
        return None, "MISSING_BOOK"

    def _mm_live_ineligible_reason(
        self,
        market_id: str,
        ctx: AgentContext,
    ) -> tuple[str, Optional[float], Optional[float], Optional[float], Optional[float]]:
        book = ctx.get_latest_orderbook(market_id) or {}
        bid = self._safe_float(book.get("best_bid"))
        ask = self._safe_float(book.get("best_ask"))
        spread: Optional[float] = None
        if bid is not None and ask is not None:
            spread = float(ask) - float(bid)
        if not book or (bid is None and ask is None):
            return "MISSING_BOOK", bid, ask, spread, None
        min_bid = self._env_float("PS_MM_MIN_BID", 0.001)
        max_ask = self._env_float("PS_MM_MAX_ASK", 0.999)
        max_spread = self._env_float("PS_MM_MAX_SPREAD", 0.5)
        if bid is not None and ask is not None:
            if not (0.0 < bid < ask < 1.0):
                return "INVALID_BOOK", bid, ask, spread, None
            if bid <= min_bid or ask >= max_ask:
                return "BOUNDARY_BOOK", bid, ask, spread, None
            if spread is None or spread <= 0.0 or spread > max_spread:
                return "WIDE_SPREAD", bid, ask, spread, None
            return "", bid, ask, spread, None
        if ask is not None:
            if not (0.0 < ask < 1.0):
                return "INVALID_BOOK", bid, ask, spread, None
            if ask >= max_ask:
                return "BOUNDARY_BOOK", bid, ask, spread, None
            return "", bid, ask, spread, None
        if bid is not None:
            if not (0.0 < bid < 1.0):
                return "INVALID_BOOK", bid, ask, spread, None
            if bid <= min_bid:
                return "BOUNDARY_BOOK", bid, ask, spread, None
            return "", bid, ask, spread, None
        return "", bid, ask, spread, None

    def _filter_mm_live_eligible_markets(self, markets: List[Market], ctx: AgentContext) -> List[Market]:
        mode = str(getattr(ctx.settings, "execution_mode", "paper") or "paper").strip().lower()
        live_exec_style = str(
            getattr(ctx.settings, "live_exec_style", os.getenv("PS_LIVE_EXEC_STYLE", "human_limit")) or "human_limit"
        ).strip().lower()
        if mode != "live_stage0" or live_exec_style not in {"human_limit", ""}:
            return list(markets)
        history = self._mm_live_history()
        kept: List[Market] = []
        for market in markets:
            market_id = str(market.market_id or "").strip()
            if not market_id:
                continue
            reason, bid, ask, spread, book_age_sec = self._mm_live_ineligible_reason(market_id, ctx)
            history.update(
                market_id=market_id,
                valid_book=(reason == ""),
                missing_book=(reason == "MISSING_BOOK"),
                boundary_book=(reason == "BOUNDARY_BOOK"),
                spread=spread,
            )
            metrics = history.metrics(market_id)
            samples = int((metrics or {}).get("samples", 0) or 0)
            if metrics is not None and samples < 5:
                self._logger.info(
                    "MM_LIVE_SCORE_WARMUP market_id=%s valid_ratio=%.2f missing_ratio=%.2f boundary_ratio=%.2f median_spread=%s samples=%s",
                    market_id,
                    float(metrics.get("valid_ratio", 0.0) or 0.0),
                    float(metrics.get("missing_ratio", 0.0) or 0.0),
                    float(metrics.get("boundary_ratio", 0.0) or 0.0),
                    "-" if self._safe_float(metrics.get("median_spread")) is None else f"{float(metrics.get('median_spread')):.6f}",
                    samples,
                )
            if reason:
                self._logger.info(
                    "MM_MARKET_INELIGIBLE market_id=%s reason=%s bid=%s ask=%s spread=%s book_age_sec=%s",
                    market_id,
                    reason,
                    "-" if bid is None else f"{bid:.6f}",
                    "-" if ask is None else f"{ask:.6f}",
                    "-" if spread is None else f"{spread:.6f}",
                    "-" if book_age_sec is None else f"{book_age_sec:.3f}",
                )
                continue
            if metrics is None or samples < 5:
                kept.append(market)
                continue
            live_eligible = self._mm_live_score_is_eligible(metrics)
            median_spread = self._safe_float(metrics.get("median_spread"))
            self._logger.info(
                "MM_LIVE_SCORE market_id=%s valid_ratio=%.2f missing_ratio=%.2f boundary_ratio=%.2f median_spread=%s samples=%s eligible=%s",
                market_id,
                float(metrics.get("valid_ratio", 0.0) or 0.0),
                float(metrics.get("missing_ratio", 0.0) or 0.0),
                float(metrics.get("boundary_ratio", 0.0) or 0.0),
                "-" if median_spread is None else f"{median_spread:.6f}",
                samples,
                int(live_eligible),
            )
            if not live_eligible:
                self._logger.info("MM_LIVE_MARKET_REJECTED market_id=%s reason=LIVE_SCORE_TOO_LOW", market_id)
                continue
            kept.append(market)
        return kept

    def _find_mm_candidates(self, raw_markets: List[Market], eligible_markets: List[Market], ctx: AgentContext) -> List[Signal]:
        mode = str(getattr(ctx.settings, "execution_mode", "paper") or "paper").strip().lower()
        live_exec_style = str(
            getattr(ctx.settings, "live_exec_style", os.getenv("PS_LIVE_EXEC_STYLE", "human_limit")) or "human_limit"
        ).strip().lower()
        self._logger.info(
            "MM_SCAN_START raw_markets_count=%s eligible_markets_count=%s live_mode=%s",
            len(raw_markets),
            len(eligible_markets),
            str(mode == "live_stage0" and live_exec_style in {"human_limit", ""}).lower(),
        )
        self._last_mm_scan_stats = {
            "raw_markets_count": int(len(raw_markets)),
            "eligible_markets_count": int(len(eligible_markets)),
            "candidates_found": 0,
        }
        if mode != "live_stage0" or live_exec_style not in {"human_limit", ""}:
            return []
        signals: List[Signal] = []
        for market in eligible_markets:
            market_id = str(market.market_id or "").strip()
            if not market_id:
                continue
            candidate, reject_reason = self._build_mm_candidate_with_reason(market_id, ctx)
            if candidate is None:
                book = ctx.get_latest_orderbook(market_id) or {}
                bid = self._safe_float(book.get("best_bid"))
                ask = self._safe_float(book.get("best_ask"))
                mid = ((float(bid) + float(ask)) / 2.0) if bid is not None and ask is not None else None
                spread = (float(ask) - float(bid)) if bid is not None and ask is not None else None
                bid_size = self._book_level_size(book.get("bids_json"))
                ask_size = self._book_level_size(book.get("asks_json"))
                mm_score = (
                    float(spread) * float(min(bid_size, ask_size))
                    if spread is not None and bid_size > 0.0 and ask_size > 0.0
                    else None
                )
                self._logger.info(
                    "MM_CANDIDATE_REJECTED market_id=%s mid=%s spread=%s bid_size=%s ask_size=%s mm_score=%s reject_reason=%s",
                    market_id,
                    "-" if mid is None else f"{mid:.6f}",
                    "-" if spread is None else f"{spread:.6f}",
                    "-" if bid_size <= 0.0 else f"{bid_size:.6f}",
                    "-" if ask_size <= 0.0 else f"{ask_size:.6f}",
                    "-" if mm_score is None else f"{mm_score:.6f}",
                    reject_reason or "UNKNOWN",
                )
                continue
            self._logger.info(
                "MM_CANDIDATE_FOUND market_id=%s mid=%.6f spread=%.6f bid_size=%.6f ask_size=%.6f mm_score=%.6f liquidity=%.6f",
                candidate.market_id,
                candidate.mid,
                candidate.spread,
                candidate.bid_size,
                candidate.ask_size,
                candidate.mm_score,
                candidate.liquidity,
            )
            signals.append(self._create_mm_signal(market, candidate, ctx))
        self._last_mm_scan_stats["candidates_found"] = int(len(signals))
        return signals

    def _cluster_markets(self, markets: List[Market]) -> Dict[str, List[Market]]:
        """Cluster markets by group_key or similarity."""
        by_group: Dict[str, List[Market]] = {}

        # Polymarket condition-based group keys are often unique per market.
        # Only use group_key when it truly clusters 2+ markets; otherwise
        # fallback to title/slug token bucketing so scout can still form pairs.
        group_counts: Dict[str, int] = {}
        for m in markets:
            g = (m.group_key or "").strip()
            if g:
                group_counts[g] = int(group_counts.get(g, 0) or 0) + 1

        for m in markets:
            g = (m.group_key or "").strip()

            if not g or int(group_counts.get(g, 0) or 0) <= 1:
                # Create synthetic group from stable text tokens.
                toks = _tokenize(f"{m.title} {m.slug}")[:2]
                g = "auto:" + "-".join(toks) if toks else "misc"

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
        opportunity_key = build_scout_opportunity_key(
            kind=SignalKind.PAIR_ARB,
            market_a_id=market_a.market_id,
            market_b_id=market_b.market_id,
            group_key=(market_a.group_key or group_key),
            pair_type=pair_type,
        )
        
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
                "opportunity_key": opportunity_key,
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

    def _create_mm_signal(self, market: Market, candidate: MMCandidate, ctx: AgentContext) -> Signal:
        opportunity_key = build_mm_opportunity_key(market_id=market.market_id)
        return Signal(
            signal_id=str(uuid.uuid4()),
            ts=ctx.now,
            run_id=ctx.run_id,
            agent_id=self.agent_id,
            kind=SignalKind.MARKET_MAKING,
            scope_market_id=market.market_id,
            scope_group_key=market.group_key,
            scope_pair_key=None,
            features={
                "mm_score": candidate.mm_score,
                "spread": candidate.spread,
                "mid": candidate.mid,
                "bid": candidate.bid,
                "ask": candidate.ask,
                "bid_size": candidate.bid_size,
                "ask_size": candidate.ask_size,
                "liquidity": candidate.liquidity,
            },
            claim={
                "type": "market_making",
                "strategy": "MM",
                "opportunity_key": opportunity_key,
                "market": {
                    "id": market.market_id,
                    "title": market.title,
                    "slug": market.slug,
                },
                "bid": candidate.bid,
                "ask": candidate.ask,
                "mid": candidate.mid,
                "spread": candidate.spread,
                "bid_size": candidate.bid_size,
                "ask_size": candidate.ask_size,
                "liquidity": candidate.liquidity,
                "mm_score": candidate.mm_score,
                "quote_mode": candidate.quote_mode,
                "post_side": candidate.post_side,
            },
            candidates=[
                CandidateAction(
                    action="MARKET_MAKE",
                    market_id=market.market_id,
                    outcome="YES",
                    side="BUY",
                    score=candidate.mm_score,
                    notional_hint=None,
                    details={
                        "strategy": "MM",
                        "spread": candidate.spread,
                        "mid": candidate.mid,
                        "bid_size": candidate.bid_size,
                        "ask_size": candidate.ask_size,
                        "quote_mode": candidate.quote_mode,
                        "post_side": candidate.post_side,
                    },
                )
            ],
            explain_short=f"Market making candidate spread={candidate.spread:.3f}",
            explain_long=(
                f"Market making candidate on market {market.market_id}. "
                f"bid={('-' if candidate.bid is None else f'{candidate.bid:.3f}')} "
                f"ask={('-' if candidate.ask is None else f'{candidate.ask:.3f}')} "
                f"spread={candidate.spread:.3f} liquidity={candidate.liquidity:.3f} "
                f"mm_score={candidate.mm_score:.3f}."
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
