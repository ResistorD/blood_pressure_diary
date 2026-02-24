from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from db.repo import Repo
from ingest.polymarket_client import PolymarketClient, _http_json, CLOB_BASE


def _parse_level(x: Any) -> Optional[Tuple[float, float]]:
    try:
        if isinstance(x, dict):
            px = x.get("price")
            sz = x.get("size") or x.get("quantity") or x.get("amount")
            if px is None or sz is None:
                return None
            return float(px), float(sz)
        if isinstance(x, (list, tuple)) and len(x) >= 2:
            return float(x[0]), float(x[1])
    except Exception:
        return None
    return None


def _normalize_levels(raw: Iterable[Any], *, max_levels: int) -> List[Dict[str, float]]:
    out: List[Dict[str, float]] = []
    for item in raw:
        parsed = _parse_level(item)
        if not parsed:
            continue
        px, sz = parsed
        if sz <= 0:
            continue
        out.append({"price": px, "size": sz})
        if len(out) >= max_levels:
            break
    return out


def _best_from_levels(levels: List[Dict[str, float]], *, side: str) -> Optional[float]:
    if not levels:
        return None
    if side == "bid":
        return max(x["price"] for x in levels)
    return min(x["price"] for x in levels)


class OrderbookCollector:
    def __init__(
        self,
        repo: Repo,
        client: PolymarketClient,
        *,
        max_levels: int = 30,
        retention_minutes: int = 180,
        keep_per_market: int = 200,
    ):
        self.repo = repo
        self.client = client
        self.max_levels = int(max_levels)
        self.retention_minutes = int(retention_minutes)
        self.keep_per_market = int(keep_per_market)
        self.last_book_ts: Dict[str, str] = {}

    def _token_id_for_market(self, market_row: Dict[str, Any]) -> Optional[str]:
        tokens = market_row.get("tokens") or []
        pick = None
        for t in tokens:
            outcome = str(t.get("outcome") or t.get("name") or "").upper()
            if outcome == "YES":
                pick = t
                break
        if pick is None and tokens:
            pick = tokens[0]
        if not pick:
            return None
        tid = pick.get("token_id") or pick.get("tokenId") or pick.get("id")
        return str(tid) if tid is not None else None

    def _fetch_market_rows_map(self) -> Dict[str, Dict[str, Any]]:
        rows = self.client._fetch_market_rows()
        return {str(r.get("id") or r.get("marketId")): r for r in rows if isinstance(r, dict)}

    def collect(self, market_ids: Iterable[str]) -> Dict[str, Any]:
        ids = [str(x) for x in market_ids if x]
        if not ids:
            return {"total": 0, "inserted": 0, "errors": 0}
        rows_map = self._fetch_market_rows_map()
        inserted = 0
        errors = 0
        for market_id in ids:
            row = rows_map.get(market_id)
            if not row:
                errors += 1
                continue
            token_id = self._token_id_for_market(row)
            if not token_id:
                errors += 1
                continue
            try:
                book = _http_json(
                    "GET",
                    f"{CLOB_BASE}/book",
                    params={"token_id": str(token_id)},
                    policy=self.client.http_policy,
                    limiter=self.client.clob_limiter,
                )
                bids_raw = (book or {}).get("bids") or []
                asks_raw = (book or {}).get("asks") or []
                bids = _normalize_levels(bids_raw, max_levels=self.max_levels)
                asks = _normalize_levels(asks_raw, max_levels=self.max_levels)
                best_bid = _best_from_levels(bids, side="bid")
                best_ask = _best_from_levels(asks, side="ask")
                mid = None
                if best_bid is not None and best_ask is not None:
                    mid = (best_bid + best_ask) / 2.0
                ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                self.repo.insert_orderbook_snapshot(
                    market_id=market_id,
                    ts_utc=ts,
                    best_bid=best_bid,
                    best_ask=best_ask,
                    mid=mid,
                    bids_json=json.dumps(bids, ensure_ascii=False),
                    asks_json=json.dumps(asks, ensure_ascii=False),
                    retention_minutes=self.retention_minutes,
                    keep_per_market=self.keep_per_market,
                )
                self.last_book_ts[market_id] = ts
                inserted += 1
            except Exception:
                errors += 1
                continue
        last = {mid: self.last_book_ts.get(mid) for mid in ids if mid in self.last_book_ts}
        return {"total": len(ids), "inserted": inserted, "errors": errors, "last_book_ts": last}
