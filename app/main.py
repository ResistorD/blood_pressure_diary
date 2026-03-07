from __future__ import annotations

import os
import logging
import threading
import uuid
from datetime import datetime, timezone
from types import ModuleType
from dataclasses import dataclass
from typing import Any, Callable

import uvicorn

from api.http import create_app
from app.settings import Settings, load_settings
from db.repo import Repo
from execution.polymarket_executor import ExecutorPolymarketCLOB
from utils.logging import get_logger

logger = get_logger("app.main")

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _git_hash() -> str:
    return os.getenv("GIT_HASH", "")


def _config_hash() -> str:
    return os.getenv("CONFIG_HASH", "")

# Execution mode selector: keep canonical paper flow unless EXECUTION_MODE=live.
def build_executor(settings: Settings):
    mode = str(getattr(settings, "execution_mode", "paper")).lower()
    if mode == "live":
        return ExecutorPolymarketCLOB()
    return None

@dataclass
class DispatcherHandle:
    loop_obj: Any | None
    thread: threading.Thread

    def stop(self, timeout_sec: float = 10.0) -> None:
        try:
            if self.loop_obj is not None and hasattr(self.loop_obj, "stop"):
                self.loop_obj.stop()
        except Exception:
            logger.warning("dispatcher stop failed", exc_info=True)
        try:
            if self.thread.is_alive():
                self.thread.join(timeout=timeout_sec)
        except Exception:
            logger.warning("dispatcher thread join failed", exc_info=True)


def _pick_dispatcher_target(loop_mod: ModuleType, settings: Any, repo: Any, bus: Any, run_id: str) -> tuple[Any | None, Callable[[], None]]:
    """
    Normalize multiple historical shapes of dispatcher/loop.py.

    Supported forms:
      1. A class (DispatcherLoop / Dispatcher / Loop / etc) with method run_forever(self)
      2. A factory function loop(...) returning an object with run_forever()
      3. A module-level function run_forever(settings, repo, bus, run_id)
    """
    # 3) module-level run_forever
    fn = getattr(loop_mod, "run_forever", None)
    if callable(fn):
        return None, lambda: fn(settings, repo, bus, run_id)

    # 2) factory function loop()
    factory = getattr(loop_mod, "loop", None)
    if callable(factory):
        obj = factory(settings=settings, repo=repo, bus=bus, run_id=run_id)
        rf = getattr(obj, "run_forever", None)
        if callable(rf):
            return obj, rf

    # 1) preferred class names
    preferred_names = ["DispatcherLoop", "Dispatcher", "Loop"]
    for name in preferred_names:
        cls = getattr(loop_mod, name, None)
        if isinstance(cls, type) and callable(getattr(cls, "run_forever", None)):
            inst = cls(settings=settings, repo=repo, bus=bus, run_id=run_id)
            return inst, inst.run_forever

    # brute-force: any class with run_forever
    for _, obj in vars(loop_mod).items():
        if isinstance(obj, type) and callable(getattr(obj, "run_forever", None)):
            try:
                inst = obj(settings=settings, repo=repo, bus=bus, run_id=run_id)
                return inst, inst.run_forever
            except Exception:
                continue

    raise ImportError(
        "dispatcher/loop.py: cannot find a dispatcher runner. "
        "Expected either: run_forever(settings,repo,bus,run_id), or loop(...)->obj.run_forever(), "
        "or a class with run_forever()."
    )

def _resolve_db_path(settings: Settings) -> str:
    """Resolve DB path reliably across different working directories.

    Priority:
      1) PS_DB_PATH env / AppSettings.db_path if explicitly set (and exists)
      2) Existing polysyndicate.db in common locations (cwd, project root, ./data, ./db)
      3) Fallback to <project_root>/polysyndicate.db
    """
    import os
    from pathlib import Path

    # If env/settings already point to a file that exists, trust it.
    try:
        candidate = Path(getattr(settings, "db_path", "") or "")
        if str(candidate) and candidate.exists():
            return str(candidate.resolve())
    except Exception:
        logger.warning("db_path candidate resolution failed", exc_info=True)

    here = Path.cwd()

    # project root = folder that contains this file's parent (app/) -> root
    project_root = Path(__file__).resolve().parents[1]

    candidates = [
        Path(os.getenv("PS_DB_PATH", "")) if os.getenv("PS_DB_PATH") else None,
        here / "polysyndicate.db",
        project_root / "polysyndicate.db",
        project_root / "data" / "polysyndicate.db",
        project_root / "db" / "polysyndicate.db",
        here / "data" / "polysyndicate.db",
        here / "db" / "polysyndicate.db",
    ]

    best = None
    best_size = -1
    for c in candidates:
        if not c:
            continue
        try:
            c = Path(c)
            if c.exists() and c.is_file():
                sz = c.stat().st_size
                if sz > best_size:
                    best = c
                    best_size = sz
        except Exception:
            logger.warning("db_path candidate stat failed", exc_info=True)
            continue

    if best is not None:
        return str(best.resolve())

    # fallback: create in project root (not in whatever random cwd)
    return str((project_root / "polysyndicate.db").resolve())

def main() -> None:
    settings = load_settings()
    log = logger
    if str(getattr(settings, "execution_mode", "paper")).lower() == "live":
        log.warning(
            "LIVE mode selected; executor safeguards enabled; dry_run=%s",
            getattr(settings, "live_dry_run", True),
        )

    settings.db_path = _resolve_db_path(settings)
    log.info("DB path (main): %s", settings.db_path)
    if not os.path.exists(settings.db_path):
        log.warning("DB does not exist yet, will be created: %s", settings.db_path)

    repo = Repo(settings.db_path)
    repo.init_schema("db/schema.sql")
    if hasattr(repo, "set_flush_sec"):
        repo.set_flush_sec(getattr(settings, "db_flush_sec", 3.0))
    try:
        setattr(repo, "deprioritize_mode", getattr(settings, "deprioritize_mode", "ui"))
        setattr(repo, "deprioritize_min_weight", float(getattr(settings, "deprioritize_min_weight", 0.05)))
    except Exception:
        logger.warning("failed to apply deprioritize settings to repo", exc_info=True)

    # Create a new run row (your schema expects mode/config_hash/git_hash)
    from domain.models import Run
    from domain.enums import Mode

    run = Run(
        run_id=str(uuid.uuid4()),
        started_at=_now_utc(),
        mode=getattr(settings, "mode", Mode.PAPER),
        config_hash=_config_hash(),
        git_hash=_git_hash(),
    )
    repo.insert_run(run)

    # Bus + dispatcher
    from dispatcher.bus import EventBus

    bus = EventBus()
    loop_obj = None
    target = None
    try:
        from dispatcher.loop import build_dispatcher
        loop_obj = build_dispatcher(settings=settings, repo=repo, bus=bus, run_id=run.run_id)
        target = loop_obj.run_forever
    except Exception:
        logger.warning("Using legacy dispatcher discovery...", exc_info=True)
        import dispatcher.loop as loop_mod
        loop_obj, target = _pick_dispatcher_target(loop_mod, settings=settings, repo=repo, bus=bus, run_id=run.run_id)
    executor = build_executor(settings)
    if loop_obj is not None and executor is not None:
        try:
            setattr(loop_obj, "executor", executor)
        except Exception:
            logger.warning("failed to attach executor to dispatcher", exc_info=True)

    t = threading.Thread(target=target, name="dispatcher", daemon=False)
    t.start()
    dispatcher_handle = DispatcherHandle(loop_obj=loop_obj, thread=t)

    app = create_app(settings=settings, repo=repo, bus=bus)
    app.state.executor = executor
    @app.on_event("shutdown")
    def _stop_dispatcher() -> None:
        dispatcher_handle.stop()

    uvicorn.run(
        app,
        host=getattr(settings, "host", "127.0.0.1"),
        port=int(getattr(settings, "port", 8000)),
        log_level=getattr(settings, "log_level", "info"),
    )

if __name__ == "__main__":
    main()
