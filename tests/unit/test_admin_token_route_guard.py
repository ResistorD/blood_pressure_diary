from __future__ import annotations

from pathlib import Path

from api.http import create_app
from app.config import AppSettings
from db.repo import Repo
from dispatcher.bus import EventBus
from domain.enums import Mode


def _route_dependency_names(route) -> set[str]:
    names: set[str] = set()
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return names
    for dep in getattr(dependant, "dependencies", []) or []:
        call = getattr(dep, "call", None)
        if callable(call):
            names.add(getattr(call, "__name__", ""))
    return names


def test_all_mutating_operator_routes_are_admin_guarded(tmp_path: Path) -> None:
    db_path = tmp_path / "guard.db"
    settings = AppSettings(mode=Mode.DRY_RUN, db_path=str(db_path))
    repo = Repo(str(db_path))
    repo.init_schema("db/schema.sql")
    bus = EventBus()
    app = create_app(settings=settings, repo=repo, bus=bus)

    guarded_paths = {
        "/cases/{market_id}/paper/buy",
        "/cases/{market_id}/paper/close",
        "/paper/action",
        "/paper/batch",
        "/paper/close_all",
        "/paper/unwind",
        "/agent/start",
        "/agent/stop",
        "/agent/config",
        "/control/toggle_paused",
        "/control/pause",
        "/control/resume",
        "/control/mode",
    }

    for route in app.routes:
        path = getattr(route, "path", "")
        methods = {m.upper() for m in (getattr(route, "methods", set()) or set())}
        if "POST" not in methods:
            continue
        if path not in guarded_paths:
            continue
        deps = _route_dependency_names(route)
        assert "_require_admin_token" in deps, f"{path} is missing admin-token guard"


def test_read_only_health_ping_not_guarded(tmp_path: Path) -> None:
    db_path = tmp_path / "guard_ro.db"
    settings = AppSettings(mode=Mode.DRY_RUN, db_path=str(db_path))
    repo = Repo(str(db_path))
    repo.init_schema("db/schema.sql")
    bus = EventBus()
    app = create_app(settings=settings, repo=repo, bus=bus)

    target = None
    for route in app.routes:
        if getattr(route, "path", "") == "/health/ping":
            target = route
            break
    assert target is not None
    deps = _route_dependency_names(target)
    assert "_require_admin_token" not in deps
