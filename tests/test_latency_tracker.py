"""Tests for observability/latency_tracker."""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_platform.observability.latency_tracker import LatencyTracker


class TestLatencyTracker(unittest.TestCase):
    def test_start_cycle_increments(self):
        tracker = LatencyTracker()
        tracker.start_cycle()
        tracker.start_cycle()
        self.assertEqual(tracker._cycle_count, 2)

    def test_mark_records_timing(self):
        tracker = LatencyTracker()
        tracker.start_cycle()
        time.sleep(0.001)
        tracker.mark("fetch")
        marks = tracker.get_marks()
        self.assertIn("fetch", marks)
        self.assertGreater(marks["fetch"], 0)

    def test_get_marks_returns_copy(self):
        tracker = LatencyTracker()
        tracker.start_cycle()
        tracker.mark("a")
        marks1 = tracker.get_marks()
        tracker.mark("b")
        marks2 = tracker.get_marks()
        self.assertNotIn("b", marks1)
        self.assertIn("b", marks2)

    def test_record_pipeline_writes_jsonl(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            tracker = LatencyTracker(output_path=path)
            tracker.start_cycle()
            tracker.mark("fetch")
            tracker.record_pipeline(
                "opp_001",
                {"detect_ms": 0.3, "total_ms": 0.8},
                status="approved",
                meta={"pair": "ETH/USDC"},
            )
            tracker.close()

            lines = Path(path).read_text().strip().splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(record["candidate_id"], "opp_001")
            self.assertEqual(record["status"], "approved")
            self.assertIn("pipeline_ms", record)
            self.assertEqual(record["meta"]["pair"], "ETH/USDC")
        finally:
            Path(path).unlink()

    def test_record_cycle_summary(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            tracker = LatencyTracker(output_path=path)
            tracker.start_cycle()
            tracker.record_cycle_summary(item_count=10, processed_count=3, status="ok")
            tracker.close()

            lines = Path(path).read_text().strip().splitlines()
            record = json.loads(lines[0])
            self.assertEqual(record["type"], "cycle_summary")
            self.assertEqual(record["item_count"], 10)
        finally:
            Path(path).unlink()

    def test_no_file_mode(self):
        tracker = LatencyTracker()
        tracker.start_cycle()
        tracker.mark("x")
        # Should not raise even without a file
        tracker.record_pipeline("id", {"total_ms": 1.0})
        tracker.record_cycle_summary()
        tracker.close()

    def test_custom_cycle_marks(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            tracker = LatencyTracker(output_path=path)
            tracker.start_cycle()
            saved_marks = {"rpc_fetch": 150.0}
            tracker.start_cycle()  # new cycle
            tracker.record_pipeline("id", {"total_ms": 0.5}, cycle_marks=saved_marks)
            tracker.close()

            record = json.loads(Path(path).read_text().strip())
            self.assertEqual(record["cycle_marks_ms"]["rpc_fetch"], 150.0)
        finally:
            Path(path).unlink()


class TestLatencyTrackerPerformance(unittest.TestCase):
    """Verify tracker overhead is minimal."""

    def test_mark_overhead_under_1ms(self):
        tracker = LatencyTracker()
        tracker.start_cycle()
        t0 = time.monotonic()
        for _ in range(1000):
            tracker.mark("stage")
        elapsed = (time.monotonic() - t0) * 1000
        per_mark = elapsed / 1000
        self.assertLess(per_mark, 1.0, f"mark() overhead {per_mark:.3f}ms > 1ms")


if __name__ == "__main__":
    unittest.main()
