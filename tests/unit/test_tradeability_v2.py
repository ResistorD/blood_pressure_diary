from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import DecisionConfig
from decision.engine_v2 import ActionType, ArbStrategy, DecisionStatus, MarketCase
from domain.models import Market, Snapshot


def test_tradeability_v2_blocks_on_quality_flags():
    now = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    cfg = DecisionConfig(
        min_age_snaps=1,
        volatility_window=3,
        liquidity_trend_window=3,
        stale_after_sec=60,
        require_two_sided_book=True,
        thin_liquidity_factor=0.8,
        min_liquidity=50.0,
    )
    case = MarketCase(market_id="m1", sum_mid=0.95, spread=0.02, liquidity=100.0, status="OK", reason="")
    hist = [
        {"ts": (now - timedelta(seconds=300)).isoformat(), "mid": 0.55, "liquidity": 10.0, "bid": None, "ask": 0.56},
        {"ts": (now - timedelta(seconds=320)).isoformat(), "mid": 0.54, "liquidity": 12.0, "bid": 0.53, "ask": 0.55},
        {"ts": (now - timedelta(seconds=340)).isoformat(), "mid": 0.53, "liquidity": 14.0, "bid": 0.52, "ask": 0.54},
    ]

    d = ArbStrategy().decide(case, positions={}, config=cfg, ctx={"history": hist, "now": now})
    assert d.status == DecisionStatus.BLOCKED
    assert d.action == ActionType.HOLD
    rj = (d.metadata or {}).get("reason_json") or {}
    checks = {c.get("key"): c for c in rj.get("checks", [])}
    assert checks["no_book"]["ok"] is False
    assert checks["thin"]["ok"] is False
    assert checks["stale"]["ok"] is False


def test_tradeability_v2_allows_buy_when_checks_pass():
    now = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    cfg = DecisionConfig(
        arb_buy_threshold=0.99,
        min_age_snaps=3,
        volatility_window=3,
        liquidity_trend_window=3,
        max_volatility=0.10,
        min_liquidity_trend=0.0,
        stale_after_sec=600,
        require_two_sided_book=True,
        thin_liquidity_factor=0.5,
        min_liquidity=50.0,
        max_spread=0.05,
    )
    case = MarketCase(market_id="m2", sum_mid=0.96, spread=0.02, liquidity=120.0, status="OK", reason="")
    hist = [
        {"ts": (now - timedelta(seconds=10)).isoformat(), "mid": 0.50, "liquidity": 120.0, "bid": 0.49, "ask": 0.51},
        {"ts": (now - timedelta(seconds=20)).isoformat(), "mid": 0.49, "liquidity": 118.0, "bid": 0.48, "ask": 0.50},
        {"ts": (now - timedelta(seconds=30)).isoformat(), "mid": 0.48, "liquidity": 116.0, "bid": 0.47, "ask": 0.49},
    ]

    d = ArbStrategy().decide(case, positions={"YES": False, "NO": False}, config=cfg, ctx={"history": hist, "now": now})
    assert d.status == DecisionStatus.OK
    assert d.action == ActionType.PAPER_BUY_BOTH


def test_repo_market_history_returns_desc(repo):
    now = datetime.now(timezone.utc)
    repo.insert_market(Market(market_id="mh1", slug="mh1", title="mh1", group_key="g1"))
    repo.insert_snapshots(
        [
            Snapshot(ts=now - timedelta(seconds=20), market_id="mh1", outcome="YES", mid=0.40, bid=0.39, ask=0.41, liquidity=80.0),
            Snapshot(ts=now - timedelta(seconds=10), market_id="mh1", outcome="YES", mid=0.42, bid=0.41, ask=0.43, liquidity=85.0),
        ]
    )
    hist = repo.market_history("mh1", limit=10)
    assert len(hist) == 2
    assert float(hist[0]["mid"]) == 0.42
