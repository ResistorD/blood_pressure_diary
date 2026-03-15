from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from api.http import _apply_execution_mode_switch, _apply_live_limits, _runtime_executor_attached, create_app
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


def test_live_control_mutating_routes_are_admin_guarded(tmp_path: Path) -> None:
    db_path = tmp_path / "live_controls_guard.db"
    settings = AppSettings(mode=Mode.DRY_RUN, db_path=str(db_path))
    repo = Repo(str(db_path))
    repo.init_schema("db/schema.sql")
    bus = EventBus()
    app = create_app(settings=settings, repo=repo, bus=bus)

    target_paths = {"/control/live/save", "/control/live/mode"}
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = {m.upper() for m in (getattr(route, "methods", set()) or set())}
        if "POST" not in methods or path not in target_paths:
            continue
        deps = _route_dependency_names(route)
        assert "_require_admin_token" in deps, f"{path} is missing admin-token guard"


def test_apply_live_limits_updates_settings_and_repo_and_env() -> None:
    class _Repo:
        def __init__(self):
            self.saved = {}

        def set_setting(self, key: str, value: str):
            self.saved[key] = value

    settings = SimpleNamespace(
        live_max_notional=0.0,
        risk=SimpleNamespace(max_notional_total=500.0),
    )
    repo = _Repo()
    out = _apply_live_limits(
        settings=settings,
        repo=repo,
        live_max_notional=7.5,
        max_total_notional=320.0,
        paper_fixed_notional=12.0,
    )

    assert float(settings.live_max_notional) == 7.5
    assert float(settings.risk.max_notional_total) == 320.0
    assert repo.saved.get("live_max_notional") == "7.5"
    assert repo.saved.get("risk_max_notional_total") == "320.0"
    assert repo.saved.get("paper_fixed_notional") == "12.0"
    assert out["restart_required"] is False


def test_apply_execution_mode_switch_updates_state(monkeypatch) -> None:
    class _Repo:
        def __init__(self):
            self.saved = {}

        def set_setting(self, key: str, value: str):
            self.saved[key] = value

    loop = SimpleNamespace(executor=None)
    app = SimpleNamespace(
        state=SimpleNamespace(
            execution_mode="paper",
            settings=SimpleNamespace(execution_mode="paper"),
            executor=None,
            dispatcher_loop=loop,
        )
    )
    repo = _Repo()

    monkeypatch.setattr("app.main.build_executor", lambda _settings: object())

    out_live = _apply_execution_mode_switch(app=app, repo=repo, new_mode_raw="live_stage0")
    assert out_live["execution_mode"] == "LIVE_STAGE0"
    assert out_live["live_executor"] is True
    assert out_live["restart_required"] is False
    assert app.state.execution_mode == "live_stage0"
    assert app.state.settings.execution_mode == "live_stage0"
    assert app.state.executor is not None
    assert app.state.dispatcher_loop.executor is app.state.executor
    assert _runtime_executor_attached(app) is True
    assert repo.saved.get("execution_mode") == "live_stage0"

    out_paper = _apply_execution_mode_switch(app=app, repo=repo, new_mode_raw="paper")
    assert out_paper["execution_mode"] == "PAPER"
    assert out_paper["live_executor"] is False
    assert app.state.executor is None
    assert app.state.dispatcher_loop.executor is None
    assert _runtime_executor_attached(app) is False


def test_runtime_executor_attached_requires_both_app_and_loop_executor() -> None:
    loop = SimpleNamespace(executor=None)
    app = SimpleNamespace(state=SimpleNamespace(executor=object(), dispatcher_loop=loop))
    assert _runtime_executor_attached(app) is False
    loop.executor = object()
    assert _runtime_executor_attached(app) is True
