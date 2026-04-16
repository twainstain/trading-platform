"""Tests for trading_platform.pipeline — BasePipeline and PriorityQueue."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeline.base_pipeline import BasePipeline, PipelineResult, ZERO
from risk.base_policy import RiskVerdict
from pipeline.queue import PriorityQueue, QueuedItem


# ── Helpers ──────────────────────────────────────────────────────────

class StubPipeline(BasePipeline):
    """Minimal pipeline for testing."""
    def __init__(self, verdict=None, **kwargs):
        super().__init__(**kwargs)
        self._verdict = verdict or RiskVerdict(True, "ok")
        self.detected = []
        self.priced = []
        self.approved_ids = []
        self.rejected_ids = []
        self.simulated = []
        self.submitted = []
        self.verified = []

    def detect(self, candidate):
        self.detected.append(candidate)
        return f"id-{len(self.detected)}"

    def price(self, candidate_id, candidate):
        self.priced.append((candidate_id, candidate))

    def evaluate_risk(self, candidate):
        return self._verdict

    def on_approved(self, candidate_id, candidate):
        self.approved_ids.append(candidate_id)

    def on_rejected(self, candidate_id, reason, candidate):
        self.rejected_ids.append((candidate_id, reason))

    def on_simulated(self, candidate_id, success, reason):
        self.simulated.append((candidate_id, success, reason))

    def on_submitted(self, candidate_id, submission):
        self.submitted.append((candidate_id, submission))

    def on_verified(self, candidate_id, result):
        self.verified.append((candidate_id, result))


class StubSimulator:
    def __init__(self, success=True, reason="ok"):
        self._success = success
        self._reason = reason
    def simulate(self, candidate):
        return (self._success, self._reason)


class StubSubmitter:
    def __init__(self, tx_hash="0xabc"):
        self._tx_hash = tx_hash
    def submit(self, candidate):
        return {"tx_hash": self._tx_hash, "submission_type": "test"}


class StubVerifier:
    def __init__(self, status="included", profit=0.005):
        self._status = status
        self._profit = profit
    def verify(self, ref):
        return {"status": self._status, "net_profit": self._profit, "ref": ref}


# ── Pipeline Tests ───────────────────────────────────────────────────

class PipelineBasicTests(unittest.TestCase):
    def test_approved_candidate_returns_dry_run_without_submitter(self):
        pipe = StubPipeline(verdict=RiskVerdict(True, "ok"))
        result = pipe.process("candidate-1")
        self.assertEqual(result.final_status, "dry_run")
        self.assertEqual(len(pipe.detected), 1)
        self.assertEqual(len(pipe.priced), 1)
        self.assertEqual(len(pipe.approved_ids), 1)

    def test_rejected_candidate_stops_pipeline(self):
        pipe = StubPipeline(verdict=RiskVerdict(False, "too_risky"))
        result = pipe.process("candidate-1")
        self.assertEqual(result.final_status, "too_risky")
        self.assertEqual(len(pipe.rejected_ids), 1)
        self.assertEqual(len(pipe.approved_ids), 0)

    def test_simulation_failure_stops_pipeline(self):
        pipe = StubPipeline(
            verdict=RiskVerdict(True, "ok"),
            simulator=StubSimulator(success=False, reason="would_revert"),
        )
        result = pipe.process("candidate-1")
        self.assertEqual(result.final_status, "simulation_failed")
        self.assertEqual(pipe.simulated[0][1], False)

    def test_simulation_success_proceeds_to_dry_run(self):
        pipe = StubPipeline(
            verdict=RiskVerdict(True, "ok"),
            simulator=StubSimulator(success=True),
        )
        result = pipe.process("candidate-1")
        self.assertEqual(result.final_status, "dry_run")
        self.assertEqual(pipe.simulated[0][1], True)

    def test_full_pipeline_with_submitter_and_verifier(self):
        pipe = StubPipeline(
            verdict=RiskVerdict(True, "ok"),
            simulator=StubSimulator(),
            submitter=StubSubmitter(tx_hash="0xfull"),
            verifier=StubVerifier(status="included", profit=0.01),
        )
        result = pipe.process("candidate-1")
        self.assertEqual(result.final_status, "included")
        self.assertAlmostEqual(float(result.net_profit), 0.01, places=4)
        self.assertEqual(len(pipe.submitted), 1)
        self.assertEqual(len(pipe.verified), 1)

    def test_submitted_without_verifier(self):
        pipe = StubPipeline(
            verdict=RiskVerdict(True, "ok"),
            submitter=StubSubmitter(),
        )
        result = pipe.process("candidate-1")
        self.assertEqual(result.final_status, "submitted")

    def test_timings_present_in_result(self):
        pipe = StubPipeline(verdict=RiskVerdict(True, "ok"))
        result = pipe.process("candidate-1")
        self.assertIn("detect_ms", result.timings)
        self.assertIn("price_ms", result.timings)
        self.assertIn("risk_ms", result.timings)
        self.assertIn("total_ms", result.timings)
        self.assertGreater(result.timings["total_ms"], 0)

    def test_candidate_id_in_result(self):
        pipe = StubPipeline(verdict=RiskVerdict(True, "ok"))
        result = pipe.process("test-candidate")
        self.assertEqual(result.candidate_id, "id-1")


# ── Queue Tests ──────────────────────────────────────────────────────

class QueueBasicTests(unittest.TestCase):
    def test_push_and_pop(self):
        q = PriorityQueue(max_size=10)
        q.push("item-A", priority=0.5)
        q.push("item-B", priority=0.9)
        # Highest priority popped first
        result = q.pop()
        self.assertEqual(result.item, "item-B")
        self.assertAlmostEqual(result.priority, 0.9)

    def test_pop_empty_returns_none(self):
        q = PriorityQueue()
        self.assertIsNone(q.pop())

    def test_size_tracking(self):
        q = PriorityQueue()
        self.assertEqual(q.size, 0)
        self.assertTrue(q.is_empty)
        q.push("a", 1.0)
        self.assertEqual(q.size, 1)
        self.assertFalse(q.is_empty)

    def test_eviction_when_full(self):
        q = PriorityQueue(max_size=3)
        q.push("low", priority=0.1)
        q.push("mid", priority=0.5)
        q.push("high", priority=0.9)
        # Queue is full. Push a higher priority item.
        accepted = q.push("higher", priority=0.95)
        self.assertTrue(accepted)
        self.assertEqual(q.size, 3)
        # The lowest (0.1) should have been evicted.
        items = []
        while not q.is_empty:
            items.append(q.pop().item)
        self.assertNotIn("low", items)
        self.assertIn("higher", items)

    def test_drop_when_lower_than_all(self):
        q = PriorityQueue(max_size=2)
        q.push("a", priority=0.8)
        q.push("b", priority=0.9)
        # Try to push something worse than both
        accepted = q.push("worse", priority=0.1)
        self.assertFalse(accepted)
        self.assertEqual(q.size, 2)

    def test_pop_batch(self):
        q = PriorityQueue(max_size=10)
        for i in range(5):
            q.push(f"item-{i}", priority=i * 0.1)
        batch = q.pop_batch(3)
        self.assertEqual(len(batch), 3)
        # Highest priority first
        priorities = [b.priority for b in batch]
        self.assertEqual(priorities, sorted(priorities, reverse=True))
        self.assertEqual(q.size, 2)

    def test_clear(self):
        q = PriorityQueue()
        q.push("a", 1.0)
        q.push("b", 2.0)
        removed = q.clear()
        self.assertEqual(removed, 2)
        self.assertTrue(q.is_empty)

    def test_stats(self):
        q = PriorityQueue(max_size=2)
        q.push("a", 1.0)
        q.push("b", 2.0)
        q.push("c", 3.0)  # evicts lowest
        s = q.stats()
        self.assertEqual(s["current_size"], 2)
        self.assertEqual(s["max_size"], 2)
        self.assertEqual(s["total_enqueued"], 3)
        self.assertEqual(s["total_dropped"], 1)

    def test_fifo_at_equal_priority(self):
        q = PriorityQueue(max_size=10)
        q.push("first", priority=1.0)
        q.push("second", priority=1.0)
        # FIFO: first pushed should be popped first at equal priority
        result = q.pop()
        self.assertEqual(result.item, "first")

    def test_metadata_preserved(self):
        q = PriorityQueue()
        q.push("item", priority=1.0, metadata={"chain": "arbitrum"})
        result = q.pop()
        self.assertEqual(result.metadata["chain"], "arbitrum")


if __name__ == "__main__":
    unittest.main()
