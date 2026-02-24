from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5002").rstrip("/")
DB_PATH = os.getenv("PS_DB_PATH", "")


def _http_json(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = None
    headers = {"accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["content-type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return {"_error": f"HTTP {e.code}", "body": json.loads(raw)}
        except Exception:
            return {"_error": f"HTTP {e.code}", "body": raw}
    except URLError as e:
        return {"_error": f"URL {e}"}


def _resolve_db_path() -> str:
    if DB_PATH:
        return DB_PATH
    here = Path.cwd()
    candidates = [
        here / "polysyndicate.db",
        here.parent / "polysyndicate.db",
        here / "data" / "polysyndicate.db",
        here / "db" / "polysyndicate.db",
    ]
    for c in candidates:
        if c.exists():
            return str(c.resolve())
    return str((here / "polysyndicate.db").resolve())


def _execute_paper_queue(db_path: str) -> int:
    from db.repo import Repo
    from execution.paper_executor import execute_pending_paper

    repo = Repo(db_path)
    repo.init_schema("db/schema.sql")
    return execute_pending_paper(repo, run_id="smoke", limit=200)


def main() -> int:
    print(f"BASE_URL={BASE_URL}")
    # 1) pick case
    live = _http_json("GET", "/cases/live?limit=1")
    items = live.get("items") or []
    if not items:
        print("FAIL: no live cases available")
        return 1
    case_id = items[0].get("case_id")
    if not case_id:
        print("FAIL: live case has no case_id")
        return 1
    print(f"Case: {case_id}")

    # 2) open size=3 via 3 buys
    for i in range(3):
        res = _http_json(
            "POST",
            "/paper/action",
            {"case_id": case_id, "action": "buy", "mode": "paper"},
        )
        if not res or res.get("ok") is not True:
            print(f"FAIL: buy {i+1} -> {res}")
            return 1

    # 3) execute queued paper commands so position exists
    db_path = _resolve_db_path()
    executed = _execute_paper_queue(db_path)
    print(f"Paper queue executed: {executed}")

    # 4) start agent with fast cadence + chunked close
    start = _http_json(
        "POST",
        "/agent/start",
        {
            "cadence_sec": 1,
            "max_positions": 1,
            "size_preset": 1,
            "close_min_chunk": 1,
            "close_hold_minutes": 0,
            "emergency_hold_minutes": 0,
            "close_allow_guarded": True,
            "close_allow_when_stale": True,
        },
    )
    if not start or start.get("ok") is not True:
        print(f"FAIL: agent start -> {start}")
        return 1

    # 5) poll events for CLOSE_CHUNK x3 + CLOSE_DONE
    deadline = time.time() + 30
    close_chunks: list[dict] = []
    close_done = False
    while time.time() < deadline:
        ev = _http_json("GET", "/agent/events?limit=200")
        events = ev.get("events") or []
        close_chunks = [
            e for e in events
            if e.get("type") == "CLOSE_CHUNK" and (e.get("market_id") == case_id or e.get("case_id") == case_id)
        ]
        close_done = any(
            e.get("type") == "CLOSE_DONE" and (e.get("market_id") == case_id or e.get("case_id") == case_id)
            for e in events
        )
        if len(close_chunks) >= 3 and close_done:
            break
        time.sleep(1)

    if len(close_chunks) < 3:
        print(f"FAIL: expected 3 CLOSE_CHUNK, got {len(close_chunks)}")
        return 1
    if not close_done:
        print("FAIL: missing CLOSE_DONE")
        return 1

    # validate remaining sequence
    remains = [float(c.get("detail", {}).get("remaining", -1)) for c in close_chunks[:3]]
    if remains != [2.0, 1.0, 0.0]:
        print(f"FAIL: remaining sequence {remains} (expected [2,1,0])")
        return 1

    print("OK: partial close contract + agent events validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
