from __future__ import annotations

from typing import List, Tuple
import logging
import json
import time
import os

from db.repo import Repo
from domain.models import Market, Snapshot
from .polymarket_client import PolymarketClient, _extract_tokens_from_row


class Ingestor:
    def __init__(self, repo: Repo, client: PolymarketClient):
        self.repo = repo
        self.client = client
        self.logger = logging.getLogger(__name__)
        self._backfill_queue: list[str] = []

    def enqueue_backfill_market(self, market_id: str) -> bool:
        mid = str(market_id or "").strip()
        if not mid:
            return False
        if mid in self._backfill_queue:
            return False
        self._backfill_queue.append(mid)
        return True

    def ingest(self) -> Tuple[int, int]:
        t_total0 = time.perf_counter()
        fetch_ms = 0.0
        parse_ms = 0.0
        db_ms = 0.0
        fetch_market_detail_ms = 0.0
        fetch_universe_markets_ms = 0.0
        fetch_snapshots_ms = 0.0
        calls_market_detail = 0
        calls_universe_markets = 0
        calls_snapshots = 0
        try:
            max_snaps_on_neterr = int(os.getenv("PS_INGEST_MAX_SNAPSHOTS_ON_NETERR", "0") or 0)
        except Exception:
            max_snaps_on_neterr = 0
        BACKFILL_MAX = 10
        BACKFILL_TTL_SEC = 600
        backfill_ids: list[str] = []
        if self._backfill_queue:
            for mid in self._backfill_queue:
                if mid not in backfill_ids:
                    backfill_ids.append(mid)
            self._backfill_queue = []
        try:
            with self.repo.conn() as con:
                rows = con.execute(
                    """
                    SELECT market_id
                    FROM markets
                    WHERE raw_json IS NULL OR length(raw_json)=0 OR trim(raw_json)=''
                    LIMIT ?
                    """,
                    (BACKFILL_MAX,),
                ).fetchall()
            backfill_ids = [r["market_id"] for r in rows or [] if r["market_id"]]
        except Exception:
            backfill_ids = []

        attempted = 0
        ok = 0
        err = 0
        sample = []
        now_mono = time.monotonic()
        for mid in backfill_ids:
            last = self.client._backfill_cache.get(mid)
            if last and now_mono - last < BACKFILL_TTL_SEC:
                continue
            self.client._backfill_cache[mid] = now_mono
            attempted += 1
            if len(sample) < 5:
                sample.append(mid)
            t_f0 = time.perf_counter()
            calls_market_detail += 1
            detail = self.client.fetch_market_detail(mid)
            dt_ms = (time.perf_counter() - t_f0) * 1000.0
            fetch_ms += dt_ms
            fetch_market_detail_ms += dt_ms
            if not detail:
                err += 1
                continue
            try:
                raw_json = json.dumps(detail, ensure_ascii=False)
                t_db0 = time.perf_counter()
                with self.repo.conn() as con:
                    con.execute(
                        "UPDATE markets SET raw_json=? WHERE market_id=?",
                        (raw_json, mid),
                    )
                db_ms += (time.perf_counter() - t_db0) * 1000.0
                ok += 1
            except Exception:
                err += 1
        if attempted:
            self.logger.info(
                "backfill raw_json: candidates=%s attempted=%s ok=%s err=%s sample=%s",
                len(backfill_ids),
                attempted,
                ok,
                err,
                sample,
            )

        t_f0 = time.perf_counter()
        calls_universe_markets += 1
        try:
            markets, market_rows = self.client.fetch_universe_markets()
        except Exception:
            self.logger.info(
                "INGEST_DEGRADED neterr=%s max_snaps=%s snaps_before=%s snaps_after=%s",
                0,
                max_snaps_on_neterr,
                0,
                0,
            )
            raise
        dt_ms = (time.perf_counter() - t_f0) * 1000.0
        fetch_ms += dt_ms
        fetch_universe_markets_ms += dt_ms
        t_db0 = time.perf_counter()
        for m in markets:
            self.repo.upsert_market(m)
        db_ms += (time.perf_counter() - t_db0) * 1000.0

        t_p0 = time.perf_counter()
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
        parse_ms += (time.perf_counter() - t_p0) * 1000.0
        if missing_ids:
            try:
                qmarks = ",".join(["?"] * len(missing_ids))
                t_db0 = time.perf_counter()
                with self.repo.conn() as con:
                    raw_rows = con.execute(
                        f"SELECT market_id, raw_json FROM markets WHERE market_id IN ({qmarks})",
                        tuple(missing_ids),
                    ).fetchall()
                db_ms += (time.perf_counter() - t_db0) * 1000.0
                raw_map = {r["market_id"]: r["raw_json"] for r in raw_rows or []}
                t_p0 = time.perf_counter()
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
                parse_ms += (time.perf_counter() - t_p0) * 1000.0
            except Exception:
                self.logger.exception("failed to hydrate tokens from DB")

        t_f0 = time.perf_counter()
        calls_snapshots += 1
        try:
            snaps = self.client.fetch_snapshots(market_rows=rows)
        except Exception:
            self.logger.info(
                "INGEST_DEGRADED neterr=%s max_snaps=%s snaps_before=%s snaps_after=%s",
                0,
                max_snaps_on_neterr,
                0,
                0,
            )
            raise
        dt_ms = (time.perf_counter() - t_f0) * 1000.0
        fetch_ms += dt_ms
        fetch_snapshots_ms += dt_ms
        fetch_stats = getattr(self.client, "last_snapshot_stats", {}) or {}
        retry_count = int(fetch_stats.get("retries", fetch_stats.get("retry_count", 0)) or 0)
        fetch_err_count = int(err or 0) + int(fetch_stats.get("fetched_err", 0) or 0)
        snaps_before = len(snaps)
        neterr_observed = (
            int(err or 0) > 0
            or int(fetch_stats.get("fetched_err", 0) or 0) > 0
            or int(fetch_stats.get("http_other", 0) or 0) > 0
            or int(fetch_stats.get("exceptions", 0) or 0) > 0
        )
        if max_snaps_on_neterr > 0 and neterr_observed and snaps_before > max_snaps_on_neterr:
            snaps = snaps[:max_snaps_on_neterr]
        snaps_after = len(snaps)
        neterr_active = 1 if (max_snaps_on_neterr > 0 and neterr_observed and snaps_after < snaps_before) else 0
        self.logger.info(
            "INGEST_DEGRADED neterr=%s max_snaps=%s snaps_before=%s snaps_after=%s",
            neterr_active,
            max_snaps_on_neterr,
            snaps_before,
            snaps_after,
        )
        self.logger.info(
            "INGEST_FETCH_DETAIL market_detail=%.0fms(calls=%s) universe=%.0fms(calls=%s) snapshots=%.0fms(calls=%s) retries=%s fetch_err=%s",
            fetch_market_detail_ms,
            calls_market_detail,
            fetch_universe_markets_ms,
            calls_universe_markets,
            fetch_snapshots_ms,
            calls_snapshots,
            retry_count,
            fetch_err_count,
        )
        inserted = 0
        db_errors = 0
        try:
            t_db0 = time.perf_counter()
            inserted = self.repo.insert_snapshots(snaps)
            db_ms += (time.perf_counter() - t_db0) * 1000.0
        except Exception:
            db_ms += (time.perf_counter() - t_db0) * 1000.0
            db_errors = len(snaps)
            inserted = 0
            self.logger.exception("snapshots db insert failed")
        stats = getattr(self.client, "last_snapshot_stats", {}) or {}
        stats["inserted"] = inserted
        stats["db_errors"] = db_errors
        fetched_n = int(stats.get("fetched_ok", 0) or 0)
        parsed_n = int(stats.get("parsed", 0) or 0)
        inserted_n = int(inserted or 0)
        err_n = int(stats.get("fetched_err", 0) or 0) + int(db_errors or 0) + int(stats.get("exceptions", 0) or 0)
        total_ms = (time.perf_counter() - t_total0) * 1000.0
        other_ms = max(0.0, total_ms - (fetch_ms + parse_ms + db_ms))
        self.logger.info(
            "INGEST_PHASES_DETAIL fetch=%.0fms parse=%.0fms db=%.0fms other=%.0fms total=%.0fms fetched=%s parsed=%s inserted=%s err=%s",
            fetch_ms,
            parse_ms,
            db_ms,
            other_ms,
            total_ms,
            fetched_n,
            parsed_n,
            inserted_n,
            err_n,
        )
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
