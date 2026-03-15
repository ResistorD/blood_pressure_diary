from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Any
import os
import re
import threading
import time

from execution.executor import Executor
from app.runtime_config import bootstrap_live_credentials, load_runtime_config, resolve_trading_identity
from utils.logging import get_logger

logger = get_logger("execution.polymarket_executor")


@dataclass
class LiveGuard:
    max_notional: float
    max_orders_per_day: int
    dry_run: bool


@dataclass
class HumanOrderContext:
    market_id: str
    token_id: str
    outcome: str
    qty: float
    price: float
    notional: float
    ttl_seconds: float
    single_leg_smoke_mode: int = 1
    strategy: str = "ARB"
    leg_side: str = "BUY"


class ExecutorPolymarketCLOB(Executor):
    """Stage-0 executor for Polymarket CLOB (minimal live submit path)."""

    def __init__(self) -> None:
        _cfg, runtime = load_runtime_config()
        self._runtime = runtime
        self._guard = LiveGuard(
            max_notional=float(getattr(runtime, "live_max_notional", 0.0) or 0.0),
            max_orders_per_day=int(getattr(runtime, "live_max_orders_per_day", 0) or 0),
            dry_run=bool(getattr(runtime, "live_dry_run", True)),
        )
        self._execution_mode = str(getattr(runtime, "execution_mode", "paper")).lower()
        self._orders_today = 0
        self._orders_day = datetime.now(timezone.utc).date()
        self._cred_bootstrap: dict[str, Any] = bootstrap_live_credentials(runtime)
        self._client = None
        self._mm_probe_stats = {"placed": 0, "filled": 0, "canceled": 0}

    def _roll_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._orders_day:
            self._orders_day = today
            self._orders_today = 0

    def _guard_live(self, notional: float) -> None:
        if self._execution_mode != "live_stage0":
            raise RuntimeError("Execution mode must be LIVE_STAGE0")
        if self._guard.dry_run:
            raise RuntimeError("Live dry-run guard is enabled")
        if not bool(self._cred_bootstrap.get("success")):
            safe_error = str(self._cred_bootstrap.get("safe_error") or "").strip()
            missing = ",".join(self._cred_bootstrap.get("missing", [])[:4])
            msg = safe_error or (f"missing={missing}" if missing else "unknown bootstrap error")
            raise RuntimeError(f"Live credential bootstrap failed: {msg}")
        if self._guard.max_notional <= 0:
            raise RuntimeError("Live max notional guard is not configured")
        if notional > self._guard.max_notional:
            raise RuntimeError("Live max notional exceeded")
        self._roll_day()
        if self._guard.max_orders_per_day <= 0:
            raise RuntimeError("Live max orders per day guard is not configured")
        if self._orders_today >= self._guard.max_orders_per_day:
            raise RuntimeError("Live max orders per day exceeded")

    def _sensitive_values(self) -> list[str]:
        vals: list[str] = []
        try:
            vals.append(str(getattr(self._runtime, "private_key", "") or "").strip())
            vals.append(str(getattr(self._runtime, "polymarket_key", "") or "").strip())
            vals.append(str(getattr(self._runtime, "polymarket_secret", "") or "").strip())
            vals.append(str(getattr(self._runtime, "polymarket_passphrase", "") or "").strip())
        except Exception:
            pass
        try:
            creds = getattr(self._runtime, "_live_api_creds", None)
            if isinstance(creds, dict):
                vals.append(str(creds.get("api_key") or "").strip())
                vals.append(str(creds.get("api_secret") or "").strip())
                vals.append(str(creds.get("api_passphrase") or "").strip())
        except Exception:
            pass
        return [v for v in vals if v]

    def _redact_sensitive_text(self, text: str) -> str:
        out = str(text or "")
        for secret in self._sensitive_values():
            if len(secret) >= 4 and secret in out:
                out = out.replace(secret, "[REDACTED]")
        out = re.sub(r"(?i)\b(api[_-]?key|api[_-]?secret|passphrase|private[_-]?key)\s*=\s*[^,\s;]+", r"\1=[REDACTED]", out)
        return out

    @staticmethod
    def _trim_text(text: str, limit: int = 320) -> str:
        t = str(text or "").strip()
        if len(t) <= limit:
            return t
        return t[: max(0, limit - 3)] + "..."

    def _safe_error_summary(self, exc: Exception) -> str:
        parts: list[str] = [type(exc).__name__]
        msg = self._trim_text(self._redact_sensitive_text(str(exc or "")))
        if msg:
            parts.append(f"message={msg}")

        status_code = getattr(exc, "status_code", None)
        response_obj = getattr(exc, "response", None)
        if status_code is None and response_obj is not None:
            status_code = getattr(response_obj, "status_code", None)
        if status_code is not None:
            parts.append(f"status_code={status_code}")

        body_val = getattr(exc, "body", None)
        if body_val is None:
            body_val = getattr(exc, "error", None)
        if body_val is None:
            body_val = getattr(exc, "detail", None)
        if body_val is None and response_obj is not None:
            body_val = getattr(response_obj, "text", None)
        if body_val is not None:
            body_txt = self._trim_text(self._redact_sensitive_text(str(body_val)))
            if body_txt:
                parts.append(f"body={body_txt}")
        return " | ".join(parts)

    def _resolve_token_id(self, market_id: str) -> str:
        token_id = str(market_id or "").strip()
        if not token_id:
            raise ValueError("market_id/token_id is required")
        return token_id

    @staticmethod
    def _normalize_execution_style(value: Any) -> str:
        style = str(value or "").strip().lower()
        if style in {"direct", "legacy"}:
            return "direct"
        return "human_limit"

    def _trading_identity_context(self) -> dict[str, Any]:
        identity = resolve_trading_identity(self._runtime)
        signer = str(identity.get("signer_address") or "").strip() or "-"
        funder = str(identity.get("funder_address") or "").strip() or "-"
        effective_funder = str(identity.get("effective_funder_address") or "").strip() or signer
        account_type = str(identity.get("account_type") or "EOA").strip().upper() or "EOA"
        signature_type = int(identity.get("signature_type", 0) or 0)
        chain_id = int(identity.get("chain_id", 137) or 137)
        return {
            "signer_address": signer,
            "funder_address": funder,
            "effective_funder_address": effective_funder,
            "account_type": account_type,
            "signature_type": signature_type,
            "chain_id": chain_id,
        }

    def _validate_order_inputs(self, market_id: str, outcome: str, side: str, qty: float, limit_price: float) -> dict[str, Any]:
        side_u = str(side or "").strip().upper()
        if side_u not in {"BUY", "SELL"}:
            raise ValueError("Stage-0 live path only supports BUY/SELL sides")
        outcome_u = str(outcome or "").strip().upper()
        if outcome_u not in {"YES", "NO"}:
            raise ValueError("outcome must be YES or NO")
        qty_f = float(qty)
        if qty_f <= 0:
            raise ValueError("qty must be > 0")
        price_f = float(limit_price)
        if price_f <= 0 or price_f >= 1:
            raise ValueError("limit_price must be in (0,1)")
        token_id = self._resolve_token_id(market_id)
        return {
            "token_id": token_id,
            "outcome": outcome_u,
            "side": side_u,
            "qty": qty_f,
            "limit_price": price_f,
            "notional": qty_f * price_f,
        }

    def _live_api_creds(self) -> dict[str, str]:
        creds = getattr(self._runtime, "_live_api_creds", None)
        if not isinstance(creds, dict):
            creds = {}
        api_key = str(creds.get("api_key") or "").strip()
        api_secret = str(creds.get("api_secret") or "").strip()
        api_passphrase = str(creds.get("api_passphrase") or "").strip()
        if not api_key or not api_secret or not api_passphrase:
            raise RuntimeError("Live API credentials are unavailable")
        return {"api_key": api_key, "api_secret": api_secret, "api_passphrase": api_passphrase}

    def _build_trading_client(self):
        if self._client is not None:
            return self._client
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds

        creds = self._live_api_creds()
        host = str(getattr(self._runtime, "polymarket_api_url", "") or "").strip()
        private_key = str(getattr(self._runtime, "private_key", "") or "").strip()
        if not host:
            raise RuntimeError("POLYMARKET_API_URL is required")
        if not private_key:
            raise RuntimeError("PRIVATE_KEY is required")

        kwargs = {
            "host": host,
            "chain_id": int(getattr(self._runtime, "polymarket_chain_id", 137) or 137),
            "key": private_key,
            "creds": ApiCreds(
                api_key=creds["api_key"],
                api_secret=creds["api_secret"],
                api_passphrase=creds["api_passphrase"],
            ),
            "signature_type": int(getattr(self._runtime, "polymarket_signature_type", 0) or 0),
        }
        funder = str(getattr(self._runtime, "polymarket_funder", "") or "").strip()
        if funder:
            kwargs["funder"] = funder
        self._client = ClobClient(**kwargs)
        return self._client

    @staticmethod
    def _extract_order_identity(payload: Any) -> tuple[Optional[str], Optional[str]]:
        if isinstance(payload, dict):
            order_id = str(
                payload.get("orderID")
                or payload.get("orderId")
                or payload.get("id")
                or payload.get("order_id")
                or ""
            ).strip() or None
            status = str(payload.get("status") or "").strip() or None
            return order_id, status
        order_id = str(getattr(payload, "order_id", "") or getattr(payload, "id", "") or "").strip() or None
        status = str(getattr(payload, "status", "") or "").strip() or None
        return order_id, status

    def _human_ctx(self, params: dict[str, Any], ttl_seconds: float, metadata: dict[str, Any] | None) -> HumanOrderContext:
        meta = metadata if isinstance(metadata, dict) else {}
        market_id = str(meta.get("market_id") or params["token_id"]).strip() or params["token_id"]
        return HumanOrderContext(
            market_id=market_id,
            token_id=params["token_id"],
            outcome=params["outcome"],
            qty=float(params["qty"]),
            price=float(params["limit_price"]),
            notional=float(params["notional"]),
            ttl_seconds=max(0.0, float(ttl_seconds or 0.0)),
            single_leg_smoke_mode=int(meta.get("single_leg_smoke_mode", 1) or 0),
            strategy=str(meta.get("strategy") or "ARB").strip().upper() or "ARB",
            leg_side=str(meta.get("leg_side") or params["side"]).strip().upper() or str(params["side"]).strip().upper(),
        )

    def _query_order_status(self, client: Any, order_id: str) -> Optional[str]:
        method_specs = [
            ("get_order", lambda fn: fn(order_id)),
            ("get_order_status", lambda fn: fn(order_id)),
            ("get_orders", lambda fn: fn([order_id])),
            ("get_open_order", lambda fn: fn(order_id)),
        ]
        for method_name, caller in method_specs:
            fn = getattr(client, method_name, None)
            if not callable(fn):
                continue
            try:
                payload = caller(fn)
            except Exception:
                continue
            if isinstance(payload, list) and payload:
                payload = payload[0]
            _oid, status = self._extract_order_identity(payload)
            if status:
                return str(status).strip().lower()
        return None

    def _cancel_order_live(self, client: Any, order_id: str) -> Any:
        method_specs = [
            ("cancel", lambda fn: fn(order_id)),
            ("cancel_order", lambda fn: fn(order_id)),
            ("cancel_orders", lambda fn: fn([order_id])),
            ("cancel_all", lambda fn: fn()),
        ]
        last_exc: Exception | None = None
        for method_name, caller in method_specs:
            fn = getattr(client, method_name, None)
            if not callable(fn):
                continue
            try:
                return caller(fn)
            except Exception as e:
                last_exc = e
        if last_exc is not None:
            raise last_exc
        raise NotImplementedError("Polymarket CLOB client cancel method is unavailable")

    def _run_ttl_cancel_worker(self, order_id: str, ctx: HumanOrderContext) -> None:
        if ctx.ttl_seconds <= 0.0:
            return
        time.sleep(ctx.ttl_seconds)
        logger.info(
            "HUMAN_ORDER_TTL_EXPIRED market_id=%s token_id=%s order_id=%s price=%.6f qty=%.6f notional=%.6f ttl_seconds=%.3f",
            ctx.market_id,
            ctx.token_id,
            order_id,
            ctx.price,
            ctx.qty,
            ctx.notional,
            ctx.ttl_seconds,
        )
        if ctx.strategy == "MM":
            logger.info(
                "MM_ORDER_REPRICE_READY market_id=%s token_id=%s side=%s order_id=%s ttl_seconds=%.3f",
                ctx.market_id,
                ctx.token_id,
                ctx.leg_side,
                order_id,
                ctx.ttl_seconds,
            )
        try:
            client = self._build_trading_client()
            status = self._query_order_status(client, order_id)
            if status in {"filled", "matched", "cancelled", "canceled"}:
                if ctx.strategy == "MM":
                    event = "MM_ORDER_FILLED" if status in {"filled", "matched"} else "MM_ORDER_CANCEL"
                    stat_key = "filled" if status in {"filled", "matched"} else "canceled"
                    self._mm_probe_stats[stat_key] = int(self._mm_probe_stats.get(stat_key, 0) or 0) + 1
                    logger.info(
                        "%s market_id=%s token_id=%s side=%s order_id=%s status=%s",
                        event,
                        ctx.market_id,
                        ctx.token_id,
                        ctx.leg_side,
                        order_id,
                        status,
                    )
                logger.info(
                    "HUMAN_ORDER_CANCEL_OK market_id=%s token_id=%s order_id=%s skipped=1 status=%s",
                    ctx.market_id,
                    ctx.token_id,
                    order_id,
                    status,
                )
                return
            logger.info(
                "HUMAN_ORDER_CANCEL_ATTEMPT market_id=%s token_id=%s order_id=%s price=%.6f qty=%.6f notional=%.6f status=%s",
                ctx.market_id,
                ctx.token_id,
                order_id,
                ctx.price,
                ctx.qty,
                ctx.notional,
                status or "unknown",
            )
            payload = self._cancel_order_live(client, order_id)
            _cancel_id, cancel_status = self._extract_order_identity(payload)
            if ctx.strategy == "MM":
                self._mm_probe_stats["canceled"] = int(self._mm_probe_stats.get("canceled", 0) or 0) + 1
                logger.info(
                    "MM_ORDER_CANCEL market_id=%s token_id=%s side=%s order_id=%s status=%s",
                    ctx.market_id,
                    ctx.token_id,
                    ctx.leg_side,
                    order_id,
                    cancel_status or status or "unknown",
                )
            logger.info(
                "HUMAN_ORDER_CANCEL_OK market_id=%s token_id=%s order_id=%s status=%s",
                ctx.market_id,
                ctx.token_id,
                order_id,
                cancel_status or status or "unknown",
            )
        except Exception as e:
            safe_error = self._safe_error_summary(e)
            logger.warning(
                "HUMAN_ORDER_CANCEL_FAIL market_id=%s token_id=%s order_id=%s safe_error=%s",
                ctx.market_id,
                ctx.token_id,
                order_id,
                safe_error,
            )

    def _start_ttl_cancel_worker(self, order_id: str, ctx: HumanOrderContext) -> None:
        if ctx.ttl_seconds <= 0.0:
            return
        worker = threading.Thread(
            target=self._run_ttl_cancel_worker,
            args=(order_id, ctx),
            name=f"human-ttl-cancel:{order_id[:24]}",
            daemon=True,
        )
        worker.start()

    def place_order(
        self,
        market_id: str,
        outcome: str,
        side: str,
        qty: float,
        limit_price: float,
        *,
        ttl_seconds: float | None = None,
        execution_style: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        try:
            params = self._validate_order_inputs(market_id, outcome, side, qty, limit_price)
        except Exception as e:
            raise RuntimeError(f"Invalid live order parameters: {self._safe_error_summary(e)}") from e

        self._guard_live(params["notional"])
        identity = self._trading_identity_context()
        style = self._normalize_execution_style(
            execution_style or getattr(self._runtime, "live_exec_style", os.getenv("PS_LIVE_EXEC_STYLE", os.getenv("LIVE_EXEC_STYLE", "human_limit")))
        )
        human_ctx = self._human_ctx(params, float(ttl_seconds or 0.0), metadata)
        if style == "human_limit":
            logger.info(
                "HUMAN_ORDER_PLACE_ATTEMPT market_id=%s token_id=%s price=%.6f qty=%.6f notional=%.6f ttl_seconds=%.3f single_leg_smoke_mode=%s",
                human_ctx.market_id,
                human_ctx.token_id,
                human_ctx.price,
                human_ctx.qty,
                human_ctx.notional,
                human_ctx.ttl_seconds,
                human_ctx.single_leg_smoke_mode,
            )
        logger.info(
            "LIVE_ORDER_SUBMIT_ATTEMPT token_id=%s outcome=%s side=%s qty=%.6f price=%.6f notional=%.6f "
            "signer_address=%s funder_address=%s effective_funder_address=%s account_type=%s signature_type=%s chain_id=%s",
            params["token_id"],
            params["outcome"],
            params["side"],
            params["qty"],
            params["limit_price"],
            params["notional"],
            identity["signer_address"],
            identity["funder_address"],
            identity["effective_funder_address"],
            identity["account_type"],
            identity["signature_type"],
            identity["chain_id"],
        )

        try:
            from py_clob_client.clob_types import OrderArgs

            client = self._build_trading_client()
            order = OrderArgs(
                token_id=params["token_id"],
                price=params["limit_price"],
                size=params["qty"],
                side=params["side"],
            )
            response = client.create_and_post_order(order)
            order_id, status = self._extract_order_identity(response)
            self._orders_today += 1
            logger.info(
                "LIVE_ORDER_SUBMIT_SUCCESS token_id=%s order_id=%s status=%s",
                params["token_id"],
                order_id or "unknown",
                status or "unknown",
            )
            if style == "human_limit":
                logger.info(
                    "HUMAN_ORDER_PLACE_OK market_id=%s token_id=%s order_id=%s price=%.6f qty=%.6f notional=%.6f status=%s",
                    human_ctx.market_id,
                    human_ctx.token_id,
                    order_id or "unknown",
                    human_ctx.price,
                    human_ctx.qty,
                    human_ctx.notional,
                    status or "unknown",
                )
                if human_ctx.strategy == "MM":
                    self._mm_probe_stats["placed"] = int(self._mm_probe_stats.get("placed", 0) or 0) + 1
                    logger.info(
                        "MM_ORDER_PLACE market_id=%s token_id=%s side=%s order_id=%s price=%.6f qty=%.6f status=%s",
                        human_ctx.market_id,
                        human_ctx.token_id,
                        human_ctx.leg_side,
                        order_id or "unknown",
                        human_ctx.price,
                        human_ctx.qty,
                        status or "unknown",
                    )
                self._start_ttl_cancel_worker(order_id or f"submitted:{params['token_id']}", human_ctx)
            return order_id or f"submitted:{params['token_id']}"
        except Exception as e:
            safe_error = self._safe_error_summary(e)
            logger.warning(
                "LIVE_ORDER_SUBMIT_FAILED token_id=%s signer_address=%s effective_funder_address=%s safe_error=%s",
                params["token_id"],
                identity["signer_address"],
                identity["effective_funder_address"],
                safe_error,
            )
            if style == "human_limit":
                logger.warning(
                    "HUMAN_ORDER_PLACE_FAIL market_id=%s token_id=%s price=%.6f qty=%.6f notional=%.6f safe_error=%s",
                    human_ctx.market_id,
                    human_ctx.token_id,
                    human_ctx.price,
                    human_ctx.qty,
                    human_ctx.notional,
                    safe_error,
                )
            raise RuntimeError(f"Live order submission failed: {safe_error}") from e

    def get_mm_probe_stats(self) -> dict[str, int]:
        return {
            "placed": int(self._mm_probe_stats.get("placed", 0) or 0),
            "filled": int(self._mm_probe_stats.get("filled", 0) or 0),
            "canceled": int(self._mm_probe_stats.get("canceled", 0) or 0),
        }

    def cancel_order(self, order_id: str) -> None:
        if self._execution_mode != "live_stage0":
            raise RuntimeError("Execution mode must be LIVE_STAGE0")
        oid = str(order_id or "").strip()
        if not oid:
            raise ValueError("order_id is required")
        client = self._build_trading_client()
        self._cancel_order_live(client, oid)
