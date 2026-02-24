"""P&L (Profit & Loss) tracking engine."""
from __future__ import annotations

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from utils.time import now_utc
from utils.logging import get_logger, warn_exc

logger = get_logger("execution.pnl_tracker")


@dataclass
class PositionPnL:
    """P&L for a single position."""
    position_id: str
    market_id: str
    outcome: str
    entry_price: float
    current_price: float
    qty: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    roi: float  # Return on investment %
    
    @property
    def is_profitable(self) -> bool:
        """Check if position is profitable."""
        return self.total_pnl > 0


@dataclass
class PortfolioPnL:
    """Portfolio-level P&L."""
    total_realized: float
    total_unrealized: float
    total_pnl: float
    total_invested: float
    roi: float
    num_positions: int
    num_profitable: int
    win_rate: float
    largest_winner: Optional[PositionPnL]
    largest_loser: Optional[PositionPnL]
    fees_paid: float = 0.0
    net_pnl: float = 0.0
    roi_net: float = 0.0


class PnLTracker:
    """Track profit and loss for positions."""
    
    def __init__(self, repo):
        self.repo = repo
    
    def calculate_position_pnl(
        self,
        position_id: str,
        market_id: str,
        outcome: str,
        entry_price: float,
        current_price: float,
        qty: float,
        realized_pnl: float = 0.0
    ) -> PositionPnL:
        """Calculate P&L for a position."""
        
        # Unrealized P&L = (current_price - entry_price) * qty
        unrealized_pnl = (current_price - entry_price) * qty
        
        # Total P&L
        total_pnl = realized_pnl + unrealized_pnl
        
        # ROI
        cost_basis = entry_price * qty
        roi = (total_pnl / cost_basis * 100) if cost_basis > 0 else 0.0
        
        return PositionPnL(
            position_id=position_id,
            market_id=market_id,
            outcome=outcome,
            entry_price=entry_price,
            current_price=current_price,
            qty=qty,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=total_pnl,
            roi=roi,
        )
    
    def calculate_portfolio_pnl(
        self,
        positions: List[PositionPnL],
        fees_paid: float = 0.0,
    ) -> PortfolioPnL:
        """Calculate portfolio-level P&L."""
        
        if not positions:
            return PortfolioPnL(
                total_realized=0.0,
                total_unrealized=0.0,
                total_pnl=0.0,
                total_invested=0.0,
                roi=0.0,
                num_positions=0,
                num_profitable=0,
                win_rate=0.0,
                largest_winner=None,
                largest_loser=None,
                fees_paid=float(fees_paid or 0.0),
                net_pnl=-float(fees_paid or 0.0),
                roi_net=0.0,
            )
        
        total_realized = sum(p.realized_pnl for p in positions)
        total_unrealized = sum(p.unrealized_pnl for p in positions)
        total_pnl = sum(p.total_pnl for p in positions)
        total_invested = sum(p.entry_price * p.qty for p in positions)
        
        roi = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0
        net_pnl = total_pnl - float(fees_paid or 0.0)
        roi_net = (net_pnl / total_invested * 100) if total_invested > 0 else 0.0
        
        num_profitable = sum(1 for p in positions if p.is_profitable)
        win_rate = (num_profitable / len(positions) * 100) if positions else 0.0
        
        # Find largest winner/loser
        sorted_by_pnl = sorted(positions, key=lambda p: p.total_pnl, reverse=True)
        largest_winner = sorted_by_pnl[0] if sorted_by_pnl else None
        largest_loser = sorted_by_pnl[-1] if sorted_by_pnl else None
        
        return PortfolioPnL(
            total_realized=total_realized,
            total_unrealized=total_unrealized,
            total_pnl=total_pnl,
            total_invested=total_invested,
            roi=roi,
            num_positions=len(positions),
            num_profitable=num_profitable,
            win_rate=win_rate,
            largest_winner=largest_winner,
            largest_loser=largest_loser,
            fees_paid=float(fees_paid or 0.0),
            net_pnl=net_pnl,
            roi_net=roi_net,
        )

    def _get_fees_paid(self) -> float:
        try:
            self.repo.ensure_paper_schema()
            with self.repo.conn() as con:
                row = con.execute(
                    "SELECT COALESCE(SUM(fee), 0.0) AS fees_paid FROM paper_trades"
                ).fetchone()
            return float(row["fees_paid"] or 0.0) if row else 0.0
        except Exception:
            return 0.0
    
    def get_current_portfolio_pnl(self) -> PortfolioPnL:
        """Get current portfolio P&L."""
        
        positions_pnl: List[PositionPnL] = []
        fees_paid = 0.0
        
        try:
            # Get open positions
            self.repo.ensure_paper_schema()
            fees_paid = self._get_fees_paid()
            
            with self.repo.conn() as con:
                rows = con.execute(
                    """
                    SELECT position_id, market_id, outcome, price, qty
                    FROM paper_positions
                    WHERE status = 'OPEN'
                    """
                ).fetchall()
                
                for row in rows:
                    position_id = row[0]
                    market_id = row[1]
                    outcome = row[2]
                    entry_price = float(row[3])
                    qty = float(row[4])
                    
                    # Get current price
                    try:
                        snapshots = self.repo.get_latest_snapshots(market_id)
                        current_price = snapshots.get(outcome, {}).get("mid", entry_price)
                    except Exception:
                        current_price = entry_price
                    
                    # Calculate P&L
                    pnl = self.calculate_position_pnl(
                        position_id=position_id,
                        market_id=market_id,
                        outcome=outcome,
                        entry_price=entry_price,
                        current_price=current_price,
                        qty=qty,
                        realized_pnl=0.0,
                    )
                    
                    positions_pnl.append(pnl)
        
        except Exception as e:
            # Return empty portfolio on error
            pass
        
        return self.calculate_portfolio_pnl(positions_pnl, fees_paid=fees_paid)
    
    def record_pnl_snapshot(self, portfolio_pnl: PortfolioPnL) -> None:
        """Record P&L snapshot to database."""
        
        try:
            with self.repo.conn() as con:
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pnl_snapshots (
                        snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        total_realized REAL,
                        total_unrealized REAL,
                        total_pnl REAL,
                        total_invested REAL,
                        roi REAL,
                        num_positions INTEGER,
                        num_profitable INTEGER,
                        win_rate REAL
                    )
                    """
                )

            row = (
                now_utc().isoformat(),
                portfolio_pnl.total_realized,
                portfolio_pnl.total_unrealized,
                portfolio_pnl.total_pnl,
                portfolio_pnl.total_invested,
                portfolio_pnl.roi,
                portfolio_pnl.num_positions,
                portfolio_pnl.num_profitable,
                portfolio_pnl.win_rate,
            )

            def _op(con):
                con.execute(
                    """
                    INSERT INTO pnl_snapshots(
                        ts, total_realized, total_unrealized, total_pnl,
                        total_invested, roi, num_positions, num_profitable, win_rate
                    )
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    row,
                )

            if hasattr(self.repo, "enqueue_write"):
                self.repo.enqueue_write(_op)
            else:
                with self.repo.conn() as con:
                    _op(con)
        
        except Exception:
            warn_exc(logger, "pnl snapshot write failed")
    
    def get_pnl_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get P&L history for last N hours."""
        
        history = []
        
        try:
            with self.repo.conn() as con:
                rows = con.execute(
                    """
                    SELECT ts, total_pnl, roi, num_positions
                    FROM pnl_snapshots
                    WHERE ts >= datetime('now', '-' || ? || ' hours')
                    ORDER BY ts DESC
                    LIMIT 100
                    """,
                    (hours,)
                ).fetchall()
                
                for row in rows:
                    history.append({
                        "ts": row[0],
                        "total_pnl": row[1],
                        "roi": row[2],
                        "num_positions": row[3],
                    })
        
        except Exception:
            warn_exc(logger, "get_pnl_history failed")
        
        return history
