from __future__ import annotations

import subprocess
from pathlib import Path


def _mtime_fallback() -> str:
    root = Path(__file__).resolve().parents[2]
    static_dir = root / "ui" / "static"
    candidates = [
        static_dir / "ps_dashboard_organic.css",
        static_dir / "ps_terminal.css",
        static_dir / "ps_terminal.js",
    ]
    mtimes = []
    for p in candidates:
        try:
            mtimes.append(int(p.stat().st_mtime))
        except Exception:
            continue
    if mtimes:
        return f"m{max(mtimes)}"
    return "dev"


def get_static_version() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return out
    except Exception:
        pass
    return _mtime_fallback()
