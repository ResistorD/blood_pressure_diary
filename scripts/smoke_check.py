from __future__ import annotations

import os
import sys
import compileall
import sqlite3


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.logging import get_logger

logger = get_logger("scripts.smoke_check")


def _fail(msg: str) -> int:
    logger.error("SMOKE_CHECK_FAIL: %s", msg)
    return 1


def _check_compileall() -> bool:
    ok = compileall.compile_dir(ROOT, quiet=1)
    if not ok:
        return False
    return True


def _check_imports() -> tuple[bool, str]:
    try:
        import app.main  # noqa: F401
    except Exception as e:
        return False, f"import app.main failed: {e}"
    try:
        import api.http  # noqa: F401
    except Exception as e:
        return False, f"import api.http failed: {e}"
    try:
        import decision.engine  # noqa: F401
    except Exception as e:
        return False, f"import decision.engine failed: {e}"
    try:
        from dispatcher.loop import build_dispatcher  # noqa: F401
    except Exception as e:
        return False, f"import dispatcher.loop.build_dispatcher failed: {e}"
    try:
        from app.settings import Settings  # noqa: F401
    except Exception as e:
        return False, f"import app.settings.Settings failed: {e}"
    return True, ""


def _check_templates() -> tuple[bool, str]:
    templates_dir = os.path.join(ROOT, "ui", "templates")
    required = [
        "_base.html",
        "overview.html",
        "signals.html",
        "decisions.html",
        "positions.html",
        "case_details.html",
        "deprioritize.html",
    ]
    missing = [name for name in required if not os.path.isfile(os.path.join(templates_dir, name))]
    if missing:
        return False, f"missing templates: {', '.join(missing)}"
    return True, ""


def _check_deprioritize_schema() -> tuple[bool, str]:
    try:
        from app.runtime_config import load_runtime_config
        from app.main import _resolve_db_path
    except Exception as e:
        return False, f"db path resolve import failed: {e}"

    try:
        _config, settings = load_runtime_config()
        db_path = _resolve_db_path(settings)
    except Exception as e:
        return False, f"db path resolve failed: {e}"

    if not os.path.exists(db_path):
        return False, f"db file not found: {db_path}"

    con = None
    try:
        con = sqlite3.connect(db_path)
        con.execute("SELECT 1 FROM deprioritize_rules LIMIT 1;")
    except Exception as e:
        return False, f"deprioritize_rules missing or query failed: {e}"
    finally:
        if con is not None:
            con.close()

    return True, ""


def _check_deprioritize_mode() -> tuple[bool, str]:
    try:
        from app.runtime_config import load_runtime_config
    except Exception as e:
        return False, f"deprioritize mode import failed: {e}"
    try:
        _config, settings = load_runtime_config()
        mode = str(getattr(settings, "deprioritize_mode", "ui") or "ui").strip().lower()
    except Exception as e:
        return False, f"deprioritize mode read failed: {e}"
    if mode not in {"off", "ui", "pipeline"}:
        return False, f"invalid DEPRIORITIZE_MODE: {mode}"
    return True, ""


def _check_dispatcher_contract() -> tuple[bool, str]:
    try:
        import dispatcher.loop as loop_mod
    except Exception as e:
        return False, f"dispatcher.loop import failed: {e}"
    if not hasattr(loop_mod, "build_dispatcher"):
        return False, "dispatcher.loop.build_dispatcher missing"
    return True, ""


def _check_table_sanity() -> tuple[bool, str]:
    try:
        from scripts.table_sanity_check import run_checks
    except Exception as e:
        return False, f"table sanity import failed: {e}"
    issues = run_checks()
    if issues:
        return False, "table sanity issues:\n" + "\n".join(issues)
    return True, ""


def main() -> int:
    if not _check_compileall():
        return _fail("compileall failed")

    ok, msg = _check_imports()
    if not ok:
        return _fail(msg)

    ok, msg = _check_templates()
    if not ok:
        return _fail(msg)

    ok, msg = _check_deprioritize_schema()
    if not ok:
        return _fail(msg)

    ok, msg = _check_deprioritize_mode()
    if not ok:
        return _fail(msg)

    ok, msg = _check_dispatcher_contract()
    if not ok:
        return _fail(msg)

    ok, msg = _check_table_sanity()
    if not ok:
        return _fail(msg)

    logger.info("SMOKE_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
