"""Tests for trading_platform.risk — RuleBasedPolicy and CircuitBreaker."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risk.base_policy import RiskRule, RiskVerdict, RuleBasedPolicy
from risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, BreakerState


# ── Rule helpers ─────────────────────────────────────────────────────

class ApproveRule:
    name = "approve"
    def evaluate(self, candidate, context):
        return RiskVerdict(True, "ok")

class RejectRule:
    name = "reject"
    def evaluate(self, candidate, context):
        return RiskVerdict(False, "rejected", {"rule": self.name})

class ThresholdRule:
    """Rejects if candidate['value'] < context['min_value']."""
    name = "threshold"
    def evaluate(self, candidate, context):
        if candidate.get("value", 0) < context.get("min_value", 0):
            return RiskVerdict(False, "below_threshold")
        return RiskVerdict(True, "ok")

class CrashingRule:
    name = "crasher"
    def evaluate(self, candidate, context):
        raise RuntimeError("rule crashed")


# ── Policy Tests ─────────────────────────────────────────────────────

class PolicyBasicTests(unittest.TestCase):
    def test_empty_policy_approves(self):
        policy = RuleBasedPolicy(rules=[])
        verdict = policy.evaluate({"id": 1})
        self.assertTrue(verdict.approved)
        self.assertEqual(verdict.reason, "all_rules_passed")

    def test_single_approve_rule(self):
        policy = RuleBasedPolicy(rules=[ApproveRule()])
        verdict = policy.evaluate({"id": 1})
        self.assertTrue(verdict.approved)

    def test_single_reject_rule(self):
        policy = RuleBasedPolicy(rules=[RejectRule()])
        verdict = policy.evaluate({"id": 1})
        self.assertFalse(verdict.approved)
        self.assertEqual(verdict.reason, "rejected")

    def test_first_failure_stops_evaluation(self):
        """Second rule should never run if first rejects."""
        policy = RuleBasedPolicy(rules=[RejectRule(), ApproveRule()])
        verdict = policy.evaluate({"id": 1})
        self.assertFalse(verdict.approved)

    def test_all_must_pass(self):
        policy = RuleBasedPolicy(rules=[ApproveRule(), ApproveRule(), ApproveRule()])
        verdict = policy.evaluate({"id": 1})
        self.assertTrue(verdict.approved)

    def test_context_passed_to_rules(self):
        policy = RuleBasedPolicy(rules=[ThresholdRule()])
        # Below threshold
        v1 = policy.evaluate({"value": 5}, min_value=10)
        self.assertFalse(v1.approved)
        # Above threshold
        v2 = policy.evaluate({"value": 15}, min_value=10)
        self.assertTrue(v2.approved)

    def test_simulation_mode(self):
        policy = RuleBasedPolicy(rules=[ApproveRule()], simulation_mode=True)
        verdict = policy.evaluate({"id": 1})
        self.assertTrue(verdict.approved)
        self.assertEqual(verdict.reason, "simulation_approved")
        self.assertTrue(verdict.details.get("simulation"))

    def test_simulation_mode_still_rejects(self):
        policy = RuleBasedPolicy(rules=[RejectRule()], simulation_mode=True)
        verdict = policy.evaluate({"id": 1})
        self.assertFalse(verdict.approved)

    def test_crashing_rule_returns_error_verdict(self):
        policy = RuleBasedPolicy(rules=[CrashingRule()])
        verdict = policy.evaluate({"id": 1})
        self.assertFalse(verdict.approved)
        self.assertIn("rule_error", verdict.reason)

    def test_add_rule(self):
        policy = RuleBasedPolicy()
        policy.add_rule(RejectRule())
        verdict = policy.evaluate({"id": 1})
        self.assertFalse(verdict.approved)


# ── Circuit Breaker Tests ────────────────────────────────────────────

class BreakerBasicTests(unittest.TestCase):
    def test_starts_closed(self):
        cb = CircuitBreaker()
        self.assertEqual(cb.state, BreakerState.CLOSED)
        self.assertFalse(cb.should_block())

    def test_trips_on_failures(self):
        config = CircuitBreakerConfig(max_failures=2, failure_window_seconds=60)
        cb = CircuitBreaker(config)
        cb.record_failure()
        self.assertFalse(cb.should_block())
        cb.record_failure()
        self.assertTrue(cb.should_block())
        self.assertEqual(cb.state, BreakerState.OPEN)

    def test_trips_on_errors(self):
        config = CircuitBreakerConfig(max_errors=2, error_window_seconds=60)
        cb = CircuitBreaker(config)
        cb.record_error()
        cb.record_error()
        self.assertTrue(cb.should_block())

    def test_trips_on_stale_data(self):
        config = CircuitBreakerConfig(max_stale_seconds=0.01)
        cb = CircuitBreaker(config)
        time.sleep(0.02)
        self.assertTrue(cb.should_block())

    def test_fresh_data_prevents_staleness_trip(self):
        config = CircuitBreakerConfig(max_stale_seconds=0.05)
        cb = CircuitBreaker(config)
        cb.record_fresh_data()
        self.assertFalse(cb.should_block())

    def test_recovery_after_cooldown(self):
        config = CircuitBreakerConfig(max_failures=1, cooldown_seconds=0.01)
        cb = CircuitBreaker(config)
        cb.record_failure()
        self.assertTrue(cb.should_block())
        time.sleep(0.02)
        # Should transition to HALF_OPEN
        self.assertEqual(cb.state, BreakerState.HALF_OPEN)
        self.assertFalse(cb.should_block())

    def test_probe_success_resets_to_closed(self):
        config = CircuitBreakerConfig(max_failures=1, cooldown_seconds=0.01)
        cb = CircuitBreaker(config)
        cb.record_failure()
        time.sleep(0.02)
        _ = cb.state  # trigger HALF_OPEN
        cb.record_success()
        self.assertEqual(cb.state, BreakerState.CLOSED)

    def test_probe_failure_returns_to_open(self):
        config = CircuitBreakerConfig(max_failures=1, cooldown_seconds=0.01)
        cb = CircuitBreaker(config)
        cb.record_failure()
        time.sleep(0.02)
        _ = cb.state  # trigger HALF_OPEN
        cb.record_failure()
        self.assertEqual(cb.state, BreakerState.OPEN)

    def test_trip_reason_tracked(self):
        config = CircuitBreakerConfig(max_failures=1)
        cb = CircuitBreaker(config)
        cb.record_failure()
        self.assertEqual(cb.trip_reason, "repeated_failures")

    def test_status_dict(self):
        cb = CircuitBreaker()
        s = cb.status()
        self.assertIn("state", s)
        self.assertIn("trip_reason", s)
        self.assertIn("recent_failures", s)
        self.assertIn("recent_errors", s)


if __name__ == "__main__":
    unittest.main()
