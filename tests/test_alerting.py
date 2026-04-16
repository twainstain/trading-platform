"""Tests for alerting — BaseAlerter and AlertDispatcher."""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_platform.alerting import AlertDispatcher, BaseAlerter


class FakeEmail:
    def __init__(self, configured=True):
        self.configured = configured
        self.sent = []

    def send(self, event_type, message, details=None, html_body=None):
        self.sent.append((event_type, message, details, html_body))
        return True


class FakeBackend:
    def __init__(self, name="test", configured=True):
        self._name = name
        self.configured = configured
        self.sent = []

    @property
    def name(self):
        return self._name

    def send(self, event_type, message, details=None):
        self.sent.append((event_type, message))
        return True


class ConcreteAlerter(BaseAlerter):
    def build_hourly_report(self):
        return ("hourly plain", "<h1>hourly</h1>", {"type": "hourly"})

    def build_daily_report(self):
        return ("daily plain", "<h1>daily</h1>", {"type": "daily"})


class AlerterTests(unittest.TestCase):
    def test_send_hourly_report(self):
        email = FakeEmail()
        alerter = ConcreteAlerter(email=email)
        alerter.send_hourly_report()
        self.assertEqual(len(email.sent), 1)
        self.assertEqual(email.sent[0][0], "hourly_summary")
        self.assertIn("hourly plain", email.sent[0][1])

    def test_send_daily_report(self):
        email = FakeEmail()
        alerter = ConcreteAlerter(email=email)
        alerter.send_daily_report()
        self.assertEqual(len(email.sent), 1)
        self.assertEqual(email.sent[0][0], "daily_summary")

    def test_no_crash_when_email_unconfigured(self):
        email = FakeEmail(configured=False)
        alerter = ConcreteAlerter(email=email)
        alerter.send_hourly_report()
        self.assertEqual(len(email.sent), 0)

    def test_no_crash_when_email_none(self):
        alerter = ConcreteAlerter(email=None)
        alerter.send_hourly_report()

    def test_maybe_send_hourly_respects_interval(self):
        email = FakeEmail()
        alerter = ConcreteAlerter(email=email, email_interval_seconds=9999, startup_delay_seconds=9999)
        alerter.maybe_send_hourly()
        self.assertEqual(len(email.sent), 0)

    def test_maybe_send_daily_skips_if_already_sent_today(self):
        email = FakeEmail()
        alerter = ConcreteAlerter(email=email, daily_timezone="America/New_York")
        today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        alerter._last_daily_date = today
        alerter.maybe_send_daily()
        self.assertEqual(len(email.sent), 0)

    def test_daily_hour_default(self):
        alerter = ConcreteAlerter()
        self.assertEqual(alerter._daily_hour, 9)

    def test_daily_timezone_default(self):
        alerter = ConcreteAlerter()
        self.assertEqual(alerter._daily_tz.key, "UTC")

    def test_maybe_send_daily_uses_named_timezone(self):
        email = FakeEmail()
        alerter = ConcreteAlerter(email=email, daily_hour=9, daily_timezone="America/New_York")
        fake_now = datetime(2026, 7, 1, 9, 15, tzinfo=ZoneInfo("America/New_York"))

        with patch("alerting.base_alerter.datetime") as mock_datetime:
            mock_datetime.now.return_value = fake_now
            alerter.maybe_send_daily()

        self.assertEqual(len(email.sent), 1)
        self.assertEqual(email.sent[0][0], "daily_summary")
        self.assertEqual(alerter._last_daily_date, "2026-07-01")

    def test_invalid_timezone_raises(self):
        with self.assertRaises(Exception):
            ConcreteAlerter(daily_timezone="Not/A_Real_Timezone")

    def test_build_not_implemented_logs_error(self):
        alerter = BaseAlerter(email=FakeEmail())
        alerter.send_hourly_report()
        self.assertEqual(len(alerter.email.sent), 0)


class DispatcherTests(unittest.TestCase):
    def test_add_configured_backend(self):
        d = AlertDispatcher()
        d.add_backend(FakeBackend(configured=True))
        self.assertEqual(d.backend_count, 1)

    def test_skip_unconfigured_backend(self):
        d = AlertDispatcher()
        d.add_backend(FakeBackend(configured=False))
        self.assertEqual(d.backend_count, 0)

    def test_alert_fans_out(self):
        b1 = FakeBackend("b1")
        b2 = FakeBackend("b2")
        d = AlertDispatcher()
        d.add_backend(b1)
        d.add_backend(b2)
        d.alert("test_event", "hello")
        self.assertEqual(len(b1.sent), 1)
        self.assertEqual(len(b2.sent), 1)

    def test_failing_backend_does_not_crash(self):
        class FailBackend:
            name = "fail"
            configured = True

            def send(self, *a, **kw):
                raise RuntimeError("boom")

        d = AlertDispatcher()
        d.add_backend(FailBackend())
        d.alert("test", "msg")


if __name__ == "__main__":
    unittest.main()
