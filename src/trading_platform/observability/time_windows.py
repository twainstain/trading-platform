"""Time-windowed aggregation helpers.

Provides standard time windows (5m, 1h, 24h, etc.) and generic
query helpers for windowed stats. Products supply their own SQL
queries — this module provides the window definitions and helpers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

WINDOWS = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "8h": timedelta(hours=8),
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
    "1m": timedelta(days=30),
}


def since(window_key: str) -> str | None:
    """Return ISO timestamp for the start of the given window.

    Returns None if window_key is not recognized.
    """
    td = WINDOWS.get(window_key)
    if td is None:
        return None
    return (datetime.now(timezone.utc) - td).isoformat()


def since_delta(td: timedelta) -> str:
    """Return ISO timestamp for now minus the given timedelta."""
    return (datetime.now(timezone.utc) - td).isoformat()


def window_keys() -> list[str]:
    """Return all available window keys in order."""
    return list(WINDOWS.keys())
