"""Tests for alerting backends — Telegram, Discord, Gmail (mocked)."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class TestTelegramAlert(unittest.TestCase):
    def _make(self, token="tok", chat_id="123"):
        from trading_platform.alerting.telegram import TelegramAlert
        return TelegramAlert(bot_token=token, chat_id=chat_id)

    def test_configured(self):
        t = self._make()
        self.assertTrue(t.configured)

    def test_not_configured(self):
        t = self._make(token="", chat_id="")
        self.assertFalse(t.configured)

    def test_name(self):
        self.assertEqual(self._make().name, "telegram")

    def test_send_not_configured_returns_false(self):
        t = self._make(token="", chat_id="")
        self.assertFalse(t.send("test", "msg"))

    @patch("alerting.telegram.requests.post")
    def test_send_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        t = self._make()
        self.assertTrue(t.send("trade_executed", "ETH profit"))
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        self.assertIn("sendMessage", call_kwargs[0][0])

    @patch("alerting.telegram.requests.post")
    def test_send_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400, text="bad request")
        t = self._make()
        self.assertFalse(t.send("test", "msg"))

    @patch("alerting.telegram.requests.post")
    def test_send_exception(self, mock_post):
        mock_post.side_effect = Exception("network error")
        t = self._make()
        self.assertFalse(t.send("test", "msg"))


class TestDiscordAlert(unittest.TestCase):
    def _make(self, url="https://discord.com/api/webhooks/test"):
        from trading_platform.alerting.discord import DiscordAlert
        return DiscordAlert(webhook_url=url)

    def test_configured(self):
        self.assertTrue(self._make().configured)

    def test_not_configured(self):
        from trading_platform.alerting.discord import DiscordAlert
        self.assertFalse(DiscordAlert(webhook_url="").configured)

    def test_name(self):
        self.assertEqual(self._make().name, "discord")

    @patch("alerting.discord.requests.post")
    def test_send_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        d = self._make()
        self.assertTrue(d.send("trade_executed", "profit!", {"amount": "0.01"}))
        payload = mock_post.call_args[1]["json"]
        self.assertIn("embeds", payload)
        self.assertEqual(len(payload["embeds"][0]["fields"]), 1)

    @patch("alerting.discord.requests.post")
    def test_send_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="error")
        self.assertFalse(self._make().send("test", "msg"))

    @patch("alerting.discord.requests.post")
    def test_send_limits_fields_to_25(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        details = {f"field_{i}": str(i) for i in range(30)}
        self._make().send("test", "msg", details)
        payload = mock_post.call_args[1]["json"]
        self.assertLessEqual(len(payload["embeds"][0]["fields"]), 25)


class TestGmailAlert(unittest.TestCase):
    def _make(self, addr="test@gmail.com", pw="pass", rcpt="rcpt@gmail.com"):
        from trading_platform.alerting.gmail import GmailAlert
        return GmailAlert(address=addr, app_password=pw, recipient=rcpt,
                          subject_prefix="[Test]")

    def test_configured(self):
        self.assertTrue(self._make().configured)

    def test_not_configured(self):
        from trading_platform.alerting.gmail import GmailAlert
        self.assertFalse(GmailAlert(address="", app_password="", recipient="").configured)

    def test_name(self):
        self.assertEqual(self._make().name, "gmail")

    def test_subject_prefix(self):
        g = self._make()
        self.assertEqual(g.subject_prefix, "[Test]")

    @patch("alerting.gmail.smtplib.SMTP")
    def test_send_success(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
        g = self._make()
        self.assertTrue(g.send("trade_executed", "profit!"))
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()

    @patch("alerting.gmail.smtplib.SMTP")
    def test_send_with_html_body(self, mock_smtp_class):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
        g = self._make()
        self.assertTrue(g.send("test", "plain", html_body="<b>html</b>"))

    @patch("alerting.gmail.smtplib.SMTP")
    def test_send_exception(self, mock_smtp_class):
        mock_smtp_class.side_effect = Exception("connection failed")
        g = self._make()
        self.assertFalse(g.send("test", "msg"))

    def test_send_not_configured(self):
        from trading_platform.alerting.gmail import GmailAlert
        g = GmailAlert(address="", app_password="", recipient="")
        self.assertFalse(g.send("test", "msg"))


if __name__ == "__main__":
    unittest.main()
