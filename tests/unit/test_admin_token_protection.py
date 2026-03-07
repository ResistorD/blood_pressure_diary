from __future__ import annotations

from pathlib import Path

import pytest
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from api.http import create_app
from app.config import AppSettings
from db.repo import Repo
from dispatcher.bus import EventBus
from domain.enums import Mode


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    db_path = tmp_path / "test.db"
    settings = AppSettings(mode=Mode.DRY_RUN, db_path=str(db_path))
    repo = Repo(str(db_path))
    repo.init_schema("db/schema.sql")
    bus = EventBus()
    app = create_app(settings=settings, repo=repo, bus=bus)
    return TestClient(app)


def test_mutating_endpoints_require_admin_token(client: TestClient) -> None:
    resp1 = client.post("/agent/start", json={})
    resp2 = client.post("/paper/action", json={"case_id": "1001", "action": "buy", "mode": "paper"})
    assert resp1.status_code == 401
    assert resp2.status_code == 401


def test_mutating_endpoints_accept_valid_admin_token(client: TestClient) -> None:
    headers = {"x-admin-token": "test-admin-token"}
    resp = client.post("/agent/start", json={}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True


def test_read_only_endpoint_remains_open(client: TestClient) -> None:
    resp = client.get("/health/ping")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"
