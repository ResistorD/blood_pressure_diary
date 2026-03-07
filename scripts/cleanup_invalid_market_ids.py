#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import _resolve_db_path
from app.settings import load_settings
from ingest.polymarket_client import is_valid_market_detail_id


def _db_path(cli_db: str | None) -> str:
    if cli_db:
        return cli_db
    settings = load_settings()
    return _resolve_db_path(settings)


def _find_invalid_ids(con: sqlite3.Connection) -> List[str]:
    rows = con.execute(
        """
        SELECT market_id
        FROM markets
        WHERE market_id IS NOT NULL
          AND trim(market_id) <> ''
          AND (raw_json IS NULL OR length(raw_json)=0 OR trim(raw_json)='')
        ORDER BY market_id
        """
    ).fetchall()
    out: List[str] = []
    for (mid,) in rows:
        m = str(mid or "").strip()
        if m and not is_valid_market_detail_id(m):
            out.append(m)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find/delete invalid market_ids with empty raw_json in markets table."
    )
    parser.add_argument("--db", default=None, help="Path to sqlite DB (default: app settings)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete offending rows. Default is dry-run (print only).",
    )
    args = parser.parse_args()

    db_path = _db_path(args.db)
    con = sqlite3.connect(db_path)
    try:
        invalid = _find_invalid_ids(con)
        print(f"db={db_path}")
        print(f"invalid_empty_raw_json_count={len(invalid)}")
        if invalid:
            print("ids=" + ",".join(invalid))
        if not args.apply:
            print("mode=DRY_RUN (no changes)")
            return 0
        if not invalid:
            print("mode=APPLY deleted=0")
            return 0
        q = ",".join(["?"] * len(invalid))
        with con:
            con.execute(f"DELETE FROM markets WHERE market_id IN ({q})", tuple(invalid))
        print(f"mode=APPLY deleted={len(invalid)}")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
