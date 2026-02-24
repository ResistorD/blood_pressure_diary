from __future__ import annotations

from typing import List, Tuple
import logging

from db.repo import Repo
from domain.models import Market, Snapshot
from .polymarket_client import PolymarketClient


class Ingestor:
    def __init__(self, repo: Repo, client: PolymarketClient):
        self.repo = repo
        self.client = client
        self.logger = logging.getLogger(__name__)

    def ingest(self) -> Tuple[int, int]:
        markets, market_rows = self.client.fetch_universe_markets()
        for m in markets:
            self.repo.upsert_market(m)

        snaps = self.client.fetch_snapshots(market_rows=market_rows)
        inserted = 0
        db_errors = 0
        try:
            inserted = self.repo.insert_snapshots(snaps)
        except Exception:
            db_errors = len(snaps)
            inserted = 0
            self.logger.exception("snapshots db insert failed")
        stats = getattr(self.client, "last_snapshot_stats", {}) or {}
        stats["inserted"] = inserted
        stats["db_errors"] = db_errors
        if stats:
            self.logger.info(
                "ingest_stats: markets=%s tokens=%s fetched_ok=%s fetched_err=%s parsed=%s inserted=%s db_errors=%s missing_token=%s missing_outcome=%s http403=%s http429=%s other=%s exc=%s",
                stats.get("markets"),
                stats.get("tokens"),
                stats.get("fetched_ok"),
                stats.get("fetched_err"),
                stats.get("parsed"),
                stats.get("inserted"),
                stats.get("db_errors"),
                stats.get("missing_token"),
                stats.get("missing_outcome"),
                stats.get("http_403"),
                stats.get("http_429"),
                stats.get("http_other"),
                stats.get("exceptions"),
            )
            if stats.get("error_samples"):
                self.logger.warning("ingest_errors: %s", stats.get("error_samples"))
        return len(markets), inserted
