from __future__ import annotations

import os
from pathlib import Path

import pytest
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from api.http import create_app
from app.config import AppSettings
from domain.enums import Mode
from db.repo import Repo
from dispatcher.bus import EventBus

@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test.db"
    settings = AppSettings(mode=Mode.DRY_RUN, db_path=str(db_path))
    repo = Repo(str(db_path))
    repo.init_schema("db/schema.sql")
    bus = EventBus()
    app = create_app(settings=settings, repo=repo, bus=bus)
    return TestClient(app)

def test_smoke_pages(client: TestClient):
    for url in ["/", "/markets", "/signals", "/decisions", "/positions", "/cases"]:
        r = client.get(url)
        assert r.status_code == 200, (url, r.status_code, r.text[:200])

def test_mode_switch(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    headers = {"x-admin-token": "test-admin-token"}
    for mode in ["DEMO", "DRY_RUN", "LIVE"]:
        r = client.post("/control/mode", data={"mode": mode}, headers=headers)
        assert r.status_code in (200, 302, 303), (mode, r.status_code, r.text[:200])
