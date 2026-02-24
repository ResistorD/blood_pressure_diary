"""API endpoints for enhanced dashboard (v2 JSON).

Этот модуль — "витрина" для dashboard_v2.html.
Repo передаётся через app factory и лежит в app.state.repo.
"""

from __future__ import annotations

from typing import Any, Dict, List

import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from utils.logging import get_logger, warn_exc

router = APIRouter()
templates = Jinja2Templates(directory="ui/templates")
logger = get_logger("api.dashboard_v2")

RU_STATUS = {
    "OK": "ОК",
    "OPPORTUNITY": "Возможность",
    "INVESTIGATE": "Проверить",
    "BLOCKED": "Заблокировано",
}


def get_repo(request: Request):
    """Dependency: repo из app.state (см. api/http.py:create_app)."""
    return request.app.state.repo


def _require_admin_token(request: Request) -> None:
    token = (request.headers.get("x-admin-token") or "").strip()
    if not token:
        auth = (request.headers.get("authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    expected = (os.getenv("ADMIN_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ADMIN_TOKEN is not configured",
        )
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )


def _safe_int(v: Any, default: int, min_v: int, max_v: int) -> int:
    try:
        n = int(v)
    except Exception:
        n = default
    return max(min_v, min(max_v, n))


def _sort_dir(v: str | None) -> str:
    return "asc" if str(v or "").lower() == "asc" else "desc"


def _row_get(row: Any, key: str, idx: int):
    try:
        return row[key]
    except (KeyError, TypeError):
        try:
            return row[idx]
        except (IndexError, KeyError, TypeError):
            return None


def _normalize_market_id(row: Any) -> str:
    for i, key in enumerate(("market_id", "id", "market", "condition_id", "scope_market_id")):
        val = _row_get(row, key, i)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _recent_activity(repo, limit: int) -> List[Dict[str, Any]]:
    lim = int(limit)
    # 1) Trades
    try:
        with repo.conn() as con:
            rows = con.execute(
                """
                SELECT ts, market_id
                FROM paper_trades
                ORDER BY ts DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows or []:
            market_id = _normalize_market_id(r)
            if market_id:
                out.append({"ts": _row_get(r, "ts", 0), "market_id": market_id, "type": "trade"})
        if out:
            return out
    except Exception:
        warn_exc(logger, "recent_activity: paper_trades query failed")

    # 2) Decisions
    try:
        with repo.conn() as con:
            rows = con.execute(
                """
                SELECT ts, market_id
                FROM decisions_v0
                ORDER BY ts DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
        out = []
        for r in rows or []:
            market_id = _normalize_market_id(r)
            if market_id:
                out.append({"ts": _row_get(r, "ts", 0), "market_id": market_id, "type": "decision"})
        if out:
            return out
    except Exception:
        warn_exc(logger, "recent_activity: decisions_v0 query failed")

    # 3) Snapshots (latest per market)
    try:
        with repo.conn() as con:
            rows = con.execute(
                """
                SELECT market_id, MAX(ts) AS ts
                FROM snapshots
                GROUP BY market_id
                ORDER BY ts DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
        out = []
        for r in rows or []:
            market_id = _normalize_market_id(r)
            if market_id:
                out.append({"ts": _row_get(r, "ts", 1), "market_id": market_id, "type": "snapshot"})
        if out:
            return out
    except Exception:
        warn_exc(logger, "recent_activity: snapshots query failed")

    # 4) Markets fallback (guarantee clickable case links)
    try:
        with repo.conn() as con:
            rows = con.execute(
                """
                SELECT market_id
                FROM markets
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
        out = []
        for r in rows or []:
            market_id = _normalize_market_id(r)
            if market_id:
                out.append({"ts": None, "market_id": market_id, "type": "market"})
        if out:
            return out
    except Exception:
        warn_exc(logger, "recent_activity: markets fallback query failed")

    return []


def _nav_counts(repo) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    try:
        counts["markets"] = int(repo.count_markets()) if hasattr(repo, "count_markets") else 0
    except Exception:
        counts["markets"] = 0
    try:
        counts["signals"] = int(repo.count_signals()) if hasattr(repo, "count_signals") else 0
    except Exception:
        counts["signals"] = 0
    try:
        counts["cases"] = int(repo.count_cases()) if hasattr(repo, "count_cases") else 0
    except Exception:
        counts["cases"] = 0
    try:
        counts["decisions"] = int(repo.count_decisions_v0()) if hasattr(repo, "count_decisions_v0") else 0
    except Exception:
        counts["decisions"] = 0
    try:
        if hasattr(repo, "count_paper_positions_filtered"):
            counts["positions"] = int(repo.count_paper_positions_filtered(status="OPEN"))
        elif hasattr(repo, "count_paper_positions"):
            counts["positions"] = int(repo.count_paper_positions())
        else:
            counts["positions"] = 0
    except Exception:
        counts["positions"] = 0
    return counts


def build_nav_context(active: str, repo) -> Dict[str, Any]:
    return {
        "nav_active": active,
        "nav_counts": _nav_counts(repo),
    }


@router.get("/dashboard-v2", response_class=HTMLResponse, include_in_schema=False)
@router.get("/dashboard_v2", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_v2_page(request: Request, repo=Depends(get_repo)):
    from datetime import datetime

    month_map = {
        "Jan": "янв",
        "Feb": "фев",
        "Mar": "мар",
        "Apr": "апр",
        "May": "май",
        "Jun": "июн",
        "Jul": "июл",
        "Aug": "авг",
        "Sep": "сен",
        "Oct": "окт",
        "Nov": "ноя",
        "Dec": "дек",
    }
    now = datetime.utcnow()
    mon = month_map.get(now.strftime("%b"), now.strftime("%b"))
    updated_ts = f"{now.strftime('%d')} {mon} {now.strftime('%Y')} · {now.strftime('%H:%M:%S')}"
    recent = []
    try:
        rows = _recent_activity(repo, limit=10)
        recent = [
            {
                "market_id": r.get("market_id"),
                "kind": r.get("type") or "—",
                "ts": r.get("ts"),
            }
            for r in rows or []
            if r.get("market_id")
        ]
    except Exception:
        warn_exc(logger, "dashboard_v2: recent activity failed")
        recent = []
    quality_by_action = []
    quality_by_agent = []
    top_winners = []
    top_losers = []
    market_best = []
    market_worst = []
    market_worst_winrate = []
    quality_coverage = {}
    try:
        quality_by_action = repo.get_quality_breakdown("action")
    except Exception:
        warn_exc(logger, "dashboard_v2: quality_by_action failed")
        quality_by_action = []
    try:
        quality_by_agent = repo.get_quality_breakdown("agent")
    except Exception:
        warn_exc(logger, "dashboard_v2: quality_by_agent failed")
        quality_by_agent = []
    try:
        top_winners = repo.get_top_decisions(10, "winners")
    except Exception:
        warn_exc(logger, "dashboard_v2: top_winners failed")
        top_winners = []
    try:
        top_losers = repo.get_top_decisions(10, "losers")
    except Exception:
        warn_exc(logger, "dashboard_v2: top_losers failed")
        top_losers = []
    try:
        market_best = repo.get_market_quality(15, "best")
    except Exception:
        warn_exc(logger, "dashboard_v2: market_best failed")
        market_best = []
    try:
        market_worst = repo.get_market_quality(15, "worst")
    except Exception:
        warn_exc(logger, "dashboard_v2: market_worst failed")
        market_worst = []
    try:
        market_worst_winrate = repo.get_market_worst_by_win_rate(15, 5)
    except Exception:
        warn_exc(logger, "dashboard_v2: market_worst_winrate failed")
        market_worst_winrate = []
    try:
        quality_coverage = repo.get_quality_coverage()
    except Exception:
        warn_exc(logger, "dashboard_v2: quality_coverage failed")
        quality_coverage = {}
    return templates.TemplateResponse(
        "dashboard_v2.html",
        {
            "request": request,
            "updated_ts": updated_ts,
            "recent_activity": recent,
            "quality_by_action": quality_by_action,
            "quality_by_agent": quality_by_agent,
            "top_winners": top_winners,
            "top_losers": top_losers,
            "market_best": market_best,
            "market_worst": market_worst,
            "market_worst_winrate": market_worst_winrate,
            "quality_coverage": quality_coverage,
            **build_nav_context("overview", repo),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/dashboard_v2/jump", include_in_schema=False)
@router.get("/dashboard-v2/jump", include_in_schema=False)
async def dashboard_v2_jump(market_id: str | None = Query(None)):
    market = (market_id or "").strip()
    if not market:
        return RedirectResponse(url="/dashboard-v2", status_code=302)
    return RedirectResponse(url=f"/case/{quote(market, safe='')}", status_code=302)


@router.get("/api/v2/metrics")
async def get_metrics(repo=Depends(get_repo)) -> Dict[str, Any]:
    """Get dashboard metrics (JSON)."""
    markets = 0
    signals_24h = 0
    positions_open = 0
    pnl_total = 0.0
    fees_paid = 0.0
    pnl_net = 0.0

    try:
        if hasattr(repo, "count_markets"):
            markets = int(repo.count_markets())
        elif hasattr(repo, "list_markets"):
            markets = len(repo.list_markets(limit=10000))
    except Exception:
        markets = 0

    try:
        with repo.conn() as con:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM signals WHERE ts >= datetime('now', '-24 hours')"
            ).fetchone()
            signals_24h = int(row["n"]) if row else 0
    except Exception:
        signals_24h = 0

    try:
        repo.ensure_paper_schema()
        if hasattr(repo, "count_paper_positions_filtered"):
            positions_open = int(repo.count_paper_positions_filtered(status="OPEN"))
        else:
            with repo.conn() as con:
                row = con.execute(
                    "SELECT COUNT(*) AS n FROM paper_positions WHERE status='OPEN'"
                ).fetchone()
                positions_open = int(row["n"]) if row else 0
    except Exception:
        positions_open = 0

    try:
        if hasattr(repo, "get_paper_metrics"):
            metrics = repo.get_paper_metrics()
            pnl_total = float(metrics.get("pnl_total") or 0.0)
            fees_paid = float(metrics.get("fees_paid") or 0.0)
            pnl_net = float(metrics.get("net_pnl") or pnl_total)
    except Exception:
        pnl_total = 0.0
        fees_paid = 0.0
        pnl_net = 0.0

    cache_hit_rate = 0
    cache_speedup = "1"
    try:
        if hasattr(repo, "get_cache_summary"):
            summary = repo.get_cache_summary() or {}
            cache_hit_rate = int(float(summary.get("overall_hit_rate", 0.0)) * 100)
    except Exception:
        cache_hit_rate = 0

    return {
        "markets": markets,
        "signals_24h": signals_24h,
        "positions": positions_open,
        "pnl": pnl_total,
        "pnl_display": f"${pnl_total:.2f}",
        "pnl_net": pnl_net,
        "pnl_net_display": f"${pnl_net:.2f}",
        "fees_paid": fees_paid,
        "cache_hit_rate": cache_hit_rate,
        "cache_speedup": cache_speedup,
    }


@router.get("/api/v2/pnl_timeseries")
async def get_pnl_timeseries(
    repo=Depends(get_repo),
    limit: int = Query(80, ge=1, le=500),
) -> List[Dict[str, Any]]:
    try:
        if hasattr(repo, "get_paper_pnl_timeseries"):
            rows = repo.get_paper_pnl_timeseries(limit=limit)
            return [
                {
                    "ts": r.get("ts"),
                    "pnl": r.get("cumulative_pnl"),
                    "event_pnl": r.get("event_pnl"),
                    "event_fee": r.get("event_fee"),
                    "event_net_pnl": r.get("event_net_pnl"),
                    "pnl_net": r.get("cumulative_net_pnl"),
                    "fees": r.get("cumulative_fees"),
                    "market_id": r.get("market_id"),
                    "outcome": r.get("outcome"),
                }
                for r in rows or []
            ]
    except Exception:
        warn_exc(logger, "paper pnl timeseries failed")
    return []


@router.get("/api/v2/recent_activity")
async def get_recent_activity(
    repo=Depends(get_repo),
    limit: int = Query(10, ge=1, le=50),
) -> List[Dict[str, Any]]:
    try:
        return _recent_activity(repo, limit=limit)
    except Exception:
        warn_exc(logger, "recent_activity endpoint failed")
        return []


@router.get("/api/v2/markets")
async def list_markets(
    request: Request,
    repo=Depends(get_repo),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
    q: str | None = None,
    sort: str | None = None,
    dir: str | None = None,
) -> Dict[str, Any]:
    q = (q or "").strip().lower()
    order_map = {
        "market_id": "market_id",
        "title": "title",
        "group_key": "group_key",
    }
    order_col = order_map.get((sort or "market_id").lower(), "market_id")
    if sort is None and dir is None:
        order_dir = "ASC"
    else:
        order_dir = "ASC" if _sort_dir(dir) == "asc" else "DESC"
    where = ""
    params: List[Any] = []
    if q:
        where = "WHERE LOWER(market_id) LIKE ? OR LOWER(COALESCE(title,'')) LIKE ? OR LOWER(COALESCE(group_key,'')) LIKE ?"
        like = f"%{q}%"
        params.extend([like, like, like])
    with repo.conn() as con:
        total_row = con.execute(
            f"SELECT COUNT(*) AS n FROM markets {where}",
            tuple(params),
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0
        rows = con.execute(
            f"""
            SELECT m.market_id, m.title, m.group_key,
                   (
                     SELECT s.liquidity
                     FROM snapshots s
                     WHERE s.market_id = m.market_id
                     ORDER BY s.ts DESC
                     LIMIT 1
                   ) AS last_liq
            FROM markets m
            {where}
            ORDER BY {order_col} {order_dir}, market_id ASC
            LIMIT ? OFFSET ?
            """,
            (*params, int(limit), int(offset)),
        ).fetchall()
    return {
        "total": total,
        "rows": [
            {
                "market_id": r["market_id"],
                "title": r["title"],
                "group_key": r["group_key"],
                "last_liq": r["last_liq"],
            }
            for r in rows or []
        ],
    }


@router.get("/api/v2/signals")
async def list_signals(
    repo=Depends(get_repo),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
    kind: str | None = None,
    agent: str | None = None,
    market_id: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    dir: str | None = None,
) -> Dict[str, Any]:
    rows = []
    total = 0
    try:
        rows = repo.list_recent_signals_filtered(
            limit=limit,
            offset=offset,
            agent=agent or None,
            kind=kind or None,
            market_id=market_id or None,
            q=q or None,
            sort_by=sort or "ts",
            sort_dir=_sort_dir(dir),
        )
        total = int(
            repo.count_signals_filtered(
                agent=agent or None,
                kind=kind or None,
                market_id=market_id or None,
                q=q or None,
            )
        )
    except Exception:
        rows = []
        total = 0

    out = []
    for r in rows or []:
        out.append(
            {
                "ts": _row_get(r, "ts", 0),
                "agent_id": _row_get(r, "agent_id", 1),
                "kind": _row_get(r, "kind", 2),
                "market_id": _row_get(r, "scope_market_id", 3),
                "explain": _row_get(r, "explain_short", 4),
            }
        )
    return {"total": total, "rows": out}


@router.get("/api/v2/cases")
async def list_cases(
    repo=Depends(get_repo),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
    status: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    dir: str | None = None,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    try:
        rows = repo.list_cases(minutes_signals=30, minutes_snaps=10)
        if rows and not isinstance(rows[0], dict):
            rows = [dict(x) for x in rows]  # type: ignore[arg-type]
    except Exception:
        rows = []

    status_q = (status or "").strip().upper()
    ql = (q or "").strip().lower()
    if status_q:
        rows = [x for x in rows if str(x.get("status", "")).upper() == status_q]
    if ql:
        rows = [
            x for x in rows
            if ql in str(x.get("title", "")).lower()
            or ql in str(x.get("market_id", "")).lower()
            or ql in str(x.get("reason", "")).lower()
        ]

    sort_key = (sort or "activity").strip().lower()
    direction = _sort_dir(dir)
    if sort_key == "status":
        pr = {"OPPORTUNITY": 0, "INVESTIGATE": 1, "BLOCKED": 2, "OK": 9}
        rows.sort(
            key=lambda c: (pr.get((c.get("status") or "").upper(), 9), c.get("last_signal_ts") or ""),
            reverse=(direction == "desc"),
        )
    elif sort_key == "market":
        rows.sort(key=lambda c: str(c.get("market_id") or "").lower(), reverse=(direction == "desc"))
    elif sort_key == "spread":
        rows.sort(key=lambda c: float(c.get("spread") or 0.0), reverse=(direction == "desc"))
    elif sort_key == "liq":
        rows.sort(key=lambda c: float(c.get("liq") or 0.0), reverse=(direction == "desc"))
    elif sort_key == "sum_mid":
        rows.sort(key=lambda c: float(c.get("sum_mid") or 0.0), reverse=(direction == "desc"))
    else:
        rows.sort(
            key=lambda c: c.get("last_signal_ts") or c.get("last_snapshot_ts") or "",
            reverse=(direction == "desc"),
        )

    total = len(rows)
    rows = rows[int(offset):int(offset) + int(limit)]

    out = []
    for r in rows:
        status_raw = str(r.get("status") or "")
        out.append(
            {
                "market_id": r.get("market_id"),
                "status": status_raw,
                "status_ru": RU_STATUS.get(status_raw.upper(), status_raw),
                "spread": r.get("spread"),
                "liq": r.get("liq"),
                "sum_mid": r.get("sum_mid"),
                "last_ts": r.get("last_signal_ts") or r.get("last_snapshot_ts"),
                "activity": r.get("activity") or r.get("activity_score") or (r.get("last_signal_ts") or r.get("last_snapshot_ts")),
            }
        )
    return {"total": total, "rows": out}


@router.get("/api/v2/positions")
async def list_positions(
    repo=Depends(get_repo),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
    status: str | None = None,
    market_id: str | None = None,
    sort: str | None = None,
    dir: str | None = None,
) -> Dict[str, Any]:
    rows = []
    total = 0
    try:
        repo.ensure_paper_schema()
        rows = repo.list_paper_positions_filtered(
            limit=limit,
            offset=offset,
            status=status or None,
            market_id=market_id or None,
            sort_by=sort or "opened_at",
            sort_dir=_sort_dir(dir),
        )
        total = int(repo.count_paper_positions_filtered(status=status or None, market_id=market_id or None))
    except Exception:
        rows = []
        total = 0

    market_ids = list({_row_get(r, "market_id", 1) for r in rows if r})
    latest = {}
    try:
        if market_ids and hasattr(repo, "get_latest_snapshots_batch"):
            latest = repo.get_latest_snapshots_batch(market_ids)
    except Exception:
        latest = {}

    sell_map: Dict[tuple[str, str], float] = {}
    try:
        with repo.conn() as con:
            sell_rows = con.execute(
                """
                SELECT market_id, outcome, ts, price
                FROM paper_trades
                WHERE side='SELL'
                ORDER BY ts DESC
                """
            ).fetchall()
        for r in sell_rows or []:
            key = (r["market_id"], r["outcome"])
            if key not in sell_map:
                sell_map[key] = float(r["price"]) if r["price"] is not None else 0.0
    except Exception:
        sell_map = {}

    out = []
    for r in rows or []:
        opened_at = _row_get(r, "opened_at", 0)
        mid = _row_get(r, "market_id", 1)
        outcome = _row_get(r, "outcome", 2)
        qty = float(_row_get(r, "qty", 3) or 0.0)
        avg_price = float(_row_get(r, "avg_price", 4) or 0.0)
        status_v = _row_get(r, "status", 5)

        pnl = 0.0
        if str(status_v).upper() == "OPEN":
            snap = (latest.get(mid) or {}).get(outcome, {})
            m = snap.get("mid")
            try:
                m = float(m) if m is not None else avg_price
            except Exception:
                m = avg_price
            pnl = (m - avg_price) * qty
        else:
            sell_px = sell_map.get((mid, outcome))
            if sell_px is not None:
                pnl = (float(sell_px) - avg_price) * qty

        out.append(
            {
                "opened_at": opened_at,
                "market_id": mid,
                "outcome": outcome,
                "qty": qty,
                "price": avg_price,
                "status": status_v,
                "pnl": pnl,
            }
        )
    return {"total": total, "rows": out}


@router.get("/api/v2/trades")
async def list_trades(
    repo=Depends(get_repo),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
    side: str | None = None,
    sort: str | None = None,
    dir: str | None = None,
) -> Dict[str, Any]:
    rows = []
    total = 0
    try:
        repo.ensure_paper_schema()
        rows = repo.list_paper_trades_filtered(
            limit=limit,
            offset=offset,
            side=side or None,
            market_id=None,
            sort_by=sort or "ts",
            sort_dir=_sort_dir(dir),
        )
        total = int(repo.count_paper_trades_filtered(side=side or None, market_id=None))
    except Exception:
        rows = []
        total = 0

    out = []
    for r in rows or []:
        ts = _row_get(r, "ts", 0)
        mid = _row_get(r, "market_id", 1)
        outcome = _row_get(r, "outcome", 2)
        side_v = _row_get(r, "side", 3)
        qty = float(_row_get(r, "qty", 4) or 0.0)
        price = float(_row_get(r, "price", 5) or 0.0)
        fee = float(_row_get(r, "fee", 6) or 0.0)
        out.append(
            {
                "ts": ts,
                "market_id": mid,
                "outcome": outcome,
                "side": side_v,
                "qty": qty,
                "price": price,
                "fee": fee,
                "total": qty * price,
                "agent_id": "",
            }
        )
    return {"total": total, "rows": out}


@router.get("/api/v2/health")
async def get_health_status(repo=Depends(get_repo)) -> Dict[str, Any]:
    """Get system health (JSON)."""
    components: List[Dict[str, Any]] = []

    # Database health
    db_ok = False
    try:
        with repo.conn() as con:
            con.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    components.append(
        {
            "name": "Database",
            "status": "OK" if db_ok else "ERROR",
            "badge": "success" if db_ok else "danger",
            "perf": 95 if db_ok else 10,
        }
    )

    # Cache health
    cache_summary = {}
    cache_hit_rate = 0
    try:
        if hasattr(repo, "get_cache_summary"):
            cache_summary = repo.get_cache_summary() or {}
            cache_hit_rate = int(float(cache_summary.get("overall_hit_rate", 0.0)) * 100)
    except Exception:
        cache_summary = {}
        cache_hit_rate = 0

    cache_enabled = bool(cache_summary.get("enabled", False)) if cache_summary else False
    components.append(
        {
            "name": "Cache",
            "status": "ON" if cache_enabled else "OFF",
            "badge": "success" if cache_enabled else "warn",
            "perf": cache_hit_rate,
        }
    )

    # Pipeline placeholders (best-effort)
    components.extend(
        [
            {"name": "Ingest", "status": "OK", "badge": "success", "perf": 85},
            {"name": "Agents", "status": "OK", "badge": "success", "perf": 88},
            {"name": "Execution", "status": "OK", "badge": "success", "perf": 90},
        ]
    )

    cache_size_mb = 0
    try:
        if hasattr(repo, "get_cache_stats"):
            stats = repo.get_cache_stats() or {}
            sizes = stats.get("sizes", {})
            cache_size_mb = int(sum(int(v or 0) for v in sizes.values()))
    except Exception:
        cache_size_mb = 0

    return {
        "components": components,
        "cache": {
            "hit_rate": cache_hit_rate,
            "speedup": "1",
            "size_mb": cache_size_mb,
        },
    }


@router.post("/api/v2/cache/clear", dependencies=[Depends(_require_admin_token)])
async def clear_cache(repo=Depends(get_repo)) -> Dict[str, str]:
    """Clear cache."""
    try:
        if hasattr(repo, "clear_cache"):
            repo.clear_cache()
        return {"status": "ok", "message": "Cache cleared"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Legacy endpoints kept for backward compatibility (old dashboard)
@router.get("/api/metrics")
async def legacy_metrics(repo=Depends(get_repo)) -> Dict[str, Any]:
    return await get_metrics(repo=repo)


@router.post("/api/cache/clear", dependencies=[Depends(_require_admin_token)])
async def legacy_clear_cache(repo=Depends(get_repo)) -> Dict[str, str]:
    return await clear_cache(repo=repo)
