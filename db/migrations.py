from __future__ import annotations

from db.repo import Repo

def apply_migrations(repo: Repo) -> None:
    """Idempotent runtime migrations.

    We keep SQLite migrations simple: create missing tables / columns in code.
    """
    repo.ensure_decisions_schema()
    repo.ensure_decisions_v0_schema()
    repo.ensure_settings_schema()
    repo.ensure_markets_schema()
    repo.ensure_snapshots_schema()
    repo.ensure_orderbook_schema()
    repo.ensure_signals_schema()
    repo.ensure_paper_schema()
    repo.ensure_paper_queue_schema()
