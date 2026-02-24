"""Position lifecycle management system."""
from __future__ import annotations

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from utils.time import now_utc, to_iso
from utils.logging import get_logger, warn_exc

logger = get_logger("execution.lifecycle")


class PositionState(str, Enum):
    """Position states."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ExitReason(str, Enum):
    """Position exit reasons."""
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    RISK_LIMIT = "RISK_LIMIT"
    MARKET_CLOSE = "MARKET_CLOSE"
    MANUAL = "MANUAL"
    STRATEGIC = "STRATEGIC"


@dataclass
class PositionConfig:
    """Position configuration."""
    take_profit_pct: float = 0.20  # 20% profit target
    stop_loss_pct: float = 0.10  # 10% loss limit
    max_hold_hours: int = 72  # Max 72 hours
    trailing_stop: bool = False
    trailing_stop_pct: float = 0.05


class PositionLifecycleManager:
    """Manage position lifecycle from entry to exit."""
    
    def __init__(self, repo, config: Optional[PositionConfig] = None):
        self.repo = repo
        self.config = config or PositionConfig()
    
    def create_position(
        self,
        market_id: str,
        outcome: str,
        side: str,
        price: float,
        qty: float,
        reason: str,
    ) -> str:
        """Create new position."""
        
        try:
            self.repo.ensure_paper_schema()
            
            with self.repo.conn() as con:
                cursor = con.execute(
                    """
                    INSERT INTO paper_positions(
                        position_id, market_id, outcome, side, price, qty,
                        status, opened_at, reason
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING position_id
                    """,
                    (
                        f"pos_{market_id}_{outcome}_{int(now_utc().timestamp())}",
                        market_id,
                        outcome,
                        side,
                        price,
                        qty,
                        PositionState.OPEN.value,
                        to_iso(now_utc()),
                        reason,
                    )
                )
                
                position_id = cursor.fetchone()[0]
                return position_id
        
        except Exception as e:
            raise Exception(f"Failed to create position: {e}")
    
    def check_exit_conditions(
        self,
        position_id: str,
        current_price: float,
    ) -> Optional[ExitReason]:
        """Check if position should be closed."""
        
        try:
            self.repo.ensure_paper_schema()
            
            with self.repo.conn() as con:
                row = con.execute(
                    """
                    SELECT market_id, outcome, side, price, qty, opened_at
                    FROM paper_positions
                    WHERE position_id = ? AND status = 'OPEN'
                    """,
                    (position_id,)
                ).fetchone()
                
                if not row:
                    return None
                
                entry_price = float(row[3])
                opened_at_str = row[5]
                
                # Calculate P&L
                if row[2] == "BUY":  # BUY side
                    pnl_pct = (current_price - entry_price) / entry_price
                else:  # SELL side
                    pnl_pct = (entry_price - current_price) / entry_price
                
                # Check take profit
                if pnl_pct >= self.config.take_profit_pct:
                    return ExitReason.TAKE_PROFIT
                
                # Check stop loss
                if pnl_pct <= -self.config.stop_loss_pct:
                    return ExitReason.STOP_LOSS
                
                # Check max hold time
                from utils.time import parse_iso
                opened_at = parse_iso(opened_at_str)
                hours_held = (now_utc() - opened_at).total_seconds() / 3600
                
                if hours_held >= self.config.max_hold_hours:
                    return ExitReason.MARKET_CLOSE
        
        except Exception:
            warn_exc(logger, "check_exit_conditions failed", position_id=position_id)
        
        return None
    
    def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: ExitReason,
    ) -> None:
        """Close position."""
        
        try:
            self.repo.ensure_paper_schema()
            
            with self.repo.conn() as con:
                # Update position
                con.execute(
                    """
                    UPDATE paper_positions
                    SET status = ?,
                        closed_at = ?,
                        exit_price = ?,
                        exit_reason = ?
                    WHERE position_id = ?
                    """,
                    (
                        PositionState.CLOSED.value,
                        to_iso(now_utc()),
                        exit_price,
                        exit_reason.value,
                        position_id,
                    )
                )
                
                # Record in history
                self._record_position_history(position_id, exit_price, exit_reason)
        
        except Exception as e:
            raise Exception(f"Failed to close position: {e}")
    
    def _record_position_history(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: ExitReason,
    ) -> None:
        """Record position to history."""
        
        try:
            with self.repo.conn() as con:
                # Create history table if not exists
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS position_history (
                        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        position_id TEXT,
                        market_id TEXT,
                        outcome TEXT,
                        entry_price REAL,
                        exit_price REAL,
                        qty REAL,
                        pnl REAL,
                        roi REAL,
                        opened_at TEXT,
                        closed_at TEXT,
                        exit_reason TEXT
                    )
                    """
                )
                
                # Get position details
                row = con.execute(
                    """
                    SELECT market_id, outcome, price, qty, opened_at, closed_at
                    FROM paper_positions
                    WHERE position_id = ?
                    """,
                    (position_id,)
                ).fetchone()
                
                if row:
                    entry_price = float(row[2])
                    qty = float(row[3])
                    pnl = (exit_price - entry_price) * qty
                    roi = (pnl / (entry_price * qty) * 100) if entry_price > 0 else 0
                    
                    # Insert to history
                    con.execute(
                        """
                        INSERT INTO position_history(
                            position_id, market_id, outcome, entry_price, exit_price,
                            qty, pnl, roi, opened_at, closed_at, exit_reason
                        )
                        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            position_id,
                            row[0],  # market_id
                            row[1],  # outcome
                            entry_price,
                            exit_price,
                            qty,
                            pnl,
                            roi,
                            row[4],  # opened_at
                            row[5],  # closed_at
                            exit_reason.value,
                        )
                    )
        
        except Exception:
            warn_exc(logger, "record_position_history failed", position_id=position_id)
    
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions."""
        
        positions = []
        
        try:
            self.repo.ensure_paper_schema()
            
            with self.repo.conn() as con:
                rows = con.execute(
                    """
                    SELECT position_id, market_id, outcome, side, price, qty, opened_at
                    FROM paper_positions
                    WHERE status = 'OPEN'
                    ORDER BY opened_at DESC
                    """
                ).fetchall()
                
                for row in rows:
                    positions.append({
                        "position_id": row[0],
                        "market_id": row[1],
                        "outcome": row[2],
                        "side": row[3],
                        "price": float(row[4]),
                        "qty": float(row[5]),
                        "opened_at": row[6],
                    })
        
        except Exception:
            warn_exc(logger, "get_open_positions failed")
        
        return positions
    
    def run_lifecycle_check(self) -> int:
        """Check all open positions for exit conditions."""
        
        closed_count = 0
        
        positions = self.get_open_positions()
        
        for pos in positions:
            try:
                # Get current price
                snapshots = self.repo.get_latest_snapshots(pos["market_id"])
                current_price = snapshots.get(pos["outcome"], {}).get("mid")
                
                if not current_price:
                    continue
                
                # Check exit conditions
                exit_reason = self.check_exit_conditions(
                    pos["position_id"],
                    current_price
                )
                
                if exit_reason:
                    self.close_position(
                        pos["position_id"],
                        current_price,
                        exit_reason
                    )
                    closed_count += 1
            
            except Exception:
                warn_exc(logger, "run_lifecycle_check failed for position", position_id=pos.get("position_id"))
                continue
        
        return closed_count
