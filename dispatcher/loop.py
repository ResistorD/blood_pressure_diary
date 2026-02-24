from __future__ import annotations

import logging
import time
import os
import json
from datetime import datetime, timezone

from app.settings import Settings
from db.repo import Repo
from dispatcher.bus import EventBus
from dispatcher.events import Alert, MarketTick, Timer
from dispatcher.scheduler import Scheduler
from ingest.ingestor import Ingestor
from ingest.polymarket_client import PolymarketClient, _extract_tokens_from_row
from ingest.orderbook_collector import OrderbookCollector
from db.agent_provider import RepoAgentDataProvider

from agents.enhanced_base import AgentContext
from agents.quant import QuantAgent
from decision.engine import DecisionEngineV0
from execution.reconcile import reconcile_paper
from app.risk_gate import RiskGate
from dispatcher.contract import Dispatcher
from agents.auto_paper_agent import get_auto_paper_agent

log = logging.getLogger("dispatcher.loop")


def _try_import_optional_agents():
    """Optional agents are allowed to be missing during early development."""
    scout = None
    logic = None
    auditor = None
    risk = None

    try:
        from agents.scout import ScoutAgent  # type: ignore
        scout = ScoutAgent()
    except Exception:
        scout = None

    try:
        from agents.logic import LogicAgent  # type: ignore
        logic = LogicAgent()
    except Exception:
        logic = None

    try:
        from agents.auditor import AuditorAgent  # type: ignore
        auditor = AuditorAgent()
    except Exception:
        auditor = None

    try:
        from agents.risk import RiskAgent  # type: ignore
        risk = RiskAgent()
    except Exception:
        risk = None

    return scout, logic, auditor, risk


class MainLoop:
    def __init__(self, settings: Settings, repo: Repo, bus: EventBus, run_id: str):
        self.settings = settings
        self.repo = repo
        self.bus = bus
        self.run_id = run_id

        self.decision_engine = DecisionEngineV0(repo, risk_gate=RiskGate(repo, settings))

        self.scheduler = Scheduler(
            poll_interval_sec=settings.poll_interval_sec,
            reconcile_interval_sec=settings.reconcile_interval_sec,
        )
        self.ingestor = Ingestor(repo, PolymarketClient())
        self.book_collector = OrderbookCollector(repo, PolymarketClient())

        # --- Agents ---
        # Fast agents run on each MarketTick (cheap per-market).
        self.fast_agents = [
            QuantAgent(
                min_liquidity=settings.risk.min_liquidity,
                max_spread=settings.risk.max_spread,
            )
        ]

        # Slow agents run on reconcile tick (cross-market scans + global checks).
        scout, logic, auditor, risk = _try_import_optional_agents()
        self.slow_agents = []
        if scout is not None:
            self.slow_agents.append(scout)
        if logic is not None:
            self.slow_agents.append(logic)
        if auditor is not None:
            self.slow_agents.append(auditor)
        if risk is not None:
            self.slow_agents.append(risk)

        # Backward-compat alias (some code may expect self.agents)
        self.agents = self.fast_agents

        self._stop = False
        self._ingest_failures = 0
        self._next_ingest_ts = 0.0
        self._next_book_ts = 0.0
        self._book_failures = 0
        self._event_buffer = []
        self._latest_snapshots_cache = {}
        self._auto_agent = get_auto_paper_agent()

    def _active_orderbook_targets(self, top_n: int = 30) -> tuple[list[str], dict]:
        ids: list[tuple[str, str]] = []
        try:
            cases = self.repo.list_cases(minutes_signals=30, minutes_snaps=10)
            for c in cases[:top_n]:
                mid = c.get("market_id") if isinstance(c, dict) else None
                if mid:
                    ids.append((str(mid), "cases"))
        except Exception:
            pass
        try:
            with self.repo.conn() as con:
                rows = con.execute(
                    "SELECT DISTINCT market_id AS market_id FROM paper_positions WHERE status='OPEN'"
                ).fetchall()
            for r in rows or []:
                mid = r["market_id"] if isinstance(r, dict) else r[0]
                if mid:
                    ids.append((str(mid), "positions"))
        except Exception:
            pass
        pinned = (os.getenv("PS_PINNED_MARKETS") or "").strip()
        if pinned:
            for mid in pinned.split(","):
                mid = mid.strip()
                if mid:
                    ids.append((mid, "pinned"))
        # unique, preserve order
        seen = set()
        unique: list[tuple[str, str]] = []
        for mid, src in ids:
            if mid and not mid.isdigit():
                continue
            if mid in seen:
                continue
            seen.add(mid)
            unique.append((mid, src))

        targets: list[str] = []
        dropped_unknown_market_id = 0
        dropped_no_tokens = 0
        source_counts: dict[str, int] = {"cases": 0, "positions": 0, "pinned": 0}
        if not unique:
            return targets, {
                "sources": source_counts,
                "dropped_unknown_market_id": dropped_unknown_market_id,
                "dropped_no_tokens": dropped_no_tokens,
            }
        try:
            qmarks = ",".join(["?"] * len(unique))
            with self.repo.conn() as con:
                rows = con.execute(
                    f"SELECT market_id, raw_json FROM markets WHERE market_id IN ({qmarks})",
                    tuple([m for m, _ in unique]),
                ).fetchall()
            raw_map = {r["market_id"]: r["raw_json"] for r in rows or []}
            for mid, src in unique:
                raw_json = raw_map.get(mid) or ""
                if not raw_json:
                    dropped_unknown_market_id += 1
                    continue
                try:
                    raw = json.loads(raw_json)
                except Exception:
                    dropped_no_tokens += 1
                    continue
                tokens = _extract_tokens_from_row(raw)
                if not tokens:
                    dropped_no_tokens += 1
                    continue
                for t in tokens:
                    tid = (
                        t.get("token_id")
                        or t.get("tokenId")
                        or t.get("clobTokenId")
                        or t.get("clob_token_id")
                        or t.get("id")
                    )
                    if tid is None:
                        continue
                    targets.append(str(tid))
                    source_counts[src] = source_counts.get(src, 0) + 1
        except Exception:
            log.exception("orderbook targets build failed")
        return targets, {
            "sources": source_counts,
            "dropped_unknown_market_id": dropped_unknown_market_id,
            "dropped_no_tokens": dropped_no_tokens,
        }

    def stop(self) -> None:
        self._stop = True

    def _ctx(self, now):
        return AgentContext(
            run_id=self.run_id,
            now=now,
            repo=self.repo,
            settings=self.settings,
            data_provider=RepoAgentDataProvider(self.repo),
            repo_latest_snapshots=self._latest_snapshots_by_outcome,
            latest_snapshots=self._latest_snapshots_cache,
        )

    def _queue_event(
        self,
        *,
        ts: datetime,
        level: str,
        component: str,
        message: str,
        payload: dict | None = None,
    ) -> None:
        self._event_buffer.append(
            {
                "ts": ts,
                "level": level,
                "component": component,
                "message": message,
                "payload": payload or {},
            }
        )
        if len(self._event_buffer) >= 128:
            self._flush_events()

    def _flush_events(self) -> None:
        if not self._event_buffer:
            return
        if hasattr(self.repo, "log_events_batch"):
            try:
                self.repo.log_events_batch(self._event_buffer)
                self._event_buffer.clear()
                return
            except Exception:
                log.warning("log_events_batch failed; falling back to per-event logging", exc_info=True)
        for e in self._event_buffer:
            self.repo.log_event(
                ts=e["ts"],
                level=e["level"],
                component=e["component"],
                message=e["message"],
                payload=e["payload"],
            )
        self._event_buffer.clear()

    def _run_agents_for_market(self, ctx: AgentContext, market_id: str) -> None:
        for agent in getattr(self, "fast_agents", []):
            try:
                signals = agent.propose(ctx, market_id=market_id)
                for s in signals:
                    self.repo.insert_signal(s)
            except Exception as e:
                log.exception(f"agent failed: {getattr(agent, 'agent_id', 'unknown')}: {e}")
                self._queue_event(
                    ts=ctx.now,
                    level="ERROR",
                    component=f"agent:{getattr(agent, 'agent_id', 'unknown')}",
                    message=str(e),
                    payload={"market_id": market_id},
                )

    def _run_slow_agents(self, ctx: AgentContext) -> None:
        # Run once per reconcile
        for agent in getattr(self, "slow_agents", []):
            try:
                # Prefer signature propose(ctx) for slow scans; fallback to per-market scan.
                try:
                    signals = agent.propose(ctx)  # type: ignore[arg-type]
                except TypeError:
                    signals = []
                    for m in self.repo.list_markets(limit=200):
                        signals.extend(agent.propose(ctx, market_id=m.market_id))
                for s in signals:
                    self.repo.insert_signal(s)
            except Exception as e:
                log.exception(f"slow agent failed: {getattr(agent, 'agent_id', 'unknown')}: {e}")
                self._queue_event(
                    ts=ctx.now,
                    level="ERROR",
                    component=f"agent:{getattr(agent, 'agent_id', 'unknown')}",
                    message=str(e),
                    payload={},
                )

    def _handle_event(self, ev) -> None:
        now = ev.ts
        ctx = self._ctx(now)

        if isinstance(ev, MarketTick) and self.settings.enable_agents:
            self._run_agents_for_market(ctx, ev.market_id)

        elif isinstance(ev, Timer):
            if ev.purpose == "reconcile":
                # Slow agents first: generate cross-market signals before decisions
                if self.settings.enable_agents:
                    self._run_slow_agents(ctx)

                n = self.decision_engine.reconcile(self.run_id)

                x = 0
                try:
                    x = reconcile_paper(self.repo, self.run_id)
                except Exception as e:
                    log.exception(f"paper reconcile failed: {e}")
                    self._queue_event(
                        ts=now,
                        level="ERROR",
                        component="paper",
                        message=f"paper reconcile failed: {e}",
                        payload={},
                    )

                self._queue_event(
                    ts=now,
                    level="INFO",
                    component="decision",
                    message=f"decisions written: {n} | paper executed: {x}",
                    payload={},
                )

        elif isinstance(ev, Alert):
            self._queue_event(
                ts=now,
                level=ev.severity,
                component="alert",
                message=f"{ev.code}: {ev.message}",
                payload={},
            )

    def run_forever(self) -> None:
        while not self._stop:
            now = datetime.now(timezone.utc)
            do_poll, do_reconcile = self.scheduler.tick(now)

            mono = time.monotonic()
            if do_poll and self.settings.enable_ingest and mono >= self._next_ingest_ts:
                try:
                    m_cnt, s_cnt = self.ingestor.ingest()
                    self._ingest_failures = 0
                    self._next_ingest_ts = 0.0
                    log.info(f"ingest: markets={m_cnt} snapshots={s_cnt}")
                    markets = self.repo.list_markets(limit=200)
                    market_ids = [m.market_id for m in markets]
                    self._latest_snapshots_cache = {}
                    if market_ids and hasattr(self.repo, "get_latest_snapshots_batch"):
                        try:
                            self._latest_snapshots_cache = self.repo.get_latest_snapshots_batch(market_ids)
                        except Exception:
                            log.warning("get_latest_snapshots_batch failed; using empty cache", exc_info=True)
                            self._latest_snapshots_cache = {}
                    for m in markets:
                        self.bus.publish(MarketTick(ts=now, market_id=m.market_id))
                except Exception as e:
                    self._ingest_failures += 1
                    retry_in = min(30.0, 0.5 * (2 ** (self._ingest_failures - 1)))
                    self._next_ingest_ts = time.monotonic() + retry_in
                    log.exception(f"ingest failed: {e}")
                    self.bus.publish(
                        Alert(
                            ts=now,
                            severity="ERROR",
                            code="INGEST_FAIL",
                            message=f"{e} | retry in {retry_in:.1f}s",
                        )
                    )

            # Orderbook collector (separate cadence)
            if mono >= self._next_book_ts:
                try:
                    active_ids, target_stats = self._active_orderbook_targets(top_n=30)
                    stats = self.book_collector.collect(active_ids)
                    stats["targets"] = target_stats
                    self._book_failures = 0
                    self._next_book_ts = mono + 3.0
                    if stats.get("errors"):
                        log.warning(f"orderbook: {stats}")
                        self._queue_event(
                            ts=now,
                            level="ERROR",
                            component="orderbook",
                            message="orderbook_errors",
                            payload=stats,
                        )
                except Exception as e:
                    self._book_failures += 1
                    retry_in = min(30.0, 0.5 * (2 ** (self._book_failures - 1)))
                    self._next_book_ts = mono + retry_in
                    log.exception(f"orderbook ingest failed: {e}")
                    self._queue_event(
                        ts=now,
                        level="ERROR",
                        component="orderbook",
                        message=str(e),
                        payload={},
                    )

            try:
                self._auto_agent.maybe_tick(repo=self.repo, run_id=self.run_id, now=now)
            except Exception as e:
                log.exception(f"auto_paper_agent tick failed: {e}")

            if do_reconcile:
                self.bus.publish(Timer(ts=now, purpose="reconcile"))

            for _ in range(500):
                ev = self.bus.pop()
                if ev is None:
                    break
                self._handle_event(ev)
            self._flush_events()
            if hasattr(self.repo, "flush_if_due"):
                try:
                    self.repo.flush_if_due()
                except Exception as e:
                    log.warning("repo.flush_if_due failed: %s", e)

            time.sleep(getattr(self.settings, "dispatcher_tick_sec", 1.0))
        self._flush_events()
        if hasattr(self.repo, "flush_writes"):
            try:
                self.repo.flush_writes()
            except Exception:
                log.warning("repo.flush_writes failed", exc_info=True)

    def _latest_snapshots_by_outcome(self, market_id: str) -> dict:
        """outcome -> {bid, ask, mid, spread, liquidity}

        Берём самые свежие строки по каждому outcome.
        """
        if market_id in self._latest_snapshots_cache:
            return self._latest_snapshots_cache.get(market_id, {})
        with self.repo.conn() as con:
            rows = con.execute(
                """
                SELECT outcome, bid, ask, mid, spread, liquidity
                FROM snapshots
                WHERE market_id = ?
                ORDER BY ts DESC
                LIMIT 50
                """,
                (market_id,),
            ).fetchall()

        out = {}
        for outcome, bid, ask, mid, spread, liq in rows:
            if outcome not in out:
                out[outcome] = {
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "spread": spread,
                    "liquidity": liq,
                }
            if "YES" in out and "NO" in out:
                break
        return out


def build_dispatcher(settings, repo, bus, run_id) -> Dispatcher:
    """Canonical dispatcher constructor."""
    return MainLoop(settings=settings, repo=repo, bus=bus, run_id=run_id)
