#!/usr/bin/env python
"""Performance benchmark for Sprint 2 optimizations.

Compares:
- Regular Repo vs OptimizedRepo
- Cache enabled vs disabled
- Single inserts vs batch inserts
"""
import sys
import tempfile
import os
from time import perf_counter
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.repo import Repo
from db.optimized_repo import OptimizedRepo
from db.cache import CacheConfig
from domain.models import Market, Snapshot
from utils.time import now_utc
from utils.logging import get_logger

logger = get_logger("benchmarks.performance")


class Benchmark:
    """Performance benchmark suite."""
    
    def __init__(self):
        self.results = {}
    
    def setup_db(self) -> str:
        """Create temporary database."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        return path
    
    def cleanup_db(self, path: str):
        """Remove temporary database."""
        try:
            os.unlink(path)
        except Exception:
            logger.warning("cleanup_db failed for %s", path, exc_info=True)
    
    def run_benchmark(self, name: str, func, iterations: int = 100):
        """Run a benchmark and record results."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Benchmark: {name}")
        logger.info(f"Iterations: {iterations}")
        logger.info(f"{'='*60}")
        
        start = perf_counter()
        result = func(iterations)
        elapsed = perf_counter() - start
        
        avg_ms = (elapsed / iterations) * 1000
        
        logger.info(f"Total time: {elapsed:.3f}s")
        logger.info(f"Average: {avg_ms:.2f}ms per iteration")
        
        self.results[name] = {
            "total_sec": elapsed,
            "avg_ms": avg_ms,
            "iterations": iterations,
            "result": result,
        }
        
        return elapsed, avg_ms
    
    def benchmark_market_lookups(self):
        """Benchmark: Market lookups with and without cache."""
        
        # Setup
        db_path = self.setup_db()
        
        # Insert test data
        repo = OptimizedRepo(db_path, enable_cache=False)
        schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
        if schema_path.exists():
            repo.init_schema(str(schema_path))
        
        markets = [
            Market(market_id=f"m{i}", slug=f"market-{i}", title=f"Market {i}")
            for i in range(100)
        ]
        for m in markets:
            repo.insert_market(m)
        
        # Test 1: Without cache
        repo_no_cache = OptimizedRepo(db_path, enable_cache=False)
        
        def lookup_no_cache(iterations):
            for _ in range(iterations):
                for i in range(100):
                    repo_no_cache.get_market(f"m{i}")
            return iterations * 100
        
        t1, avg1 = self.run_benchmark("Market lookup (no cache)", lookup_no_cache, iterations=10)
        
        # Test 2: With cache
        repo_cache = OptimizedRepo(db_path, enable_cache=True)
        
        def lookup_with_cache(iterations):
            for _ in range(iterations):
                for i in range(100):
                    repo_cache.get_market(f"m{i}")
            return iterations * 100
        
        t2, avg2 = self.run_benchmark("Market lookup (with cache)", lookup_with_cache, iterations=10)
        
        # Calculate speedup
        speedup = avg1 / avg2 if avg2 > 0 else 0
        logger.info(f"\n🚀 Speedup with cache: {speedup:.1f}x")
        
        # Cleanup
        self.cleanup_db(db_path)
    
    def benchmark_snapshot_lookups(self):
        """Benchmark: Snapshot lookups with and without cache."""
        
        db_path = self.setup_db()
        
        # Setup
        repo = OptimizedRepo(db_path, enable_cache=False)
        schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
        if schema_path.exists():
            repo.init_schema(str(schema_path))
        
        # Insert test data
        for i in range(50):
            market = Market(market_id=f"m{i}", slug=f"m{i}", title=f"M{i}")
            repo.insert_market(market)
            
            for outcome in ["YES", "NO"]:
                snapshot = Snapshot(
                    ts=now_utc(),
                    market_id=f"m{i}",
                    outcome=outcome,
                    mid=0.5,
                    bid=0.48,
                    ask=0.52,
                    spread=0.04,
                    liquidity=100.0,
                )
                repo.insert_snapshot(snapshot)
        
        # Test 1: Without cache
        repo_no_cache = OptimizedRepo(db_path, enable_cache=False)
        
        def lookup_no_cache(iterations):
            for _ in range(iterations):
                for i in range(50):
                    repo_no_cache.get_latest_snapshots(f"m{i}")
            return iterations * 50
        
        t1, avg1 = self.run_benchmark("Snapshot lookup (no cache)", lookup_no_cache, iterations=10)
        
        # Test 2: With cache
        repo_cache = OptimizedRepo(db_path, enable_cache=True)
        
        def lookup_with_cache(iterations):
            for _ in range(iterations):
                for i in range(50):
                    repo_cache.get_latest_snapshots(f"m{i}")
            return iterations * 50
        
        t2, avg2 = self.run_benchmark("Snapshot lookup (with cache)", lookup_with_cache, iterations=10)
        
        speedup = avg1 / avg2 if avg2 > 0 else 0
        logger.info(f"\n🚀 Speedup with cache: {speedup:.1f}x")
        
        self.cleanup_db(db_path)
    
    def benchmark_batch_inserts(self):
        """Benchmark: Single inserts vs batch inserts."""
        
        # Test 1: Single inserts
        db_path1 = self.setup_db()
        repo1 = OptimizedRepo(db_path1, enable_cache=False)
        schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
        if schema_path.exists():
            repo1.init_schema(str(schema_path))
        
        market = Market(market_id="m1", slug="m1", title="M1")
        repo1.insert_market(market)
        
        def single_inserts(iterations):
            for i in range(iterations):
                snapshot = Snapshot(
                    ts=now_utc(),
                    market_id="m1",
                    outcome="YES" if i % 2 == 0 else "NO",
                    mid=0.5,
                )
                repo1.insert_snapshot(snapshot)
            return iterations
        
        t1, avg1 = self.run_benchmark("Snapshot insert (single)", single_inserts, iterations=100)
        
        # Test 2: Batch inserts
        db_path2 = self.setup_db()
        repo2 = OptimizedRepo(db_path2, enable_cache=False)
        if schema_path.exists():
            repo2.init_schema(str(schema_path))
        
        repo2.insert_market(market)
        
        def batch_inserts(iterations):
            batch_size = 10
            for _ in range(iterations // batch_size):
                snapshots = [
                    Snapshot(
                        ts=now_utc(),
                        market_id="m1",
                        outcome="YES" if i % 2 == 0 else "NO",
                        mid=0.5,
                    )
                    for i in range(batch_size)
                ]
                repo2.insert_snapshots_batch(snapshots)
            return iterations
        
        t2, avg2 = self.run_benchmark("Snapshot insert (batch)", batch_inserts, iterations=100)
        
        speedup = avg1 / avg2 if avg2 > 0 else 0
        logger.info(f"\n🚀 Speedup with batch: {speedup:.1f}x")
        
        self.cleanup_db(db_path1)
        self.cleanup_db(db_path2)
    
    def print_summary(self):
        """Print benchmark summary."""
        logger.info("\n" + "="*60)
        logger.info("BENCHMARK SUMMARY")
        logger.info("="*60)
        
        for name, result in self.results.items():
            logger.info(f"\n{name}:")
            logger.info(f"  Average: {result['avg_ms']:.2f}ms")
            logger.info(f"  Total: {result['total_sec']:.3f}s")
        
        logger.info("\n" + "="*60)


def main():
    """Run all benchmarks."""
    logger.info("PolySyndicate Performance Benchmarks (Sprint 2)")
    logger.info("="*60)
    
    bench = Benchmark()
    
    # Run benchmarks
    bench.benchmark_market_lookups()
    bench.benchmark_snapshot_lookups()
    bench.benchmark_batch_inserts()
    
    # Summary
    bench.print_summary()
    
    logger.info("\n✅ Benchmarks complete!")


if __name__ == "__main__":
    main()

