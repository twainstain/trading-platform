"""Tests for data — TTLCache."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_platform.data import TTLCache


class CacheBasicTests(unittest.TestCase):
    def test_set_and_get(self):
        c = TTLCache(ttl_seconds=60)
        c.set("key1", "value1")
        self.assertEqual(c.get("key1"), "value1")

    def test_get_missing_returns_none(self):
        c = TTLCache()
        self.assertIsNone(c.get("nonexistent"))

    def test_has(self):
        c = TTLCache()
        c.set("k", "v")
        self.assertTrue(c.has("k"))
        self.assertFalse(c.has("missing"))

    def test_delete(self):
        c = TTLCache()
        c.set("k", "v")
        self.assertTrue(c.delete("k"))
        self.assertFalse(c.has("k"))
        self.assertFalse(c.delete("k"))

    def test_clear(self):
        c = TTLCache()
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        self.assertEqual(c.size, 0)

    def test_size(self):
        c = TTLCache()
        self.assertEqual(c.size, 0)
        c.set("a", 1)
        c.set("b", 2)
        self.assertEqual(c.size, 2)

    def test_overwrite(self):
        c = TTLCache()
        c.set("k", "old")
        c.set("k", "new")
        self.assertEqual(c.get("k"), "new")


class CacheTTLTests(unittest.TestCase):
    def test_expired_entry_returns_none(self):
        c = TTLCache(ttl_seconds=0.01)
        c.set("k", "v")
        time.sleep(0.02)
        self.assertIsNone(c.get("k"))

    def test_has_returns_false_for_expired(self):
        c = TTLCache(ttl_seconds=0.01)
        c.set("k", "v")
        time.sleep(0.02)
        self.assertFalse(c.has("k"))

    def test_ttl_override(self):
        c = TTLCache(ttl_seconds=60)
        c.set("short", "v", ttl_override=0.01)
        c.set("long", "v")
        time.sleep(0.02)
        self.assertIsNone(c.get("short"))
        self.assertEqual(c.get("long"), "v")

    def test_size_excludes_expired(self):
        c = TTLCache(ttl_seconds=0.01)
        c.set("a", 1)
        c.set("b", 2)
        time.sleep(0.02)
        self.assertEqual(c.size, 0)


class CacheStatsTests(unittest.TestCase):
    def test_hit_tracking(self):
        c = TTLCache()
        c.set("k", "v")
        c.get("k")
        c.get("k")
        c.get("missing")
        s = c.stats()
        self.assertEqual(s["total_hits"], 2)
        self.assertEqual(s["total_misses"], 1)
        self.assertAlmostEqual(s["hit_rate"], 0.667, places=2)

    def test_stats_fields(self):
        c = TTLCache(ttl_seconds=300)
        s = c.stats()
        self.assertIn("size", s)
        self.assertIn("total_hits", s)
        self.assertIn("total_misses", s)
        self.assertIn("hit_rate", s)
        self.assertIn("ttl_seconds", s)
        self.assertEqual(s["ttl_seconds"], 300)


if __name__ == "__main__":
    unittest.main()
