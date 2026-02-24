from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from domain.models import Market, Snapshot


GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HttpPolicy:
    timeout_sec: int = 20
    retries: int = 4
    backoff_base_sec: float = 0.35
    backoff_cap_sec: float = 5.0


class RateLimiter:
    """Simple thread-safe per-host rate limiter."""

    def __init__(self, rate_per_sec: float):
        self._min_interval = (1.0 / rate_per_sec) if rate_per_sec > 0 else 0.0
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                time.sleep(self._next_allowed - now)
                now = time.monotonic()
            self._next_allowed = max(self._next_allowed, now) + self._min_interval


def _parse_retry_after(exc: HTTPError) -> Optional[float]:
    try:
        header = exc.headers.get("Retry-After") if exc.headers else None
        if not header:
            return None
        return max(0.0, float(header))
    except (ValueError, AttributeError, TypeError):
        return None


def _http_json(
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    policy: Optional[HttpPolicy] = None,
    limiter: Optional[RateLimiter] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Any:
    p = policy or HttpPolicy()
    attempts = max(1, int(p.retries))
    if params:
        qs = urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{qs}"
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        if limiter is not None:
            limiter.wait()
        try:
            req = Request(
                url=url,
                method=method,
                headers={
                    # Polymarket sometimes blocks "generic" clients; a simple UA helps avoid 403.
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Accept": "application/json,text/plain,*/*",
                    **(headers or {}),
                },
            )
            with urlopen(req, timeout=p.timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except HTTPError as e:
            last_err = e
            # Explicitly back off on anti-bot/rate-limit style responses.
            if e.code not in {403, 429, 500, 502, 503, 504}:
                break
            retry_after = _parse_retry_after(e)
            delay = retry_after if retry_after is not None else min(
                p.backoff_cap_sec,
                p.backoff_base_sec * (2 ** (attempt - 1)),
            )
            time.sleep(delay)
        except Exception as e:
            last_err = e
            delay = min(
                p.backoff_cap_sec,
                p.backoff_base_sec * (2 ** (attempt - 1)),
            )
            time.sleep(delay)
    raise last_err or RuntimeError("HTTP failed")


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9\-\s]", "", s)
    return s


def _bucket_close_time(close_time: Optional[str]) -> str:
    # make clusters less fragmented: bucket by YYYY-MM (good enough for demo)
    if not close_time:
        return "na"
    try:
        dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m")
    except (ValueError, TypeError):
        return "na"


def _parse_close_time(close_time: Any) -> Optional[datetime]:
    if close_time in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(close_time).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _num(raw: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        try:
            v = raw.get(key)
            if v is None or v == "":
                continue
            return float(v)
        except (ValueError, TypeError):
            continue
    return default


def _to_market(raw: Dict[str, Any]) -> Optional[Market]:
    market_id = str(raw.get("id") or raw.get("marketId") or "")
    if not market_id:
        return None
    slug = str(raw.get("slug") or "")
    title = str(raw.get("question") or raw.get("title") or slug or market_id)
    close_time_raw = raw.get("endDate") or raw.get("closeTime") or raw.get("close_time")
    market_group = raw.get("marketGroup") or raw.get("market_group") or raw.get("marketGroupId")
    condition_id = raw.get("conditionId") or raw.get("condition_id")
    question_id = raw.get("questionID") or raw.get("questionId") or raw.get("question_id")
    group_key = _make_group_key(market_group, condition_id, question_id, slug, title, close_time_raw)
    return Market(
        market_id=market_id,
        slug=slug or market_id,
        title=title,
        close_time=_parse_close_time(close_time_raw),
        group_key=group_key,
    )


def _select_universe_rows(
    rows: List[Dict[str, Any]],
    *,
    top_n: int,
    max_expiry_days: Optional[int],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    now_dt = now or datetime.now(timezone.utc)
    expiry_cutoff = None
    if max_expiry_days is not None and max_expiry_days > 0:
        expiry_cutoff = now_dt + timedelta(days=int(max_expiry_days))

    ranked: List[Tuple[float, float, float, Dict[str, Any]]] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue

        close_time_raw = raw.get("endDate") or raw.get("closeTime") or raw.get("close_time")
        close_time = _parse_close_time(close_time_raw)
        if expiry_cutoff is not None and close_time is not None and close_time > expiry_cutoff:
            continue

        volume = _num(raw, "volumeNum", "volume", "volume24hr", "oneDayVolume", "volume24hrClob")
        activity = _num(raw, "volume24hr", "oneDayVolume", "activeVolume", "trades24h")
        liquidity = _num(raw, "liquidityNum", "liquidity", "clobLiquidity")
        ranked.append((volume, activity, liquidity, raw))

    ranked.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    cap = max(0, int(top_n))
    return [x[3] for x in ranked[:cap]]


def _make_group_key(market_group: object, condition_id: str | None, question_id: str | None,
                   slug: str, title: str, close_time: Optional[str]) -> str:
    """Stable clustering key for UI & logic.

    Prefer Polymarket-native grouping when available:
    - marketGroup: groups related markets (multi-outcome sets, etc.)
    - conditionId / questionID: stable ids

    Only if none exist, fall back to a heuristic slug/title prefix.
    """
    # 1) native group
    if market_group not in (None, "", 0, "0"):
        return f"pmg:{market_group}"

    # 2) stable ids
    if condition_id:
        return f"cond:{condition_id}"
    if question_id:
        return f"qid:{question_id}"

    # 3) heuristic: slug/title prefix + close-month bucket
    s = _norm(slug or "")
    t = _norm(title or "")
    if s:
        base = "-".join(s.split("-")[:6])
    elif t:
        base = "-".join(t.split(" ")[:6])
    else:
        base = "unknown"
    return f"{base}|{_bucket_close_time(close_time)}"



def _best_bid_ask(book: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], float]:
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    def _best(side):
        if not side:
            return None
        try:
            # side items are like {"price":"0.51","size":"123"} or lists; be defensive
            x = side[0]
            if isinstance(x, dict):
                return float(x.get("price"))
            if isinstance(x, (list, tuple)) and len(x) >= 1:
                return float(x[0])
        except (ValueError, TypeError):
            return None
        return None
    bid = _best(bids)
    ask = _best(asks)
    liq = 0.0
    # liquidity proxy: sum of top-5 sizes on both sides
    try:
        for side in (bids[:5], asks[:5]):
            for x in side:
                if isinstance(x, dict):
                    liq += float(x.get("size") or 0.0)
                elif isinstance(x, (list, tuple)) and len(x) >= 2:
                    liq += float(x[1] or 0.0)
    except (ValueError, TypeError):
        # liquidity is best-effort; ignore malformed sizes
        pass
    return bid, ask, liq


class PolymarketClient:
    """Polymarket ingest client (Gamma markets + CLOB orderbooks).

    Notes:
    - Uses stdlib urllib (no requests dependency).
    - Designed for DRY_RUN / DEMO mode. LIVE trading is intentionally a stub.
    """

    def __init__(
        self,
        *,
        limit: int = 120,
        order_by: str = "volumeNum",
        max_expiry_days: Optional[int] = None,
        gamma_rps: Optional[float] = None,
        clob_rps: Optional[float] = None,
        http_policy: Optional[HttpPolicy] = None,
    ):
        env_top_n = int(os.getenv("PS_UNIVERSE_TOP_N", str(limit)))
        env_max_expiry = int(os.getenv("PS_UNIVERSE_MAX_EXPIRY_DAYS", "180"))
        env_gamma_rps = float(os.getenv("PS_GAMMA_RPS", "1.5"))
        env_clob_rps = float(os.getenv("PS_CLOB_RPS", "6.0"))
        env_fetch_limit = int(os.getenv("PS_UNIVERSE_FETCH_LIMIT", str(max(env_top_n * 3, env_top_n))))

        self.limit = int(env_top_n)
        self.fetch_limit = int(max(env_fetch_limit, self.limit))
        self.max_expiry_days = env_max_expiry if max_expiry_days is None else int(max_expiry_days)
        self.order_by = order_by
        self.http_policy = http_policy or HttpPolicy()
        self.gamma_limiter = RateLimiter(gamma_rps if gamma_rps is not None else env_gamma_rps)
        self.clob_limiter = RateLimiter(clob_rps if clob_rps is not None else env_clob_rps)
        self.last_snapshot_stats: Dict[str, Any] = {}

    def _fetch_market_rows(self) -> List[Dict[str, Any]]:
        url = f"{GAMMA_BASE}/markets"
        data = _http_json(
            "GET",
            url,
            params={
                "closed": "false",
                "limit": self.fetch_limit,
                "offset": 0,
                "order": self.order_by,
                "ascending": "false",
            },
            policy=self.http_policy,
            limiter=self.gamma_limiter,
        )
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []

    def _fetch_universe_rows(self) -> List[Dict[str, Any]]:
        rows = self._fetch_market_rows()
        return _select_universe_rows(
            rows,
            top_n=self.limit,
            max_expiry_days=self.max_expiry_days,
        )

    def fetch_universe_markets(self) -> Tuple[List[Market], List[Dict[str, Any]]]:
        rows = self._fetch_universe_rows()
        markets: List[Market] = []
        for raw in rows:
            m = _to_market(raw)
            if m is not None:
                markets.append(m)
        return markets, rows

    def fetch_markets(self) -> List[Market]:
        markets, _ = self.fetch_universe_markets()
        return markets

    def fetch_snapshots(self, market_rows: Optional[List[Dict[str, Any]]] = None) -> List[Snapshot]:
        # Query CLOB books only for universe-selected markets.
        now = datetime.now(timezone.utc)
        markets = market_rows if market_rows is not None else self._fetch_universe_rows()
        snaps: List[Snapshot] = []
        stats = {
            "markets": len(markets),
            "tokens": 0,
            "fetched_ok": 0,
            "fetched_err": 0,
            "parsed": 0,
            "missing_token": 0,
            "missing_outcome": 0,
            "http_403": 0,
            "http_429": 0,
            "http_other": 0,
            "exceptions": 0,
            "error_samples": [],
        }
        api_key = (os.getenv("PS_CLOB_API_KEY") or os.getenv("CLOB_API_KEY") or "").strip()
        clob_headers = {
            "Origin": "https://polymarket.com",
            "Referer": "https://polymarket.com/",
        }
        if api_key:
            clob_headers["X-API-KEY"] = api_key
        for m in markets:
            market_id = str(m.get("id") or m.get("marketId") or "")
            if not market_id:
                continue
            tokens = m.get("tokens") or []
            for tok in tokens:
                try:
                    outcome = str(tok.get("outcome") or tok.get("name") or "")
                    token_id = (
                        tok.get("token_id")
                        or tok.get("tokenId")
                        or tok.get("clobTokenId")
                        or tok.get("clob_token_id")
                        or tok.get("id")
                    )
                    if not outcome or token_id is None:
                        if not outcome:
                            stats["missing_outcome"] += 1
                        if token_id is None:
                            stats["missing_token"] += 1
                        continue
                    stats["tokens"] += 1
                    book = _http_json(
                        "GET",
                        f"{CLOB_BASE}/book",
                        params={"token_id": str(token_id)},
                        policy=self.http_policy,
                        limiter=self.clob_limiter,
                        headers=clob_headers,
                    )
                    bid, ask, liq = _best_bid_ask(book or {})
                    mid = None
                    spread = None
                    if bid is not None and ask is not None:
                        mid = (bid + ask) / 2.0
                        spread = max(0.0, (ask - bid))
                    elif bid is not None:
                        mid = bid
                        spread = 0.0
                    elif ask is not None:
                        mid = ask
                        spread = 0.0
                    snaps.append(
                        Snapshot(
                            ts=now,
                            market_id=market_id,
                            outcome=outcome,
                            bid=bid,
                            ask=ask,
                            mid=mid,
                            spread=spread,
                            liquidity=liq,
                        )
                    )
                    stats["fetched_ok"] += 1
                    stats["parsed"] += 1
                except HTTPError as e:
                    stats["fetched_err"] += 1
                    if e.code == 403:
                        stats["http_403"] += 1
                    elif e.code == 429:
                        stats["http_429"] += 1
                    else:
                        stats["http_other"] += 1
                    if len(stats["error_samples"]) < 3:
                        detail = ""
                        try:
                            detail = e.read().decode("utf-8", errors="replace")
                        except Exception:
                            detail = ""
                        stats["error_samples"].append(
                            {"market_id": market_id, "token_id": str(token_id), "status": e.code, "detail": detail[:200]}
                        )
                    continue
                except Exception as e:
                    stats["fetched_err"] += 1
                    stats["exceptions"] += 1
                    if len(stats["error_samples"]) < 3:
                        stats["error_samples"].append(
                            {"market_id": market_id, "token_id": str(token_id), "status": "EXC", "detail": str(e)[:200]}
                        )
                    continue
        self.last_snapshot_stats = stats
        if stats["fetched_err"] or stats["missing_token"] or stats["missing_outcome"]:
            logger.warning(
                "snapshots: markets=%s tokens=%s ok=%s err=%s missing_token=%s missing_outcome=%s http403=%s http429=%s other=%s exc=%s",
                stats["markets"],
                stats["tokens"],
                stats["fetched_ok"],
                stats["fetched_err"],
                stats["missing_token"],
                stats["missing_outcome"],
                stats["http_403"],
                stats["http_429"],
                stats["http_other"],
                stats["exceptions"],
            )
            if stats["error_samples"]:
                logger.warning("snapshots errors: %s", stats["error_samples"])
        else:
            logger.info(
                "snapshots: markets=%s tokens=%s ok=%s parsed=%s",
                stats["markets"],
                stats["tokens"],
                stats["fetched_ok"],
                stats["parsed"],
            )
        return snaps
