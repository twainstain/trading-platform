"""Tests for data/endpoint_failover — multi-endpoint provider."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_platform.data.endpoint_failover import EndpointProvider


class TestEndpointProvider(unittest.TestCase):
    def test_single_endpoint(self):
        p = EndpointProvider("test", ["http://a.com"])
        self.assertEqual(p.get_endpoint(), "http://a.com")
        self.assertEqual(p.endpoint_count, 1)

    def test_empty_urls_raises(self):
        with self.assertRaises(ValueError):
            EndpointProvider("test", [])

    def test_success_resets_errors(self):
        p = EndpointProvider("test", ["http://a.com", "http://b.com"])
        p.record_error()
        p.record_error()
        self.assertEqual(p._endpoints[0].error_count, 2)
        p.record_success()
        self.assertEqual(p._endpoints[0].error_count, 0)

    def test_failover_after_max_errors(self):
        p = EndpointProvider("test", ["http://a.com", "http://b.com"],
                             max_errors_before_disable=2, backoff_seconds=60)
        self.assertEqual(p.get_endpoint(), "http://a.com")
        p.record_error()
        p.record_error()  # triggers disable + rotate
        self.assertEqual(p.get_endpoint(), "http://b.com")

    def test_all_disabled_reenables_least_recent(self):
        p = EndpointProvider("test", ["http://a.com", "http://b.com"],
                             max_errors_before_disable=1, backoff_seconds=60)
        p.record_error()  # disables a, rotates to b
        p.record_error()  # disables b
        # Both disabled — should re-enable one
        url = p.get_endpoint()
        self.assertIn(url, ["http://a.com", "http://b.com"])

    def test_disabled_endpoint_recovers_after_backoff(self):
        p = EndpointProvider("test", ["http://a.com", "http://b.com"],
                             max_errors_before_disable=1, backoff_seconds=0.01)
        p.record_error()  # disables a
        time.sleep(0.02)
        # After backoff, a should be available again
        url = p.get_endpoint()
        # It should rotate back to a since backoff expired
        self.assertIn(url, ["http://a.com", "http://b.com"])

    def test_status_dict(self):
        p = EndpointProvider("mychain", ["http://a.com"])
        s = p.status()
        self.assertEqual(s["name"], "mychain")
        self.assertEqual(len(s["endpoints"]), 1)
        self.assertFalse(s["endpoints"][0]["disabled"])

    def test_current_url(self):
        p = EndpointProvider("test", ["http://a.com", "http://b.com"])
        self.assertEqual(p.current_url, "http://a.com")

    def test_three_endpoints_rotation(self):
        p = EndpointProvider("test", ["http://a.com", "http://b.com", "http://c.com"],
                             max_errors_before_disable=1, backoff_seconds=60)
        self.assertEqual(p.get_endpoint(), "http://a.com")
        p.record_error()
        self.assertEqual(p.get_endpoint(), "http://b.com")
        p.record_error()
        self.assertEqual(p.get_endpoint(), "http://c.com")


if __name__ == "__main__":
    unittest.main()
