from __future__ import annotations

from datetime import datetime, timezone
import uuid

from db.repo import Repo
from app.runtime_config import load_runtime_config
from utils.logging import get_logger, warn_exc

logger = get_logger("execution.simulator")

class PaperSimulator:
    """Paper trading ledger (minimal).

    We only store positions/trades tables. No automatic fills yet.
    Later: fill pending decisions_v0 into paper_trades and update paper_positions.
    """

    def __init__(self, repo: Repo):
        self.repo = repo

    def ensure(self) -> None:
        self.repo.ensure_paper_schema()

    def reset(self) -> None:
        with self.repo.conn() as con:
            con.execute("DELETE FROM paper_trades")
            con.execute("DELETE FROM paper_positions")

    @staticmethod
    def _fee_rate() -> float:
        try:
            _cfg, runtime = load_runtime_config()
            return float(getattr(runtime, "taker_fee_rate", 0.0) or 0.0)
        except Exception:
            warn_exc(logger, "simulator fee rate load failed")
            return 0.0

    def record_trade(self, run_id: str, market_id: str, outcome: str, side: str, qty: float, price: float, fee: float = 0.0, note: str = "") -> str:
        if fee == 0.0:
            fee_rate = self._fee_rate()
            if fee_rate:
                fee = float(qty) * float(price) * fee_rate
        trade_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self.repo.conn() as con:
            con.execute(
                """
                INSERT INTO paper_trades(trade_id, ts, run_id, market_id, outcome, side, qty, price, fee, note)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (trade_id, ts, run_id, market_id, outcome, side, float(qty), float(price), float(fee), note),
            )
        return trade_id
