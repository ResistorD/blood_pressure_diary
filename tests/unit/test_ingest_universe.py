from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

from domain.models import Market, Snapshot
from ingest.ingestor import Ingestor
from ingest.polymarket_client import HttpPolicy, _http_json, _select_universe_rows


def test_select_universe_topn_and_expiry():
    now = datetime(2026, 2, 18, tzinfo=timezone.utc)
    near = (now + timedelta(days=5)).isoformat()
    far = (now + timedelta(days=400)).isoformat()

    rows = [
        {"id": "m1", "endDate": near, "volumeNum": 10, "volume24hr": 5, "liquidityNum": 50},
        {"id": "m2", "endDate": near, "volumeNum": 90, "volume24hr": 20, "liquidityNum": 30},
        {"id": "m3", "endDate": near, "volumeNum": 70, "volume24hr": 80, "liquidityNum": 40},
        {"id": "m4", "endDate": far, "volumeNum": 999, "volume24hr": 999, "liquidityNum": 999},
    ]

    selected = _select_universe_rows(rows, top_n=2, max_expiry_days=30, now=now)
    ids = [x["id"] for x in selected]

    assert ids == ["m2", "m3"]


def test_http_json_retries_with_retry_after(monkeypatch):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def read(self):
            return b'{"ok": true}'

    calls = {"n": 0}
    sleeps: list[float] = []

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise HTTPError(req.full_url, 429, "rate limited", {"Retry-After": "0.2"}, None)
        return _Resp()

    monkeypatch.setattr("ingest.polymarket_client.urlopen", fake_urlopen)
    monkeypatch.setattr("ingest.polymarket_client.time.sleep", lambda sec: sleeps.append(sec))

    out = _http_json("GET", "https://example.test/api", policy=HttpPolicy(retries=3, backoff_base_sec=0.1))
    assert out["ok"] is True
    assert calls["n"] == 2
    assert sleeps == [0.2]


def test_ingestor_uses_selected_universe():
    class _Repo:
        def __init__(self):
            self.markets = []
            self.snapshots = []

        def upsert_market(self, m):
            self.markets.append(m.market_id)

        def insert_snapshots(self, snaps):
            self.snapshots.extend(snaps)
            return len(snaps)

    class _Client:
        def __init__(self):
            self.rows = [{"id": "m1", "tokens": [{"outcome": "YES", "token_id": "t1"}]}]
            self.got_rows = None
            self.got_hot_ids = None

        def fetch_universe_markets(self):
            return [
                Market(market_id="m1", slug="m1", title="M1", close_time=None, group_key="g1"),
            ], self.rows

        def fetch_snapshots(self, market_rows=None, hot_market_ids=None):
            self.got_rows = market_rows
            self.got_hot_ids = set(hot_market_ids or set())
            return [
                Snapshot(ts=datetime.now(timezone.utc), market_id="m1", outcome="YES", mid=0.5),
            ]

    class _CaseRepo(_Repo):
        def list_cases(self, minutes_signals=30, minutes_snaps=10):
            return [{"market_id": "m1"}]

    repo = _CaseRepo()
    client = _Client()
    ingestor = Ingestor(repo, client)  # type: ignore[arg-type]

    m_cnt, s_cnt = ingestor.ingest()
    assert m_cnt == 1
    assert s_cnt == 1
    assert repo.markets == ["m1"]
    assert client.got_rows == client.rows
    assert client.got_hot_ids == {"m1"}


def test_ingestor_hot_market_ids_fallback_on_list_cases_error():
    class _Repo:
        def upsert_market(self, _m):
            return None

        def insert_snapshots(self, snaps):
            return len(snaps)

        def list_cases(self, minutes_signals=30, minutes_snaps=10):
            raise RuntimeError("list_cases broken")

    class _Client:
        def __init__(self):
            self.hot_ids = None

        def fetch_universe_markets(self):
            return [
                Market(market_id="m1", slug="m1", title="M1", close_time=None, group_key="g1"),
            ], [{"id": "m1", "tokens": [{"outcome": "YES", "token_id": "t1"}]}]

        def fetch_snapshots(self, market_rows=None, hot_market_ids=None):
            self.hot_ids = set(hot_market_ids or set())
            return [Snapshot(ts=datetime.now(timezone.utc), market_id="m1", outcome="YES", mid=0.5)]

    ingestor = Ingestor(_Repo(), _Client())  # type: ignore[arg-type]
    _m_cnt, s_cnt = ingestor.ingest()
    assert s_cnt == 1
    assert ingestor.client.hot_ids == set()
