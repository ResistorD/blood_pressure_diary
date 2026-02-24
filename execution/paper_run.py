from __future__ import annotations

import argparse
import os

from db.repo import Repo
from execution.reconcile import reconcile_paper
from utils.logging import get_logger

logger = get_logger("execution.paper_run")


def _guess_db_path() -> str:
    env = os.environ.get("POLYSYN_DB") or os.environ.get("DATABASE_PATH")
    if env:
        return env
    return "polysyndicate.db"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--db", type=str, default="polysyndicate.db")
    args = parser.parse_args()

    from db.repo import Repo
    from execution.reconcile import reconcile_paper
    from execution.paper_executor import execute_pending_paper

    repo = Repo(args.db)

    run_id = "paper_run"

    # 1. enqueue from decisions
    enqueued = reconcile_paper(repo, run_id=run_id)

    # 2. execute pending
    executed = execute_pending_paper(repo, run_id=run_id, limit=args.limit)

    logger.info("paper_run: enqueued %s, executed %s", enqueued, executed)



if __name__ == "__main__":
    main()
