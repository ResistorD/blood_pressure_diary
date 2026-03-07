from __future__ import annotations

import json
import os
import re
import errno as errno_mod
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen, build_opener, ProxyHandler

from domain.models import Market, Snapshot


GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

logger = logging.getLogger(__name__)


def _read_winhttp_proxy() -> str:
    try:
        cp = subprocess.run(
            ["netsh", "winhttp", "show", "proxy"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        out = (cp.stdout or "").strip()
        if not out:
            return "-"
        one = " ".join(out.split())
        if "Direct access" in one:
            return "DIRECT"
        return one[:200]
    except Exception:
        return "-"


def _env_proxy_value(name: str) -> str:
    return (os.getenv(name) or os.getenv(name.lower()) or "").strip()


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


class BookTimeoutSoftSkip(Exception):
    def __init__(self, exc: Exception):
        super().__init__(str(exc))
        self.original = exc


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return True
    for obj in (exc, reason, getattr(exc, "__cause__", None), getattr(reason, "__cause__", None) if reason is not None else None):
        if obj is None:
            continue
        err_no = getattr(obj, "errno", None)
        win_err = getattr(obj, "winerror", None)
        if err_no in {errno_mod.ETIMEDOUT, 110} or win_err in {10060}:
            return True
        msg = str(obj).lower()
        if "timed out" in msg or "timeout" in msg:
            return True
    return False


def _parse_retry_after(exc: HTTPError) -> Optional[float]:
    try:
        header = exc.headers.get("Retry-After") if exc.headers else None
        if not header:
            return None
        return max(0.0, float(header))
    except (ValueError, AttributeError, TypeError):
        return None


def _call_label_from_url_path(url_path: str) -> str:
    if url_path == "/book":
        return "snapshots"
    if url_path == "/markets":
        return "universe"
    if re.match(r"^/markets/[^/]+$", url_path or ""):
        return "market_detail"
    return "unknown"


def _extract_errno(exc: BaseException) -> Optional[int]:
    candidates = [
        exc,
        getattr(exc, "reason", None),
        getattr(exc, "__cause__", None),
        getattr(getattr(exc, "reason", None), "__cause__", None),
    ]
    for obj in candidates:
        if obj is None:
            continue
        for attr in ("errno", "winerror"):
            val = getattr(obj, attr, None)
            if isinstance(val, int):
                return val
    return None


def _http_json(
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    policy: Optional[HttpPolicy] = None,
    limiter: Optional[RateLimiter] = None,
    headers: Optional[Dict[str, str]] = None,
    trace: Optional[Dict[str, Any]] = None,
    opener: Any = None,
    timeout_sec: Optional[float] = None,
    fail_fast_book: bool = False,
) -> Any:
    p = policy or HttpPolicy()
    attempts = max(1, int(p.retries))
    req_ms_acc = 0.0
    read_ms_acc = 0.0
    json_ms_acc = 0.0
    retry_count = 0
    status_last: Any = "?"
    bytes_last: Any = "?"
    content_type_last = "-"
    encoding_last = "?"
    rl_rem_last: Any = "-"
    retry_after_last: Any = "-"
    url_path = urlparse(url).path or "/"
    if params:
        qs = urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{qs}"
        try:
            url_path = urlparse(url).path or url_path
        except Exception:
            pass
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        if limiter is not None:
            limiter.wait()
        t_req0 = time.perf_counter()
        req_headers = {
            "User-Agent": "curl/8.0",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            **(headers or {}),
        }
        try:
            req = Request(
                url=url,
                method=method,
                headers=req_headers,
            )
            eff_timeout = float(timeout_sec) if timeout_sec is not None else float(p.timeout_sec)
            if opener is not None:
                resp_ctx = opener.open(req, timeout=eff_timeout)
            else:
                resp_ctx = urlopen(req, timeout=eff_timeout)
            with resp_ctx as resp:
                req_ms_acc += (time.perf_counter() - t_req0) * 1000.0
                try:
                    status_last = int(getattr(resp, "status", None) or resp.getcode() or 200)
                except Exception:
                    status_last = 200
                try:
                    content_type_last = str(resp.headers.get("Content-Type") or "-")
                    encoding_last = str(resp.headers.get("Content-Encoding") or "-")
                    rl_rem_last = str(resp.headers.get("x-ratelimit-remaining") or "-")
                    retry_after_last = str(resp.headers.get("retry-after") or "-")
                except Exception:
                    pass
                t_read0 = time.perf_counter()
                raw_b = resp.read()
                read_ms_acc += (time.perf_counter() - t_read0) * 1000.0
                try:
                    bytes_last = int(len(raw_b))
                except Exception:
                    bytes_last = "?"
                t_json0 = time.perf_counter()
                import gzip
                import zlib
                ce = (str(encoding_last or "")).lower()
                if "gzip" in ce or raw_b.startswith(b"\x1f\x8b"):
                    raw_b = gzip.decompress(raw_b)
                elif "deflate" in ce:
                    try:
                        raw_b = zlib.decompress(raw_b)
                    except Exception:
                        raw_b = zlib.decompress(raw_b, -zlib.MAX_WBITS)
                text = raw_b.decode("utf-8")
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    call_name = "-"
                    if isinstance(trace, dict):
                        call_name = str(trace.get("call_name") or trace.get("call") or "-")
                    status_sniff = str(status_last if status_last not in {None, "?", ""} else "-")
                    ct_sniff = str(content_type_last or "-")
                    ce_sniff = str(encoding_last or "-")
                    try:
                        head = text[:300]
                    except Exception:
                        head = repr(raw_b[:200])
                    head = head.replace("\r", " ").replace("\n", " ").replace("\t", " ")
                    if len(head) > 300:
                        head = head[:300]
                    logger.info(
                        "HTTP_BODY_SNIFF call=%s url_path=%s status=%s ct=%s ce=%s bytes=%s head=%s",
                        call_name,
                        url_path,
                        status_sniff,
                        ct_sniff,
                        ce_sniff,
                        len(raw_b),
                        head,
                    )
                    raise RuntimeError(
                        f"Non-JSON response for {url_path}: status={status_sniff} ct={ct_sniff} ce={ce_sniff} head={head}"
                    ) from e
                json_ms_acc += (time.perf_counter() - t_json0) * 1000.0
                if trace is not None:
                    trace.update(
                        {
                            "req_ms": req_ms_acc,
                            "read_ms": read_ms_acc,
                            "json_ms": json_ms_acc,
                            "status": status_last,
                            "bytes": bytes_last,
                            "encoding": encoding_last,
                            "url_path": url_path,
                            "retries": retry_count,
                            "rl_rem": rl_rem_last,
                            "retry_after": retry_after_last,
                        }
                    )
                return data
        except HTTPError as e:
            last_err = e
            req_ms_acc += (time.perf_counter() - t_req0) * 1000.0
            try:
                status_last = int(getattr(e, "code", None) or status_last)
            except Exception:
                pass
            if getattr(e, "code", None) == 403:
                logger.info(
                    "HTTP_403 url_path=%s ua=%s",
                    url_path,
                    req_headers.get("User-Agent", "-"),
                )
            try:
                encoding_last = str((e.headers or {}).get("Content-Encoding") or encoding_last)
                rl_rem_last = str((e.headers or {}).get("x-ratelimit-remaining") or rl_rem_last)
                retry_after_last = str((e.headers or {}).get("retry-after") or retry_after_last)
            except Exception:
                pass
            # Explicitly back off on anti-bot/rate-limit style responses.
            if e.code not in {403, 429, 500, 502, 503, 504}:
                break
            retry_count += 1
            retry_after = _parse_retry_after(e)
            delay = retry_after if retry_after is not None else min(
                p.backoff_cap_sec,
                p.backoff_base_sec * (2 ** (attempt - 1)),
            )
            time.sleep(delay)
        except Exception as e:
            if fail_fast_book and url_path == "/book" and _is_timeout_error(e):
                raise BookTimeoutSoftSkip(e) from e
            last_err = e
            req_ms_acc += (time.perf_counter() - t_req0) * 1000.0
            reason = getattr(e, "reason", None)
            win_err = getattr(reason, "winerror", None) if reason is not None else None
            err_no = win_err if isinstance(win_err, int) else _extract_errno(e)
            if err_no == 10013:
                err_type = type(reason).__name__ if reason is not None else type(e).__name__
                logger.info(
                    "NET_ERR_PROFILE call=%s url_path=%s err_type=%s errno=%s",
                    _call_label_from_url_path(url_path),
                    url_path,
                    err_type,
                    err_no,
                )
            retry_count += 1
            delay = min(
                p.backoff_cap_sec,
                p.backoff_base_sec * (2 ** (attempt - 1)),
            )
            time.sleep(delay)
    if trace is not None:
        trace.update(
            {
                "req_ms": req_ms_acc,
                "read_ms": read_ms_acc,
                "json_ms": json_ms_acc,
                "status": status_last,
                "bytes": bytes_last,
                "encoding": encoding_last,
                "url_path": url_path,
                "retries": retry_count,
                "rl_rem": rl_rem_last,
                "retry_after": retry_after_last,
            }
        )
    raise last_err or RuntimeError("HTTP failed")


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9\-\s]", "", s)
    return s


def is_valid_market_detail_id(market_id: str) -> bool:
    mid = str(market_id or "").strip()
    return bool(re.fullmatch(r"\d+", mid))


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


def _normalize_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return [value]
    return [value]


def _extract_tokens_from_row(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    tokens = raw.get("tokens") or []
    if isinstance(tokens, list) and tokens:
        return tokens
    outcomes = _normalize_list(raw.get("outcomes") or raw.get("outcome"))
    clob_ids = _normalize_list(raw.get("clobTokenIds") or raw.get("clob_token_ids") or raw.get("clobTokenIDs"))
    if outcomes and clob_ids and len(outcomes) == len(clob_ids):
        built = []
        for outcome, tid in zip(outcomes, clob_ids):
            built.append({"outcome": outcome, "token_id": tid, "clobTokenId": tid})
        return built
    yes_id = raw.get("yesTokenId") or raw.get("yes_token_id")
    no_id = raw.get("noTokenId") or raw.get("no_token_id")
    if yes_id or no_id:
        built = []
        if yes_id:
            built.append({"outcome": "YES", "token_id": yes_id, "clobTokenId": yes_id})
        if no_id:
            built.append({"outcome": "NO", "token_id": no_id, "clobTokenId": no_id})
        return built
    return []


def _has_clob_tokens(raw: Dict[str, Any]) -> bool:
    tokens = raw.get("tokens") or []
    if isinstance(tokens, list) and tokens:
        return True
    clob_ids = raw.get("clobTokenIds") or raw.get("clob_token_ids") or []
    if isinstance(clob_ids, list) and len(clob_ids) > 0:
        return True
    if raw.get("yesTokenId") or raw.get("noTokenId"):
        return True
    return False


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
    try:
        raw_json = json.dumps(raw, ensure_ascii=False)
    except Exception:
        raw_json = ""
    return Market(
        market_id=market_id,
        slug=slug or market_id,
        title=title,
        close_time=_parse_close_time(close_time_raw),
        group_key=group_key,
        raw_json=raw_json,
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
        self._backfill_cache: Dict[str, float] = {}
        self._snap_rr_cursor = 0
        http_proxy = _env_proxy_value("HTTP_PROXY")
        https_proxy = _env_proxy_value("HTTPS_PROXY")
        winhttp_proxy = _read_winhttp_proxy()
        proxy_map: Dict[str, str] = {}
        if http_proxy:
            proxy_map["http"] = http_proxy
        if https_proxy:
            proxy_map["https"] = https_proxy
        # Best-effort fallback: if env proxy is not set and WinHTTP has a proxy, reuse it.
        if not proxy_map and winhttp_proxy not in {"-", "DIRECT"}:
            m_http = re.search(r"http=([^;\s]+)", winhttp_proxy, flags=re.IGNORECASE)
            m_https = re.search(r"https=([^;\s]+)", winhttp_proxy, flags=re.IGNORECASE)
            if m_http:
                proxy_map["http"] = m_http.group(1)
            if m_https:
                proxy_map["https"] = m_https.group(1)
            if not proxy_map:
                m_host = re.search(r"Proxy Server\(s\)\s*:\s*([^\s;]+)", winhttp_proxy, flags=re.IGNORECASE)
                if m_host:
                    proxy_map["http"] = m_host.group(1)
                    proxy_map["https"] = m_host.group(1)
        self._proxy_handler = ProxyHandler(proxy_map) if proxy_map else ProxyHandler()
        self._opener = build_opener(self._proxy_handler)
        logger.info(
            "PROXY_CFG http_proxy=%s https_proxy=%s winhttp_proxy=%s",
            http_proxy or "-",
            https_proxy or "-",
            winhttp_proxy,
        )
        self._http_local = threading.local()
        try:
            env_http_timeout = int(os.getenv("PS_HTTP_TIMEOUT_S", "10") or 10)
        except Exception:
            env_http_timeout = 10
        self.http_policy = HttpPolicy(
            timeout_sec=max(1, int(env_http_timeout)),
            retries=self.http_policy.retries,
            backoff_base_sec=self.http_policy.backoff_base_sec,
            backoff_cap_sec=self.http_policy.backoff_cap_sec,
        )
        try:
            self.book_req_timeout_sec = float(os.getenv("PS_BOOK_REQ_TIMEOUT_S", "7") or 7.0)
        except Exception:
            self.book_req_timeout_sec = 7.0
        self.book_req_timeout_sec = max(1.0, float(self.book_req_timeout_sec))
        self.book_fail_fast = str(os.getenv("PS_BOOK_FAIL_FAST", "1") or "1").strip() not in {"0", "false", "no"}
        try:
            c = int(os.getenv("PS_BOOK_CONCURRENCY", "16") or 16)
        except Exception:
            c = 16
        self.book_concurrency = max(1, min(64, c))

    def _thread_opener(self):
        opener = getattr(self._http_local, "opener", None)
        if opener is None:
            opener = build_opener(self._proxy_handler)
            self._http_local.opener = opener
        return opener

    def fetch_market_detail(self, market_id: str) -> Optional[Dict[str, Any]]:
        try:
            data = _http_json(
                "GET",
                f"{GAMMA_BASE}/markets/{market_id}",
                policy=self.http_policy,
                limiter=self.gamma_limiter,
            )
            if isinstance(data, dict):
                if not data.get("tokens"):
                    data["tokens"] = _extract_tokens_from_row(data)
                return data
        except Exception as e:
            logger.info(
                "MARKET_DETAIL_FETCH_ERR market_id=%s err_type=%s err=%s",
                market_id,
                type(e).__name__,
                str(e)[:200],
            )
            return None
        return None

    def _fetch_market_rows(self) -> List[Dict[str, Any]]:
        url = f"{GAMMA_BASE}/markets"
        logger.info(
            "ORDERBOOK_PLAN rows=%s markets=%s chunk=%s conc=%s sample=%s",
            self.fetch_limit,
            "-",
            "-",
            self.book_concurrency,
            "-",
        )
        try:
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
        except URLError as e:
            reason = getattr(e, "reason", None)
            win_err = getattr(reason, "winerror", None) if reason is not None else None
            err_no = win_err if isinstance(win_err, int) else _extract_errno(e)
            if err_no == 10013:
                err_type = type(reason).__name__ if reason is not None else type(e).__name__
                logger.info(
                    "ORDERBOOK_NET_ERR i=%s n=%s inflight=%s/%s url_path=%s errno=%s err_type=%s",
                    "-",
                    self.fetch_limit,
                    "-",
                    "-",
                    urlparse(url).path or "/",
                    err_no,
                    err_type,
                )
            raise
        if isinstance(data, list):
            rows = [x for x in data if isinstance(x, dict)]
            for row in rows:
                if not row.get("tokens"):
                    row["tokens"] = _extract_tokens_from_row(row)
            if rows:
                sample = rows[0]
                logger.info(
                    "gamma sample: id=%s slug=%s outcomes=%s clobTokenIds=%s tokens=%s",
                    sample.get("id") or sample.get("marketId"),
                    sample.get("slug"),
                    sample.get("outcomes"),
                    sample.get("clobTokenIds") or sample.get("clob_token_ids"),
                    len(sample.get("tokens") or []),
                )
            return rows
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

    def fetch_snapshots(
        self,
        market_rows: Optional[List[Dict[str, Any]]] = None,
        hot_market_ids: Optional[Set[str]] = None,
    ) -> List[Snapshot]:
        # Query CLOB books only for universe-selected markets.
        t_total0 = time.perf_counter()
        req_ms = 0.0
        read_ms = 0.0
        json_ms = 0.0
        calls_pages = 0
        retry_count = 0
        fetch_err_count = 0
        status_last: Any = "?"
        bytes_last: Any = "?"
        encoding_last = "-"
        url_path_last = "/book"
        rl_rem_last: Any = "-"
        retry_after_last: Any = "-"
        timeout_count = 0
        soft_skipped_count = 0
        inflight_current = 0
        inflight_max = 0
        inflight_lock = threading.Lock()
        req_sum_ms = 0.0
        durations_ms: List[float] = []
        now = datetime.now(timezone.utc)
        snaps: List[Snapshot] = []
        stats = {
            "markets": 0,
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
        try:
            book_max_pages = int(os.getenv("PS_BOOK_MAX_PAGES", "0") or 0)
        except Exception:
            book_max_pages = 0
        try:
            dev_mode = str(os.getenv("PS_DEV", "0") or "0").strip().lower() not in {"0", "false", "no", ""}
            default_snapshots_limit = 60 if dev_mode else 0
            ingest_snapshots_limit = int(
                os.getenv("PS_INGEST_SNAPSHOTS_LIMIT", str(default_snapshots_limit)) or default_snapshots_limit
            )
        except Exception:
            ingest_snapshots_limit = 0
        ingest_snapshots_limit = max(0, int(ingest_snapshots_limit))
        try:
            markets = market_rows if market_rows is not None else self._fetch_universe_rows()
        except Exception:
            raise
        stats["markets"] = len(markets)
        all_tasks: List[Tuple[str, str, str]] = []
        for m in markets:
            market_id = str(m.get("id") or m.get("marketId") or "")
            if not market_id:
                continue
            tokens = m.get("tokens") or []
            for tok in tokens:
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
                all_tasks.append((market_id, outcome, str(token_id)))
        hot_ids = {str(x) for x in (hot_market_ids or set()) if str(x)}
        hot_tasks: List[Tuple[str, str, str]] = []
        cold_tasks: List[Tuple[str, str, str]] = []
        for task in all_tasks:
            if task[0] in hot_ids:
                hot_tasks.append(task)
            else:
                cold_tasks.append(task)
        total_candidates = len(all_tasks)
        limit = ingest_snapshots_limit if ingest_snapshots_limit > 0 else book_max_pages
        cursor_before = int(getattr(self, "_snap_rr_cursor", 0) or 0)
        tasks = all_tasks
        hot_planned = hot_tasks
        if limit > 0:
            hot_planned = hot_tasks[:limit]
            remaining = max(0, limit - len(hot_planned))
            cold_planned: List[Tuple[str, str, str]] = []
            cold_n = len(cold_tasks)
            if remaining > 0 and cold_n > 0:
                if cold_n <= remaining:
                    cold_planned = cold_tasks
                else:
                    start = cursor_before % cold_n
                    end = start + remaining
                    if end <= cold_n:
                        cold_planned = cold_tasks[start:end]
                    else:
                        cold_planned = cold_tasks[start:] + cold_tasks[: end - cold_n]
                    self._snap_rr_cursor = (start + remaining) % cold_n
            tasks = hot_planned + cold_planned
            stats["tokens"] = len(tasks)
        logger.info(
            "SNAPSHOTS_PLAN total=%s planned=%s limit=%s cursor=%s",
            total_candidates,
            len(tasks),
            (limit if limit > 0 else "none"),
            cursor_before,
        )
        t_req_phase0 = time.perf_counter()

        def _fetch_one(task: Tuple[str, str, str]) -> Dict[str, Any]:
            nonlocal inflight_current, inflight_max
            market_id, outcome, token_id = task
            trace: Dict[str, Any] = {}
            t_one0 = time.perf_counter()
            with inflight_lock:
                inflight_current += 1
                if inflight_current > inflight_max:
                    inflight_max = inflight_current
            try:
                try:
                    book = _http_json(
                        "GET",
                        f"{CLOB_BASE}/book",
                        params={"token_id": token_id},
                        policy=self.http_policy,
                        limiter=self.clob_limiter if self.book_concurrency == 1 else None,
                        headers=clob_headers,
                        trace=trace,
                        opener=(self._opener if self.book_concurrency == 1 else self._thread_opener()),
                        timeout_sec=self.book_req_timeout_sec,
                        fail_fast_book=self.book_fail_fast,
                    )
                except BookTimeoutSoftSkip as e:
                    return {
                        "timeout": True,
                        "market_id": market_id,
                        "token_id": token_id,
                        "detail": str(getattr(e, "original", e))[:200],
                    }
            finally:
                with inflight_lock:
                    inflight_current -= 1
            req_dur_ms = (time.perf_counter() - t_one0) * 1000.0
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
            return {
                "snapshot": Snapshot(
                    ts=now,
                    market_id=market_id,
                    outcome=outcome,
                    bid=bid,
                    ask=ask,
                    mid=mid,
                    spread=spread,
                    liquidity=liq,
                ),
                "trace": trace,
                "market_id": market_id,
                "token_id": token_id,
                "req_dur_ms": req_dur_ms,
            }

        if self.book_concurrency <= 1:
            iterator = tasks
            for task in iterator:
                calls_pages += 1
                try:
                    res = _fetch_one(task)
                    if res.get("timeout"):
                        timeout_count += 1
                        if self.book_fail_fast:
                            soft_skipped_count += 1
                        stats["fetched_err"] += 1
                        stats["exceptions"] += 1
                        fetch_err_count += 1
                        if len(stats["error_samples"]) < 3:
                            stats["error_samples"].append(
                                {"market_id": task[0], "token_id": task[2], "status": "TIMEOUT", "detail": str(res.get("detail", ""))}
                            )
                        continue
                    tr = res.get("trace") or {}
                    req_ms += float(tr.get("req_ms", 0.0) or 0.0)
                    read_ms += float(tr.get("read_ms", 0.0) or 0.0)
                    json_ms += float(tr.get("json_ms", 0.0) or 0.0)
                    retry_count += int(tr.get("retries", 0) or 0)
                    status_last = tr.get("status", status_last)
                    bytes_last = tr.get("bytes", bytes_last)
                    encoding_last = str(tr.get("encoding", encoding_last) or encoding_last)
                    url_path_last = str(tr.get("url_path", url_path_last) or url_path_last)
                    rl_rem_last = tr.get("rl_rem", rl_rem_last)
                    retry_after_last = tr.get("retry_after", retry_after_last)
                    dur_ms = float(res.get("req_dur_ms", 0.0) or 0.0)
                    req_sum_ms += dur_ms
                    durations_ms.append(dur_ms)
                    snaps.append(res["snapshot"])
                    stats["fetched_ok"] += 1
                    stats["parsed"] += 1
                except HTTPError as e:
                    stats["fetched_err"] += 1
                    fetch_err_count += 1
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
                            {"market_id": task[0], "token_id": task[2], "status": e.code, "detail": detail[:200]}
                        )
                    continue
                except Exception as e:
                    stats["fetched_err"] += 1
                    stats["exceptions"] += 1
                    fetch_err_count += 1
                    if len(stats["error_samples"]) < 3:
                        stats["error_samples"].append(
                            {"market_id": task[0], "token_id": task[2], "status": "EXC", "detail": str(e)[:200]}
                        )
                    continue
        else:
            with ThreadPoolExecutor(max_workers=self.book_concurrency) as ex:
                fut_map = {ex.submit(_fetch_one, task): task for task in tasks}
                for fut in as_completed(fut_map):
                    task = fut_map[fut]
                    calls_pages += 1
                    try:
                        res = fut.result()
                        if res.get("timeout"):
                            timeout_count += 1
                            if self.book_fail_fast:
                                soft_skipped_count += 1
                            stats["fetched_err"] += 1
                            stats["exceptions"] += 1
                            fetch_err_count += 1
                            if len(stats["error_samples"]) < 3:
                                stats["error_samples"].append(
                                    {"market_id": task[0], "token_id": task[2], "status": "TIMEOUT", "detail": str(res.get("detail", ""))}
                                )
                            continue
                        tr = res.get("trace") or {}
                        req_ms += float(tr.get("req_ms", 0.0) or 0.0)
                        read_ms += float(tr.get("read_ms", 0.0) or 0.0)
                        json_ms += float(tr.get("json_ms", 0.0) or 0.0)
                        retry_count += int(tr.get("retries", 0) or 0)
                        status_last = tr.get("status", status_last)
                        bytes_last = tr.get("bytes", bytes_last)
                        encoding_last = str(tr.get("encoding", encoding_last) or encoding_last)
                        url_path_last = str(tr.get("url_path", url_path_last) or url_path_last)
                        rl_rem_last = tr.get("rl_rem", rl_rem_last)
                        retry_after_last = tr.get("retry_after", retry_after_last)
                        dur_ms = float(res.get("req_dur_ms", 0.0) or 0.0)
                        req_sum_ms += dur_ms
                        durations_ms.append(dur_ms)
                        snaps.append(res["snapshot"])
                        stats["fetched_ok"] += 1
                        stats["parsed"] += 1
                    except HTTPError as e:
                        stats["fetched_err"] += 1
                        fetch_err_count += 1
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
                                {"market_id": task[0], "token_id": task[2], "status": e.code, "detail": detail[:200]}
                            )
                        continue
                    except Exception as e:
                        stats["fetched_err"] += 1
                        stats["exceptions"] += 1
                        fetch_err_count += 1
                        if len(stats["error_samples"]) < 3:
                            stats["error_samples"].append(
                                {"market_id": task[0], "token_id": task[2], "status": "EXC", "detail": str(e)[:200]}
                            )
                        continue
        req_ms = (time.perf_counter() - t_req_phase0) * 1000.0
        total_ms = (time.perf_counter() - t_total0) * 1000.0
        if timeout_count > 0 or not self.book_fail_fast:
            logger.info(
                "SNAPSHOTS_TIMEOUTS timeouts=%s soft_skipped=%s timeout_s=%s fail_fast=%s",
                timeout_count,
                soft_skipped_count,
                int(self.book_req_timeout_sec),
                1 if self.book_fail_fast else 0,
            )
        req_avg_ms = (req_sum_ms / calls_pages) if calls_pages > 0 else 0.0
        req_p95_ms = 0.0
        if durations_ms:
            ds = sorted(durations_ms)
            idx = int(0.95 * (len(ds) - 1))
            req_p95_ms = ds[idx]
        logger.info(
            "SNAPSHOTS_FETCH_PROFILE ms_total=%.0f ms_req=%.0f ms_read=%.0f ms_json=%.0f status=%s bytes=%s encoding=%s url=%s rl_rem=%s retry_after=%s calls_pages=%s",
            total_ms,
            req_ms,
            read_ms,
            json_ms,
            status_last,
            bytes_last,
            encoding_last,
            url_path_last,
            rl_rem_last,
            retry_after_last,
            calls_pages,
        )
        logger.info(
            "SNAPSHOTS_CONCURRENCY_PROFILE conc=%s calls_pages=%s inflight_max=%s total_ms=%.0f req_sum_ms=%.0f req_avg_ms=%.0f req_p95_ms=%.0f",
            self.book_concurrency,
            calls_pages,
            inflight_max,
            total_ms,
            req_sum_ms,
            req_avg_ms,
            req_p95_ms,
        )
        self.last_snapshot_stats = stats
        # Batch timestamp diagnostics: reveals if all snapshots share one ts or span a range
        if snaps:
            ts_vals = [s.ts for s in snaps]
            min_ts = min(ts_vals)
            max_ts = max(ts_vals)
            span_sec = (max_ts - min_ts).total_seconds()
            distinct_ts = len(set(s.ts.isoformat(timespec="seconds") for s in snaps))
            stats["batch_min_ts"] = min_ts.isoformat(timespec="seconds")
            stats["batch_max_ts"] = max_ts.isoformat(timespec="seconds")
            stats["batch_span_sec"] = round(span_sec, 1)
            stats["batch_distinct_ts"] = distinct_ts
            logger.info(
                "snapshots_batch_ts: count=%s min_ts=%s max_ts=%s span_sec=%s distinct_ts=%s",
                len(snaps),
                stats["batch_min_ts"],
                stats["batch_max_ts"],
                stats["batch_span_sec"],
                distinct_ts,
            )
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
