from __future__ import annotations

from typing import List, Tuple
import logging
import json

from db.repo import Repo
from domain.models import Market, Snapshot
from .polymarket_client import PolymarketClient, _extract_tokens_from_row


class Ingestor:
    def __init__(self, repo: Repo, client: PolymarketClient):
        self.repo = repo
        self.client = client
        self.logger = logging.getLogger(__name__)

    def ingest(self) -> Tuple[int, int]:
        markets, market_rows = self.client.fetch_universe_markets()
        for m in markets:
            self.repo.upsert_market(m)

        rows = market_rows or []
        missing_ids = []
        for row in rows:
            tokens = _extract_tokens_from_row(row)
            if tokens:
                row["tokens"] = tokens
            else:
                mid = str(row.get("id") or row.get("marketId") or "")
                if mid:
                    missing_ids.append(mid)
        if missing_ids:
            try:
                qmarks = ",".join(["?"] * len(missing_ids))
                with self.repo.conn() as con:
                    raw_rows = con.execute(
                        f"SELECT market_id, raw_json FROM markets WHERE market_id IN ({qmarks})",
                        tuple(missing_ids),
                    ).fetchall()
                raw_map = {r["market_id"]: r["raw_json"] for r in raw_rows or []}
                for row in rows:
                    mid = str(row.get("id") or row.get("marketId") or "")
                    if not mid or row.get("tokens"):
                        continue
                    raw_json = raw_map.get(mid) or ""
                    if not raw_json:
                        continue
                    try:
                        raw = json.loads(raw_json)
                    except Exception:
                        continue
                    tokens = _extract_tokens_from_row(raw)
                    if tokens:
                        row["tokens"] = tokens
            except Exception:
                self.logger.exception("failed to hydrate tokens from DB")

        snaps = self.client.fetch_snapshots(market_rows=rows)
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
