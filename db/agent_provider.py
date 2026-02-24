from __future__ import annotations

from typing import Any, Dict, List


class RepoAgentDataProvider:
    """Adapter exposing a narrow read API for agents.

    This decouples agents from the full Repo God object and simplifies tests:
    tests can stub only this tiny interface.
    """

    def __init__(self, repo: Any):
        self.repo = repo

    def list_markets(self, limit: int = 500) -> List[Any]:
        if hasattr(self.repo, "markets"):
            return list(self.repo.markets.list_markets(limit=limit))
        if hasattr(self.repo, "list_markets"):
            return list(self.repo.list_markets(limit=limit))
        return []

    def get_latest_snapshots(self, market_id: str) -> Dict[str, Dict]:
        if hasattr(self.repo, "get_latest_snapshots"):
            return dict(self.repo.get_latest_snapshots(market_id) or {})
        return {}

    def list_open_positions(self) -> List[Dict[str, Any]]:
        if hasattr(self.repo, "paper"):
            return list(self.repo.paper.list_open_positions())
        out: List[Dict[str, Any]] = []
        try:
            if hasattr(self.repo, "ensure_paper_schema"):
                self.repo.ensure_paper_schema()
            with self.repo.conn() as con:
                rows = con.execute(
                    "SELECT market_id, outcome, qty, price FROM paper_positions WHERE status='OPEN'"
                ).fetchall()
                for row in rows:
                    out.append(
                        {
                            "market_id": row[0],
                            "outcome": row[1],
                            "notional": float(row[2]) * float(row[3]),
                        }
                    )
        except Exception:
            return []
        return out
