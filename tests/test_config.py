"""Tests for config — BaseConfig and env helpers."""

import json
import os
import sys
import tempfile
import unittest
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_platform.config.base_config import BaseConfig
from trading_platform.config.env import find_env_file, get_env, load_env, require_env


# -- BaseConfig tests --

@dataclass(frozen=True)
class SampleConfig(BaseConfig):
    pair: str = ""
    trade_size: Decimal = Decimal("1")
    min_profit: Decimal = Decimal("0.001")
    enabled: bool = True

    def validate(self) -> None:
        if self.trade_size <= 0:
            raise ValueError("trade_size must be positive")


class TestBaseConfig(unittest.TestCase):
    def test_from_dict_basic(self):
        cfg = SampleConfig.from_dict({"pair": "ETH/USDC", "trade_size": 5})
        self.assertEqual(cfg.pair, "ETH/USDC")
        self.assertEqual(cfg.trade_size, Decimal("5"))

    def test_from_dict_ignores_unknown_keys(self):
        cfg = SampleConfig.from_dict({"pair": "X", "unknown_field": 42})
        self.assertEqual(cfg.pair, "X")

    def test_from_dict_decimal_conversion(self):
        cfg = SampleConfig.from_dict({"min_profit": 0.005})
        self.assertIsInstance(cfg.min_profit, Decimal)

    def test_from_dict_overrides(self):
        cfg = SampleConfig.from_dict({"pair": "A"}, pair="B")
        self.assertEqual(cfg.pair, "B")

    def test_validation_runs(self):
        with self.assertRaises(ValueError):
            SampleConfig.from_dict({"trade_size": -1})

    def test_from_file(self):
        data = {"pair": "BTC/USDC", "trade_size": "10", "min_profit": "0.01"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            cfg = SampleConfig.from_file(path)
            self.assertEqual(cfg.pair, "BTC/USDC")
            self.assertEqual(cfg.trade_size, Decimal("10"))
        finally:
            os.unlink(path)

    def test_to_dict(self):
        cfg = SampleConfig.from_dict({"pair": "X", "trade_size": 2})
        d = cfg.to_dict()
        self.assertEqual(d["pair"], "X")
        self.assertEqual(d["trade_size"], "2")  # Decimal serialized as string
        self.assertIsInstance(d, dict)

    def test_defaults_used(self):
        cfg = SampleConfig.from_dict({})
        self.assertEqual(cfg.pair, "")
        self.assertEqual(cfg.trade_size, Decimal("1"))
        self.assertTrue(cfg.enabled)

    def test_frozen(self):
        cfg = SampleConfig.from_dict({"pair": "X"})
        with self.assertRaises(AttributeError):
            cfg.pair = "Y"  # type: ignore


# -- Env helpers tests --

class TestEnvHelpers(unittest.TestCase):
    def test_get_env_with_default(self):
        val = get_env("DEFINITELY_NOT_SET_12345", "fallback")
        self.assertEqual(val, "fallback")

    def test_get_env_reads_existing(self):
        os.environ["_TEST_TRADING_ENV"] = "hello"
        try:
            self.assertEqual(get_env("_TEST_TRADING_ENV"), "hello")
        finally:
            del os.environ["_TEST_TRADING_ENV"]

    def test_require_env_raises(self):
        with self.assertRaises(EnvironmentError):
            require_env("DEFINITELY_NOT_SET_99999")

    def test_require_env_returns_value(self):
        os.environ["_TEST_REQ_ENV"] = "val"
        try:
            self.assertEqual(require_env("_TEST_REQ_ENV"), "val")
        finally:
            del os.environ["_TEST_REQ_ENV"]

    def test_find_env_file_explicit_path(self):
        with tempfile.NamedTemporaryFile(suffix=".env", delete=False) as f:
            f.write(b"FOO=bar\n")
            path = f.name
        try:
            result = find_env_file(env_path=path)
            self.assertIsNotNone(result)
            self.assertEqual(result, Path(path).resolve())
        finally:
            os.unlink(path)

    def test_find_env_file_missing_returns_none(self):
        result = find_env_file(env_path="/nonexistent/.env")
        self.assertIsNone(result)

    def test_load_env_with_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("_TEST_LOAD_ENV_VAR=loaded_value\n")
            path = f.name
        try:
            load_env(env_path=path)
            self.assertEqual(os.environ.get("_TEST_LOAD_ENV_VAR"), "loaded_value")
        finally:
            os.unlink(path)
            os.environ.pop("_TEST_LOAD_ENV_VAR", None)


if __name__ == "__main__":
    unittest.main()
