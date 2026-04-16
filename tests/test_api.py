"""Tests for api/base_app — FastAPI base factory."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# FastAPI test client requires httpx
try:
    from fastapi.testclient import TestClient
    from api.base_app import create_base_app, is_paused
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


@unittest.skipUnless(HAS_FASTAPI, "fastapi/httpx not installed")
class TestBaseApp(unittest.TestCase):
    def setUp(self):
        self.metrics = MagicMock()
        self.metrics.snapshot.return_value = {
            "uptime_seconds": 100,
            "counters": {"scans": 5},
        }
        self.app = create_base_app(
            metrics=self.metrics,
            require_auth=False,
            title="Test App",
        )
        self.client = TestClient(self.app)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("uptime_seconds", data)

    def test_metrics(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("counters", data)

    def test_pause_status(self):
        resp = self.client.get("/pause")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["paused"])

    def test_pause_and_resume(self):
        resp = self.client.post("/pause")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["paused"])

        # Health should show paused
        resp = self.client.get("/health")
        self.assertEqual(resp.json()["status"], "paused")

        # Resume
        resp = self.client.post("/resume")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["paused"])

    def test_metrics_without_collector(self):
        app = create_base_app(metrics=None, require_auth=False)
        client = TestClient(app)
        resp = client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("error", resp.json())


@unittest.skipUnless(HAS_FASTAPI, "fastapi/httpx not installed")
class TestBaseAppAuth(unittest.TestCase):
    def test_auth_required(self):
        import os
        os.environ["DASHBOARD_USER"] = "testuser"
        os.environ["DASHBOARD_PASS"] = "testpass"
        try:
            app = create_base_app(require_auth=True)
            client = TestClient(app)

            # No auth → 401
            resp = client.get("/health")
            self.assertEqual(resp.status_code, 401)

            # Wrong creds → 401
            resp = client.get("/health", auth=("wrong", "wrong"))
            self.assertEqual(resp.status_code, 401)

            # Correct creds → 200
            resp = client.get("/health", auth=("testuser", "testpass"))
            self.assertEqual(resp.status_code, 200)
        finally:
            os.environ.pop("DASHBOARD_USER", None)
            os.environ.pop("DASHBOARD_PASS", None)


if __name__ == "__main__":
    unittest.main()
