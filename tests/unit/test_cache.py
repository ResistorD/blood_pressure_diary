"""Tests for cache and optimized repository (Sprint 2)."""
import pytest
import time
from datetime import datetime, timezone

from db.cache import RepoCache, CacheConfig, CacheStats
from db.optimized_repo import OptimizedRepo
from domain.models import Market, Snapshot
from utils.time import now_utc


class TestCacheStats:
    """Tests for CacheStats."""
    
    def test_initial_stats(self):
        """Test initial statistics are zero."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.total_requests == 0
        assert stats.hit_rate == 0.0
    
    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats()
        stats.hits = 80
        stats.misses = 20
        
        assert stats.total_requests == 100
        assert stats.hit_rate == 0.8
        assert stats.miss_rate == 0.2
    
    def test_reset(self):
        """Test statistics reset."""
        stats = CacheStats()
        stats.hits = 10
        stats.misses = 5
        
        stats.reset()
        
        assert stats.hits == 0
        assert stats.misses == 0


class TestRepoCache:
    """Tests for RepoCache."""
    
    def test_cache_initialization(self):
        """Test cache initialization."""
        config = CacheConfig(enabled=True)
        cache = RepoCache(config)
        
        assert cache.config.enabled
        stats = cache.get_stats()
        assert stats["enabled"]
    
    def test_cache_disabled(self):
        """Test cache can be disabled."""
        config = CacheConfig(enabled=False)
        cache = RepoCache(config)
        
        # Should not cache when disabled
        market_id = "test-market"
        result = cache.get_market(market_id)
        assert result is None
        
        stats = cache.get_stats()
        assert not stats["enabled"]
    
    def test_market_cache_hit(self):
        """Test market cache hit."""
        cache = RepoCache()
        
        market_id = "test-market"
        market = Market(
            market_id=market_id,
            slug="test",
            title="Test Market"
        )
        
        # Set and get
        cache.set_market(market_id, market)
        result = cache.get_market(market_id)
        
        assert result == market
        
        stats = cache.get_stats()
        assert stats["markets"]["hits"] == 1
        assert stats["markets"]["hit_rate"] == 1.0
    
    def test_market_cache_miss(self):
        """Test market cache miss."""
        cache = RepoCache()
        
        result = cache.get_market("nonexistent")
        assert result is None
        
        stats = cache.get_stats()
        assert stats["markets"]["misses"] == 1
    
    def test_snapshot_cache(self):
        """Test snapshot caching."""
        cache = RepoCache()
        
        market_id = "test-market"
        outcome = "YES"
        data = {
            "bid": 0.60,
            "ask": 0.65,
            "mid": 0.625,
            "spread": 0.05,
            "liquidity": 100.0,
        }
        
        # Set and get
        cache.set_snapshot(market_id, outcome, data)
        result = cache.get_snapshot(market_id, outcome)
        
        assert result == data
        
        stats = cache.get_stats()
        assert stats["snapshots"]["hits"] == 1
    
    def test_snapshot_ttl(self):
        """Test snapshot TTL expiration."""
        config = CacheConfig(snapshot_ttl=1)  # 1 second TTL
        cache = RepoCache(config)
        
        market_id = "test-market"
        data = {"mid": 0.5}
        
        cache.set_snapshot(market_id, "YES", data)
        
        # Should hit immediately
        assert cache.get_snapshot(market_id, "YES") == data
        
        # Wait for TTL
        time.sleep(1.1)
        
        # Should miss after TTL
        assert cache.get_snapshot(market_id, "YES") is None
    
    def test_cache_invalidation(self):
        """Test cache invalidation."""
        cache = RepoCache()
        
        market_id = "test-market"
        market = Market(market_id=market_id, slug="test", title="Test")
        
        cache.set_market(market_id, market)
        assert cache.get_market(market_id) is not None
        
        # Invalidate
        cache.invalidate_market(market_id)
        assert cache.get_market(market_id) is None
    
    def test_clear_all(self):
        """Test clearing all caches."""
        cache = RepoCache()
        
        # Populate caches
        cache.set_market("m1", Market(market_id="m1", slug="m1", title="M1"))
        cache.set_snapshot("m1", "YES", {"mid": 0.5})
        
        # Clear all
        cache.clear_all()
        
        # Should be empty
        assert cache.get_market("m1") is None
        assert cache.get_snapshot("m1", "YES") is None
    
    def test_cache_summary(self):
        """Test cache summary statistics."""
        cache = RepoCache()
        
        # Generate some activity
        cache.set_market("m1", Market(market_id="m1", slug="m1", title="M1"))
        cache.get_market("m1")  # hit
        cache.get_market("m2")  # miss
        
        summary = cache.get_summary()
        
        assert summary["enabled"]
        assert summary["total_requests"] == 2
        assert summary["total_hits"] == 1
        assert summary["overall_hit_rate"] == 0.5


class TestOptimizedRepo:
    """Tests for OptimizedRepo."""
    
    def test_init_with_cache(self, temp_db):
        """Test repository initialization with cache."""
        repo = OptimizedRepo(temp_db, enable_cache=True)
        
        stats = repo.get_cache_stats()
        assert stats is not None
        assert stats["enabled"]
    
    def test_init_without_cache(self, temp_db):
        """Test repository initialization without cache."""
        repo = OptimizedRepo(temp_db, enable_cache=False)
        
        stats = repo.get_cache_stats()
        assert stats is None
    
    def test_market_caching(self, temp_db):
        """Test market operations with caching."""
        repo = OptimizedRepo(temp_db, enable_cache=True)
        
        # Initialize schema
        from pathlib import Path
        schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
        if schema_path.exists():
            repo.init_schema(str(schema_path))
        
        # Insert market
        market = Market(
            market_id="test-market-1",
            slug="test-1",
            title="Test Market 1"
        )
        repo.insert_market(market)
        
        # First get - cache miss
        result1 = repo.get_market("test-market-1")
        assert result1 is not None
        
        # Second get - cache hit
        result2 = repo.get_market("test-market-1")
        assert result2 is not None
        
        # Check cache stats
        stats = repo.get_cache_stats()
        assert stats["markets"]["hits"] >= 1
    
    def test_snapshot_caching(self, temp_db):
        """Test snapshot caching."""
        repo = OptimizedRepo(temp_db, enable_cache=True)
        
        from pathlib import Path
        schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
        if schema_path.exists():
            repo.init_schema(str(schema_path))
        
        # Insert market first
        market = Market(market_id="m1", slug="m1", title="M1")
        repo.insert_market(market)
        
        # Insert snapshot
        snapshot = Snapshot(
            ts=now_utc(),
            market_id="m1",
            outcome="YES",
            bid=0.60,
            ask=0.65,
            mid=0.625,
            spread=0.05,
            liquidity=100.0,
        )
        repo.insert_snapshot(snapshot)
        
        # First get - miss (just inserted, cache invalidated)
        result1 = repo.get_latest_snapshots("m1")
        assert "YES" in result1
        
        # Second get - should hit cache
        result2 = repo.get_latest_snapshots("m1")
        assert "YES" in result2
        
        # Check stats
        stats = repo.get_cache_stats()
        assert stats["snapshots"]["hits"] >= 1
    
    def test_batch_insert_snapshots(self, temp_db):
        """Test batch snapshot insertion."""
        repo = OptimizedRepo(temp_db, enable_cache=True)
        
        from pathlib import Path
        schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
        if schema_path.exists():
            repo.init_schema(str(schema_path))
        
        # Insert market
        market = Market(market_id="m1", slug="m1", title="M1")
        repo.insert_market(market)
        
        # Create batch of snapshots
        snapshots = [
            Snapshot(
                ts=now_utc(),
                market_id="m1",
                outcome="YES",
                mid=0.6,
            ),
            Snapshot(
                ts=now_utc(),
                market_id="m1",
                outcome="NO",
                mid=0.4,
            ),
        ]
        
        # Batch insert
        count = repo.insert_snapshots_batch(snapshots)
        assert count == 2
    
    def test_batch_insert_empty(self, temp_db):
        """Test batch insert with empty list."""
        repo = OptimizedRepo(temp_db)
        
        count = repo.insert_snapshots_batch([])
        assert count == 0
    
    def test_cache_clear(self, temp_db):
        """Test cache clearing."""
        repo = OptimizedRepo(temp_db, enable_cache=True)
        
        from pathlib import Path
        schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
        if schema_path.exists():
            repo.init_schema(str(schema_path))
        
        # Populate cache
        market = Market(market_id="m1", slug="m1", title="M1")
        repo.insert_market(market)
        repo.get_market("m1")
        
        # Clear cache
        repo.clear_cache()
        
        # Stats should reset
        summary = repo.get_cache_summary()
        if summary:
            assert summary["cache_sizes"]["markets"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
