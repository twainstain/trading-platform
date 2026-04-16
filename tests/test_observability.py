"""Tests for observability — MetricsCollector."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_platform.observability import MetricsCollector


class MetricsTests(unittest.TestCase):
    def test_increment_counter(self):
        m = MetricsCollector()
        m.increment("detected")
        m.increment("detected")
        snap = m.snapshot()
        self.assertEqual(snap["counters"]["detected"], 2)

    def test_tagged_counter(self):
        m = MetricsCollector()
        m.increment("rejected", tag="low_profit")
        m.increment("rejected", tag="low_profit")
        m.increment("rejected", tag="high_gas")
        snap = m.snapshot()
        self.assertEqual(snap["counters"]["rejected"], 3)
        self.assertEqual(snap["tagged_counters"]["rejected"]["low_profit"], 2)
        self.assertEqual(snap["tagged_counters"]["rejected"]["high_gas"], 1)

    def test_gauge(self):
        m = MetricsCollector()
        m.set_gauge("queue_size", 42)
        snap = m.snapshot()
        self.assertEqual(snap["gauges"]["queue_size"], 42)

    def test_gauge_overwrite(self):
        m = MetricsCollector()
        m.set_gauge("price", 100)
        m.set_gauge("price", 200)
        self.assertEqual(m.snapshot()["gauges"]["price"], 200)

    def test_latency(self):
        m = MetricsCollector()
        m.record_latency(10.0)
        m.record_latency(20.0)
        m.record_latency(30.0)
        snap = m.snapshot()
        self.assertAlmostEqual(snap["avg_latency_ms"], 20.0, places=1)
        self.assertEqual(snap["latency_samples"], 3)

    def test_latency_capped_at_1000(self):
        m = MetricsCollector()
        for i in range(1500):
            m.record_latency(float(i))
        snap = m.snapshot()
        self.assertEqual(snap["latency_samples"], 1000)

    def test_p95_latency(self):
        m = MetricsCollector()
        for i in range(100):
            m.record_latency(float(i))
        snap = m.snapshot()
        self.assertGreaterEqual(snap["p95_latency_ms"], 90)

    def test_uptime(self):
        m = MetricsCollector()
        snap = m.snapshot()
        self.assertGreaterEqual(snap["uptime_seconds"], 0)

    def test_empty_snapshot(self):
        m = MetricsCollector()
        snap = m.snapshot()
        self.assertEqual(snap["counters"], {})
        self.assertEqual(snap["gauges"], {})
        self.assertEqual(snap["avg_latency_ms"], 0)


if __name__ == "__main__":
    unittest.main()
