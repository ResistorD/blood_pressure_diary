from __future__ import annotations

import logging
from types import SimpleNamespace

from agents.scout import ScoutAgent
from domain.models import Market
from agents.enhanced_base import AgentContext


def test_cluster_markets_falls_back_when_group_keys_are_singletons() -> None:
    agent = ScoutAgent()
    markets = [
        Market(market_id="1", slug="btc-above-100k", title="BTC above 100k", group_key="cond:a"),
        Market(market_id="2", slug="btc-above-120k", title="BTC above 120k", group_key="cond:b"),
        Market(market_id="3", slug="eth-above-5k", title="ETH above 5k", group_key="cond:c"),
    ]

    grouped = agent._cluster_markets(markets)
    multi_groups = [members for members in grouped.values() if len(members) >= 2]

    assert multi_groups, "expected at least one fallback group with 2+ markets"
    assert any({m.market_id for m in g} == {"1", "2"} for g in multi_groups)


def test_scout_filters_live_stage0_ineligible_markets_before_pair_construction(caplog) -> None:
    agent = ScoutAgent()
    markets = [
        Market(market_id="562003", slug="btc-above-100k", title="BTC above 100k"),
        Market(market_id="562004", slug="btc-above-120k", title="BTC above 120k"),
        Market(market_id="562005", slug="btc-above-140k", title="BTC above 140k"),
    ]

    class _Provider:
        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {
                "562003": {"YES": {"bid": 0.001, "ask": 0.999, "mid": 0.5, "spread": 0.998}},
                "562004": {"YES": {"bid": 0.40, "ask": 0.405, "mid": 0.4025, "spread": 0.005}},
                "562005": {"YES": {"bid": None, "ask": None, "mid": None, "spread": None}},
            }.get(market_id, {})

        def get_latest_orderbook(self, market_id: str):
            return {
                "562003": {"best_bid": 0.001, "best_ask": 0.999},
                "562004": {"best_bid": 0.40, "best_ask": 0.405},
                "562005": {"best_bid": None, "best_ask": None},
            }.get(market_id, {})

        def list_open_positions(self):
            return []

    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=_Provider(),
    )

    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        filtered = agent._filter_live_stage0_eligible_markets(markets, ctx)

    assert [m.market_id for m in filtered] == ["562004"]
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert payload.count("LIVE_STAGE0_MARKET_INELIGIBLE") == 2
    assert "market_id=562003 reason=BOUNDARY_BOOK" in payload
    assert "market_id=562005 reason=MISSING_BOOK" in payload


def test_mm_candidate_detection(caplog) -> None:
    agent = ScoutAgent()
    markets = [Market(market_id="562004", slug="btc-flat", title="BTC flat")]

    class _Provider:
        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {"562004": {"YES": {"bid": 0.40, "ask": 0.46, "mid": 0.43, "spread": 0.06}}}.get(market_id, {})

        def get_latest_orderbook(self, market_id: str):
            return {
                "562004": {
                    "best_bid": 0.40,
                    "best_ask": 0.46,
                    "bids_json": '[{"price":0.40,"size":12}]',
                    "asks_json": '[{"price":0.46,"size":8}]',
                }
            }.get(market_id, {})

        def list_open_positions(self):
            return []

    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=_Provider(),
    )

    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        out = agent._propose(ctx)

    mm = [s for s in out if str(s.claim.get("strategy") or "").upper() == "MM"]
    assert len(mm) == 1
    assert mm[0].scope_market_id == "562004"
    assert mm[0].features["mm_score"] == 0.48
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_CANDIDATE_FOUND market_id=562004" in payload


def test_mm_candidate_rejected_logs_reason(caplog) -> None:
    agent = ScoutAgent()
    markets = [Market(market_id="562010", slug="btc-tight", title="BTC tight")]

    class _Provider:
        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return {
                "562010": {
                    "best_bid": 0.40,
                    "best_ask": 0.41,
                    "bids_json": '[{"price":0.40,"size":12}]',
                    "asks_json": '[{"price":0.41,"size":8}]',
                }
            }.get(market_id, {})

        def list_open_positions(self):
            return []

    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=_Provider(),
    )

    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        out = agent._propose(ctx)

    assert out == []
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_CANDIDATE_REJECTED market_id=562010" in payload
    assert "reject_reason=WIDE_SPREAD" in payload


def test_mm_scan_runs_without_arb_candidates(caplog) -> None:
    agent = ScoutAgent()
    markets = [Market(market_id="562011", slug="solo-market", title="Solo market")]

    class _Provider:
        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return {
                "562011": {
                    "best_bid": 0.40,
                    "best_ask": 0.41,
                    "bids_json": '[{"price":0.40,"size":10}]',
                    "asks_json": '[{"price":0.41,"size":10}]',
                }
            }.get(market_id, {})

        def list_open_positions(self):
            return []

    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=_Provider(),
    )

    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        out = agent._propose(ctx)

    assert all(str(s.claim.get("strategy") or "").upper() != "ARB" for s in out)
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_SCAN_START raw_markets_count=1 eligible_markets_count=1 live_mode=true" in payload
    assert ("MM_CANDIDATE_FOUND" in payload) or ("MM_CANDIDATE_REJECTED" in payload)


def test_mm_market_prefilter_excludes_dead_books(caplog) -> None:
    agent = ScoutAgent()
    markets = [
        Market(market_id="562020", slug="dead-1", title="Dead 1"),
        Market(market_id="562021", slug="dead-2", title="Dead 2"),
        Market(market_id="562022", slug="ok", title="OK"),
    ]

    class _Provider:
        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return {
                "562020": {},
                "562021": {"best_bid": None, "best_ask": None},
                "562022": {
                    "best_bid": 0.40,
                    "best_ask": 0.46,
                    "bids_json": '[{"price":0.40,"size":12}]',
                    "asks_json": '[{"price":0.46,"size":8}]',
                },
            }.get(market_id, {})

        def list_open_positions(self):
            return []

    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=_Provider(),
    )

    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        filtered = agent._filter_mm_live_eligible_markets(markets, ctx)

    assert [m.market_id for m in filtered] == ["562022"]
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert payload.count("MM_MARKET_INELIGIBLE") == 2
    assert "market_id=562020 reason=MISSING_BOOK" in payload
    assert "market_id=562021 reason=MISSING_BOOK" in payload


def test_mm_one_sided_candidate_detection_with_ask_only(caplog, monkeypatch) -> None:
    agent = ScoutAgent()
    markets = [Market(market_id="562023", slug="ask-only", title="Ask only")]

    class _Provider:
        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return {
                "562023": {
                    "best_bid": None,
                    "best_ask": 0.46,
                    "asks_json": '[{"price":0.46,"size":8}]',
                }
            }.get(market_id, {})

        def list_open_positions(self):
            return []

    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=_Provider(),
    )
    monkeypatch.setenv("PS_MM_MAX_ASK", "0.999")
    monkeypatch.setenv("PS_MM_MAX_SPREAD", "0.35")

    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        out = agent._propose(ctx)

    mm = [s for s in out if str(s.claim.get("strategy") or "").upper() == "MM"]
    assert len(mm) == 1
    assert mm[0].claim["quote_mode"] == "ASK_ONLY"
    assert mm[0].claim["post_side"] == "BUY"
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_CANDIDATE_FOUND market_id=562023" in payload


def test_mm_market_prefilter_respects_mm_thresholds(monkeypatch, caplog) -> None:
    agent = ScoutAgent()
    markets = [
        Market(market_id="562030", slug="boundary", title="Boundary"),
        Market(market_id="562031", slug="wide", title="Wide"),
        Market(market_id="562032", slug="good", title="Good"),
    ]

    class _Provider:
        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return {
                "562030": {"best_bid": 0.02, "best_ask": 0.40, "bids_json": '[{"price":0.02,"size":10}]', "asks_json": '[{"price":0.40,"size":10}]'},
                "562031": {"best_bid": 0.30, "best_ask": 0.60, "bids_json": '[{"price":0.30,"size":10}]', "asks_json": '[{"price":0.60,"size":10}]'},
                "562032": {"best_bid": 0.40, "best_ask": 0.46, "bids_json": '[{"price":0.40,"size":10}]', "asks_json": '[{"price":0.46,"size":10}]'},
            }.get(market_id, {})

        def list_open_positions(self):
            return []

    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=_Provider(),
    )
    monkeypatch.setenv("PS_MM_MIN_BID", "0.02")
    monkeypatch.setenv("PS_MM_MAX_ASK", "0.98")
    monkeypatch.setenv("PS_MM_MAX_SPREAD", "0.20")

    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        filtered = agent._filter_mm_live_eligible_markets(markets, ctx)

    assert [m.market_id for m in filtered] == ["562032"]
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "market_id=562030 reason=BOUNDARY_BOOK" in payload
    assert "market_id=562031 reason=WIDE_SPREAD" in payload


def test_mm_scan_start_reports_filtered_counts(caplog) -> None:
    agent = ScoutAgent()
    raw_markets = [
        Market(market_id="562040", slug="dead", title="Dead"),
        Market(market_id="562041", slug="good", title="Good"),
    ]
    eligible_markets = [raw_markets[1]]

    class _Provider:
        def list_markets(self, limit: int = 500):
            return list(raw_markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return {
                "562041": {
                    "best_bid": 0.40,
                    "best_ask": 0.46,
                    "bids_json": '[{"price":0.40,"size":10}]',
                    "asks_json": '[{"price":0.46,"size":10}]',
                }
            }.get(market_id, {})

        def list_open_positions(self):
            return []

    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=_Provider(),
    )

    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        agent._find_mm_candidates(raw_markets, eligible_markets, ctx)

    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_SCAN_START raw_markets_count=2 eligible_markets_count=1 live_mode=true" in payload


def test_mm_live_score_stable_market_is_eligible(caplog) -> None:
    agent = ScoutAgent()
    markets = [Market(market_id="562100", slug="stable", title="Stable")]

    class _Provider:
        book = {
            "best_bid": 0.40,
            "best_ask": 0.46,
            "bids_json": '[{"price":0.40,"size":12}]',
            "asks_json": '[{"price":0.46,"size":8}]',
        }

        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return dict(self.book)

        def list_open_positions(self):
            return []

    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=_Provider(),
    )

    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        filtered = []
        for _ in range(10):
            filtered = agent._filter_mm_live_eligible_markets(markets, ctx)

    assert [m.market_id for m in filtered] == ["562100"]
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_LIVE_SCORE market_id=562100" in payload
    assert "eligible=1" in payload


def test_mm_live_score_rejects_repeated_missing_book_history(caplog) -> None:
    agent = ScoutAgent()
    markets = [Market(market_id="562101", slug="missing", title="Missing")]

    class _Provider:
        def __init__(self) -> None:
            self.book = {}

        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return dict(self.book)

        def list_open_positions(self):
            return []

    provider = _Provider()
    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=provider,
    )

    for _ in range(5):
        provider.book = {}
        agent._filter_mm_live_eligible_markets(markets, ctx)

    provider.book = {
        "best_bid": 0.40,
        "best_ask": 0.46,
        "bids_json": '[{"price":0.40,"size":12}]',
        "asks_json": '[{"price":0.46,"size":8}]',
    }
    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        filtered = agent._filter_mm_live_eligible_markets(markets, ctx)

    assert filtered == []
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_LIVE_SCORE market_id=562101" in payload
    assert "eligible=0" in payload
    assert "MM_LIVE_MARKET_REJECTED market_id=562101 reason=LIVE_SCORE_TOO_LOW" in payload


def test_mm_live_score_rejects_repeated_boundary_book_history(caplog) -> None:
    agent = ScoutAgent()
    markets = [Market(market_id="562102", slug="boundary", title="Boundary")]

    class _Provider:
        def __init__(self) -> None:
            self.book = {}

        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return dict(self.book)

        def list_open_positions(self):
            return []

    provider = _Provider()
    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=provider,
    )

    for _ in range(5):
        provider.book = {
            "best_bid": 0.40,
            "best_ask": 0.999,
            "bids_json": '[{"price":0.40,"size":12}]',
            "asks_json": '[{"price":0.999,"size":8}]',
        }
        agent._filter_mm_live_eligible_markets(markets, ctx)

    provider.book = {
        "best_bid": 0.40,
        "best_ask": 0.46,
        "bids_json": '[{"price":0.40,"size":12}]',
        "asks_json": '[{"price":0.46,"size":8}]',
    }
    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        filtered = agent._filter_mm_live_eligible_markets(markets, ctx)

    assert filtered == []
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_LIVE_SCORE market_id=562102" in payload
    assert "eligible=0" in payload
    assert "MM_LIVE_MARKET_REJECTED market_id=562102 reason=LIVE_SCORE_TOO_LOW" in payload


def test_mm_live_score_rejects_high_spread_history(caplog) -> None:
    agent = ScoutAgent()
    markets = [Market(market_id="562103", slug="wide", title="Wide")]

    class _Provider:
        def __init__(self) -> None:
            self.book = {}

        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return dict(self.book)

        def list_open_positions(self):
            return []

    provider = _Provider()
    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=provider,
    )

    for _ in range(5):
        provider.book = {
            "best_bid": 0.30,
            "best_ask": 0.60,
            "bids_json": '[{"price":0.30,"size":12}]',
            "asks_json": '[{"price":0.60,"size":8}]',
        }
        agent._filter_mm_live_eligible_markets(markets, ctx)

    provider.book = {
        "best_bid": 0.40,
        "best_ask": 0.46,
        "bids_json": '[{"price":0.40,"size":12}]',
        "asks_json": '[{"price":0.46,"size":8}]',
    }
    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        filtered = agent._filter_mm_live_eligible_markets(markets, ctx)

    assert filtered == []
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_LIVE_SCORE market_id=562103" in payload
    assert "eligible=0" in payload
    assert "MM_LIVE_MARKET_REJECTED market_id=562103 reason=LIVE_SCORE_TOO_LOW" in payload


def test_mm_live_score_warmup_allows_market_but_logs(caplog) -> None:
    agent = ScoutAgent()
    markets = [Market(market_id="562104", slug="warmup", title="Warmup")]

    class _Provider:
        def list_markets(self, limit: int = 500):
            return list(markets)

        def get_latest_snapshots(self, market_id: str):
            return {}

        def get_latest_orderbook(self, market_id: str):
            return {
                "best_bid": 0.40,
                "best_ask": 0.46,
                "bids_json": '[{"price":0.40,"size":12}]',
                "asks_json": '[{"price":0.46,"size":8}]',
            }

        def list_open_positions(self):
            return []

    ctx = AgentContext(
        run_id="run-test",
        now=SimpleNamespace(),
        repo=object(),
        settings=SimpleNamespace(execution_mode="live_stage0", live_exec_style="human_limit"),
        data_provider=_Provider(),
    )

    with caplog.at_level(logging.INFO, logger="agent.scout.v2"):
        filtered = []
        for _ in range(4):
            filtered = agent._filter_mm_live_eligible_markets(markets, ctx)

    assert [m.market_id for m in filtered] == ["562104"]
    payload = "\n".join(r.getMessage() for r in caplog.records)
    assert "MM_LIVE_SCORE_WARMUP market_id=562104" in payload
