from __future__ import annotations

"""One-command demo entrypoint.

Usage:
    python -m app.demo
"""

import os

def main() -> None:
    # DEMO should be reproducible and isolated
    os.environ.setdefault("PS_MODE", "DEMO")
    os.environ.setdefault("PS_DB_PATH", "polysyndicate_demo.db")
    # keep it safe by default
    os.environ.setdefault("PS_ENABLE_EXECUTION", "0")

    from app.main_v2 import main as run_main
    run_main()

if __name__ == "__main__":
    main()
