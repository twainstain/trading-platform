"""Tests for risk/retry — bounded retry with re-evaluation."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_platform.risk.retry import RetryPolicy, RetryResult, config_hash, execute_with_retry


class TestConfigHash(unittest.TestCase):
    def test_deterministic(self):
        d = {"a": 1, "b": "two"}
        self.assertEqual(config_hash(d), config_hash(d))

    def test_different_dicts_different_hash(self):
        self.assertNotEqual(config_hash({"a": 1}), config_hash({"a": 2}))

    def test_order_independent(self):
        self.assertEqual(
            config_hash({"a": 1, "b": 2}),
            config_hash({"b": 2, "a": 1}),
        )

    def test_returns_16_chars(self):
        self.assertEqual(len(config_hash({"x": 42})), 16)


class TestExecuteWithRetry(unittest.TestCase):
    def test_success_first_attempt(self):
        fn = MagicMock(return_value=(True, "ok"))
        result = execute_with_retry(fn)
        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.last_reason, "ok")
        fn.assert_called_once()

    def test_fails_then_succeeds(self):
        fn = MagicMock(side_effect=[
            (False, "timeout"),
            (True, "ok"),
        ])
        policy = RetryPolicy(max_retries=2, delay_seconds=0)
        result = execute_with_retry(fn, policy=policy)
        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)

    def test_exhausts_retries(self):
        fn = MagicMock(return_value=(False, "always_fails"))
        policy = RetryPolicy(max_retries=2, delay_seconds=0)
        result = execute_with_retry(fn, policy=policy)
        self.assertFalse(result.success)
        self.assertEqual(result.attempts, 3)  # 1 initial + 2 retries
        self.assertEqual(result.last_reason, "always_fails")

    def test_aborts_when_no_longer_valid(self):
        fn = MagicMock(return_value=(False, "fail"))
        check = MagicMock(return_value=False)
        policy = RetryPolicy(max_retries=2, delay_seconds=0, require_re_evaluation=True)
        result = execute_with_retry(fn, is_still_valid=check, policy=policy)
        self.assertFalse(result.success)
        self.assertEqual(result.last_reason, "retry_aborted:not_valid")
        self.assertEqual(result.attempts, 1)  # only the first attempt

    def test_skips_re_evaluation_when_disabled(self):
        call_count = 0
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return (False, "fail")
            return (True, "ok")

        check = MagicMock(return_value=False)
        policy = RetryPolicy(max_retries=2, delay_seconds=0, require_re_evaluation=False)
        result = execute_with_retry(fn, is_still_valid=check, policy=policy)
        self.assertTrue(result.success)
        check.assert_not_called()

    def test_config_hash_passed_through(self):
        fn = MagicMock(return_value=(True, "ok"))
        result = execute_with_retry(fn, current_config_hash="abc123")
        self.assertEqual(result.config_hash, "abc123")

    def test_no_re_eval_check_when_none(self):
        fn = MagicMock(side_effect=[(False, "fail"), (True, "ok")])
        policy = RetryPolicy(max_retries=1, delay_seconds=0)
        result = execute_with_retry(fn, is_still_valid=None, policy=policy)
        self.assertTrue(result.success)


class TestRetryPolicy(unittest.TestCase):
    def test_defaults(self):
        p = RetryPolicy()
        self.assertEqual(p.max_retries, 2)
        self.assertEqual(p.delay_seconds, 1.0)
        self.assertTrue(p.require_re_evaluation)


if __name__ == "__main__":
    unittest.main()
