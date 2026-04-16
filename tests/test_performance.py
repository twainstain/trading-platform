"""Performance tests — verify hot-path overhead is acceptable.

These tests set concrete time budgets based on the ArbitrageTrader
perf experiments (pipeline avg 0.52ms, p95 1.34ms). Platform
primitives must not be the bottleneck.
"""

import sys
import time
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_platform.contracts import RiskVerdict
from trading_platform.data.cache import TTLCache
from trading_platform.observability.metrics import MetricsCollector
from trading_platform.pipeline.queue import PriorityQueue
from trading_platform.risk.base_policy import RuleBasedPolicy
from trading_platform.risk.circuit_breaker import CircuitBreaker


class ApproveAll:
    name = "approve"
    def evaluate(self, candidate, context):
        return RiskVerdict(True, "ok")


class TestPipelinePerformance(unittest.TestCase):
    """Ensure pipeline primitives run under strict time budgets."""

    def test_priority_queue_throughput(self):
        """Push+pop 10k items should take < 100ms."""
        q = PriorityQueue(max_size=0)
        t0 = time.monotonic()
        for i in range(10_000):
            q.push({"id": i}, priority=float(i))
        for _ in range(10_000):
            q.pop()
        elapsed = (time.monotonic() - t0) * 1000
        self.assertLess(elapsed, 100, f"Queue 10k push+pop took {elapsed:.1f}ms")

    def test_risk_evaluation_throughput(self):
        """10k risk evaluations with 5 rules should take < 50ms."""
        policy = RuleBasedPolicy(rules=[ApproveAll() for _ in range(5)])
        candidate = {"value": 100}
        t0 = time.monotonic()
        for _ in range(10_000):
            policy.evaluate(candidate)
        elapsed = (time.monotonic() - t0) * 1000
        self.assertLess(elapsed, 50, f"10k risk evals took {elapsed:.1f}ms")

    def test_circuit_breaker_check_speed(self):
        """100k should_block() calls should take < 200ms."""
        breaker = CircuitBreaker()
        breaker.record_fresh_data()
        t0 = time.monotonic()
        for _ in range(100_000):
            breaker.should_block()
        elapsed = (time.monotonic() - t0) * 1000
        self.assertLess(elapsed, 200, f"100k breaker checks took {elapsed:.1f}ms")

    def test_metrics_increment_throughput(self):
        """100k increments should take < 100ms."""
        m = MetricsCollector()
        t0 = time.monotonic()
        for _ in range(100_000):
            m.increment("test_counter")
        elapsed = (time.monotonic() - t0) * 1000
        self.assertLess(elapsed, 100, f"100k increments took {elapsed:.1f}ms")

    def test_ttl_cache_throughput(self):
        """10k set+get cycles should take < 50ms."""
        cache = TTLCache(ttl_seconds=60)
        t0 = time.monotonic()
        for i in range(10_000):
            cache.set(f"key_{i}", i)
            cache.get(f"key_{i}")
        elapsed = (time.monotonic() - t0) * 1000
        self.assertLess(elapsed, 50, f"10k cache set+get took {elapsed:.1f}ms")

    def test_metrics_snapshot_speed(self):
        """Snapshot with 1000 latency samples should take < 5ms."""
        m = MetricsCollector()
        for i in range(1000):
            m.record_latency(float(i))
            m.increment("counter_a", tag=f"tag_{i % 10}")
        t0 = time.monotonic()
        for _ in range(100):
            m.snapshot()
        elapsed = (time.monotonic() - t0) * 1000
        per_snap = elapsed / 100
        self.assertLess(per_snap, 5, f"Snapshot took {per_snap:.2f}ms")

    def test_queue_eviction_performance(self):
        """Queue with bounded size should handle evictions efficiently."""
        q = PriorityQueue(max_size=100)
        t0 = time.monotonic()
        for i in range(10_000):
            q.push({"id": i}, priority=float(i % 200))
        elapsed = (time.monotonic() - t0) * 1000
        self.assertLess(elapsed, 100, f"10k push with eviction took {elapsed:.1f}ms")
        self.assertLessEqual(q.size, 100)


if __name__ == "__main__":
    unittest.main()
