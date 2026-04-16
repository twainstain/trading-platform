"""Tests for observability/log — logging setup and helpers."""

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_platform.observability.log import DecimalEncoder, get_logger, log_json


class TestDecimalEncoder(unittest.TestCase):
    def test_encodes_decimal_as_string(self):
        data = {"price": Decimal("1234.5678")}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)
        self.assertEqual(parsed["price"], "1234.5678")

    def test_normal_types_pass_through(self):
        data = {"count": 42, "name": "test", "flag": True}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)
        self.assertEqual(parsed["count"], 42)

    def test_nested_decimals(self):
        data = {"outer": {"inner": Decimal("0.001")}}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)
        self.assertEqual(parsed["outer"]["inner"], "0.001")


class TestGetLogger(unittest.TestCase):
    def test_returns_logger(self):
        logger = get_logger("test_module")
        self.assertEqual(logger.name, "test_module")

    def test_different_names_different_loggers(self):
        a = get_logger("mod_a")
        b = get_logger("mod_b")
        self.assertNotEqual(a.name, b.name)


class TestTimeWindows(unittest.TestCase):
    """Test time_windows module."""

    def test_window_keys(self):
        from trading_platform.observability.time_windows import window_keys, WINDOWS
        keys = window_keys()
        self.assertIn("5m", keys)
        self.assertIn("24h", keys)
        self.assertIn("1w", keys)
        self.assertEqual(len(keys), len(WINDOWS))

    def test_since_returns_iso(self):
        from trading_platform.observability.time_windows import since
        result = since("1h")
        self.assertIsNotNone(result)
        self.assertIn("T", result)

    def test_since_unknown_returns_none(self):
        from trading_platform.observability.time_windows import since
        self.assertIsNone(since("999y"))

    def test_since_delta(self):
        from datetime import timedelta
        from trading_platform.observability.time_windows import since_delta
        result = since_delta(timedelta(hours=2))
        self.assertIn("T", result)


if __name__ == "__main__":
    unittest.main()
