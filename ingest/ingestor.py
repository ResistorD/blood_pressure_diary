from __future__ import annotations

from typing import List, Tuple

from db.repo import Repo
from domain.models import Market, Snapshot
from .polymarket_client import PolymarketClient


class Ingestor:
    def __init__(self, repo: Repo, client: PolymarketClient):
        self.repo = repo
        self.client = client

    def ingest(self) -> Tuple[int, int]:
        markets, market_rows = self.client.fetch_universe_markets()
        for m in markets:
            self.repo.upsert_market(m)

        snaps = self.client.fetch_snapshots(market_rows=market_rows)
        inserted = self.repo.insert_snapshots(snaps)
        return len(markets), inserted
