"""Discord alert backend.

Sends messages via Discord Webhook. Requires:
  - DISCORD_WEBHOOK_URL: Webhook URL from Discord channel settings
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

EVENT_COLORS = {
    "opportunity_found": 0x3498DB,
    "trade_executed": 0x2ECC71,
    "trade_reverted": 0xE74C3C,
    "trade_not_included": 0xF39C12,
    "simulation_failed": 0xE67E22,
    "system_error": 0xE74C3C,
    "daily_summary": 0x9B59B6,
    "hourly_summary": 0x3498DB,
}


class DiscordAlert:
    """Send alerts to a Discord channel via webhook."""

    def __init__(
        self,
        webhook_url: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "discord"

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url)

    def send(self, event_type: str, message: str, details: dict | None = None) -> bool:
        if not self.configured:
            logger.debug("Discord not configured — skipping alert")
            return False

        color = EVENT_COLORS.get(event_type, 0x95A5A6)
        title = event_type.replace("_", " ").title()

        fields = []
        if details:
            for key, val in details.items():
                fields.append({
                    "name": key.replace("_", " ").title(),
                    "value": str(val),
                    "inline": True,
                })

        payload = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,
                "fields": fields[:25],
            }],
        }

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code in (200, 204):
                return True
            logger.warning("Discord webhook returned %d: %s", resp.status_code, resp.text)
            return False
        except Exception as exc:
            logger.error("Discord send failed: %s", exc)
            return False
