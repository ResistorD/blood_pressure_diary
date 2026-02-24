"""Pytest configuration and fixtures."""
import pytest
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path

from db.repo import Repo
from domain.models import Run, Market
from domain.enums import Mode


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name
    
    yield db_path
    
    # Cleanup
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def repo(temp_db):
    """Create a test repository with schema initialized."""
    r = Repo(temp_db)
    
    # Initialize schema
    schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
    if schema_path.exists():
        r.init_schema(str(schema_path))
    
    return r


@pytest.fixture
def test_run(repo):
    """Create a test run."""
    run = Run(
        run_id="test-run-001",
        started_at=datetime.now(timezone.utc),
        mode=Mode.DRY_RUN,
        config_hash="test-hash",
        git_hash="test-git",
    )
    repo.insert_run(run)
    return run


@pytest.fixture
def test_market(repo):
    """Create a test market."""
    market = Market(
        market_id="test-market-001",
        slug="test-market",
        title="Test Market for Testing",
        group_key="test-group",
    )
    repo.insert_market(market)
    return market


@pytest.fixture
def sample_snapshots():
    """Sample snapshot data."""
    return {
        "YES": {
            "bid": 0.60,
            "ask": 0.65,
            "mid": 0.625,
            "spread": 0.05,
            "liquidity": 100.0,
        },
        "NO": {
            "bid": 0.35,
            "ask": 0.40,
            "mid": 0.375,
            "spread": 0.05,
            "liquidity": 100.0,
        },
    }
