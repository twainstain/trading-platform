"""Multi-endpoint provider with automatic failover.

Generic version of ArbitrageTrader's RpcProvider — works for any
service with multiple endpoints (RPC, REST APIs, etc.). No web3
dependency; products wrap this to create their own typed providers.

Usage:
    provider = EndpointProvider("ethereum", [
        "https://eth-mainnet.alchemy.com/v2/KEY",
        "https://eth.llamarpc.com",
    ])
    url = provider.get_endpoint()
    try:
        response = requests.get(url + "/some-path")
        provider.record_success()
    except Exception:
        provider.record_error()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _EndpointState:
    url: str
    error_count: int = 0
    last_error_at: float = 0
    disabled_until: float = 0


class EndpointProvider:
    """Multi-endpoint provider with automatic failover.

    Rotates through endpoints on repeated failures. Disabled endpoints
    are re-enabled after a backoff period. If all endpoints are disabled,
    the least-recently-errored one is re-enabled.
    """

    def __init__(
        self,
        name: str,
        urls: list[str],
        backoff_seconds: float = 30.0,
        max_errors_before_disable: int = 3,
    ) -> None:
        if not urls:
            raise ValueError(f"At least one URL required for '{name}'")
        self.name = name
        self.backoff_seconds = backoff_seconds
        self.max_errors_before_disable = max_errors_before_disable
        self._endpoints = [_EndpointState(url=u) for u in urls]
        self._current_index = 0

    @property
    def endpoint_count(self) -> int:
        return len(self._endpoints)

    @property
    def current_url(self) -> str:
        return self._endpoints[self._current_index].url

    def get_endpoint(self) -> str:
        """Return the best available endpoint URL."""
        return self._select_endpoint()

    def record_success(self) -> None:
        """Record a successful call on the current endpoint."""
        ep = self._endpoints[self._current_index]
        ep.error_count = 0

    def record_error(self) -> None:
        """Record a failed call and potentially rotate."""
        now = time.time()
        ep = self._endpoints[self._current_index]
        ep.error_count += 1
        ep.last_error_at = now

        if ep.error_count >= self.max_errors_before_disable:
            ep.disabled_until = now + self.backoff_seconds
            logger.warning(
                "Endpoint disabled for %ds: %s (name=%s, errors=%d)",
                self.backoff_seconds, ep.url[:60], self.name, ep.error_count,
            )
            self._rotate()

    def _select_endpoint(self) -> str:
        """Select the best available endpoint."""
        now = time.time()
        tried = 0
        while tried < len(self._endpoints):
            ep = self._endpoints[self._current_index]
            if ep.disabled_until <= now:
                return ep.url
            self._rotate()
            tried += 1

        # All disabled — re-enable the least-recently-errored one.
        best = min(self._endpoints, key=lambda e: e.last_error_at)
        best.disabled_until = 0
        best.error_count = 0
        logger.warning("All endpoints disabled — re-enabling %s", best.url[:60])
        return best.url

    def _rotate(self) -> None:
        self._current_index = (self._current_index + 1) % len(self._endpoints)

    def status(self) -> dict:
        now = time.time()
        return {
            "name": self.name,
            "current_url": self.current_url[:60] + ("..." if len(self.current_url) > 60 else ""),
            "endpoints": [
                {
                    "url": ep.url[:60] + ("..." if len(ep.url) > 60 else ""),
                    "error_count": ep.error_count,
                    "disabled": ep.disabled_until > now,
                }
                for ep in self._endpoints
            ],
        }
