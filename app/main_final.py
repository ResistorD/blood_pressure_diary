"""Deprecated entrypoint.

Use: `python -m app.main`
"""
from __future__ import annotations

import warnings


def main() -> None:
    warnings.warn(
        "app.main_final is deprecated; use `python -m app.main` instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from app.main import main as canonical_main

    canonical_main()


if __name__ == "__main__":
    main()
