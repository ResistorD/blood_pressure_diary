from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Iterable, Tuple
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.settings import load_settings
from db.repo import Repo


logger = logging.getLogger("tools.backfill_markets")
GAMMA_BASE = "https://gamma-api.polymarket.com"


def _fetch_gamma_detail(market_id: str) -> Tuple[int | None, str, bool]:
    url = f"{GAMMA_BASE}/markets/{market_id}"
    try:
        req = Request(
            url=url,
            method="GET",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, raw, True
    except HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        return e.code, raw, False
    except Exception:
        return None, "", False


def backfill_raw_json_for_ids(repo: Repo, ids: Iterable[str]) -> None:
    for market_id in ids:
        status, raw, ok = _fetch_gamma_detail(str(market_id))
        bytes_len = len(raw.encode("utf-8")) if raw else 0
        parse_ok = False
        has_tokens = False
        data = None
        if raw:
            try:
                data = json.loads(raw)
                parse_ok = isinstance(data, dict)
                if parse_ok:
                    has_tokens = False
                    tokens = data.get("tokens") or []
                    if isinstance(tokens, list) and tokens:
                        has_tokens = True
                    clob_ids = data.get("clobTokenIds") or data.get("clob_token_ids") or []
                    if isinstance(clob_ids, list) and len(clob_ids) > 0:
                        has_tokens = True
                    if data.get("yesTokenId") or data.get("noTokenId"):
                        has_tokens = True
            except Exception:
                parse_ok = False
        logger.info(
            "gamma detail: market_id=%s http_status=%s bytes=%s has_clobTokenIds=%s parse_ok=%s",
            market_id,
            status,
            bytes_len,
            has_tokens,
            parse_ok,
        )
        if not parse_ok or data is None:
            continue
        try:
            raw_json = json.dumps(data, ensure_ascii=False)
            with repo.conn() as con:
                con.execute(
                    "UPDATE markets SET raw_json=? WHERE market_id=?",
                    (raw_json, market_id),
                )
                row = con.execute(
                    "SELECT length(raw_json) AS n FROM markets WHERE market_id=?",
                    (market_id,),
                ).fetchone()
            new_len = int(row["n"] or 0) if row else 0
            logger.info(
                "raw_json updated: market_id=%s rows_updated=%s new_raw_len=%s",
                market_id,
                1,
                new_len,
            )
        except Exception:
            logger.exception("raw_json update failed: market_id=%s", market_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", required=True, help="Comma-separated market ids")
    args = parser.parse_args()

    ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    if not ids:
        logger.error("no ids provided")
        return

    settings = load_settings()
    db_path = os.path.abspath(getattr(settings, "db_path", "polysyndicate.db"))
    logger.info("DB path: %s", db_path)
    repo = Repo(db_path)
    repo.init_schema("db/schema.sql")
    backfill_raw_json_for_ids(repo, ids)


if __name__ == "__main__":
    main()
