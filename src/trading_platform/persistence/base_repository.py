"""Base repository — generic CRUD patterns for trading systems.

Products subclass and add domain-specific queries. The base provides:
  - Timestamp helpers
  - Row-to-dict conversion
  - Cached count queries with TTL
  - Status update pattern
  - Checkpoint (key-value) storage
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from trading_platform.persistence.db import DbConnection

logger = logging.getLogger(__name__)


class BaseRepository:
    """Generic repository with shared CRUD patterns.

    Subclass and add domain-specific methods. The base provides
    utility methods that all trading products need.
    """

    def __init__(self, conn: DbConnection) -> None:
        self.conn = conn
        self._count_cache: dict[str, tuple[float, int]] = {}
        self._count_cache_ttl: float = 30.0

    @staticmethod
    def _now() -> str:
        """Current UTC timestamp as ISO string."""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_dict(row: Any) -> dict | None:
        """Convert a DB row to a dict. Works for both SQLite Row and PG dict."""
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        return dict(row)

    def _rows_to_dicts(self, rows: list) -> list[dict]:
        """Convert a list of DB rows to dicts."""
        return [self._row_to_dict(r) for r in rows if r is not None]

    def _cached_count(self, cache_key: str, sql: str, params: tuple = ()) -> int:
        """Execute a COUNT query with TTL caching.

        Truncates time-based cache keys to minute precision to avoid
        cache misses from microsecond drift.
        """
        now = time.time()
        # Truncate cache key to minute precision for time-based keys.
        truncated_key = cache_key[:16] if len(cache_key) > 16 else cache_key
        cached = self._count_cache.get(truncated_key)
        if cached is not None:
            cached_at, count = cached
            if now - cached_at < self._count_cache_ttl:
                return count

        row = self.conn.execute(sql, params).fetchone()
        count = (row["cnt"] if row else 0) if isinstance(row, dict) else (row[0] if row else 0)
        self._count_cache[truncated_key] = (now, count)
        return count

    def update_status(self, table: str, id_column: str, record_id: str,
                      new_status: str) -> None:
        """Update the status of a record."""
        self.conn.execute(
            f"UPDATE {table} SET status = ?, updated_at = ? WHERE {id_column} = ?",
            (new_status, self._now(), record_id),
        )
        self.conn.commit()

    def save_checkpoint(self, checkpoint_type: str, value: str) -> None:
        """Upsert a system checkpoint (key-value pair)."""
        existing = self.conn.execute(
            "SELECT checkpoint_id FROM system_checkpoints WHERE checkpoint_type = ?",
            (checkpoint_type,),
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE system_checkpoints SET value = ?, updated_at = ? "
                "WHERE checkpoint_type = ?",
                (value, self._now(), checkpoint_type),
            )
        else:
            self.conn.execute(
                "INSERT INTO system_checkpoints (checkpoint_type, value, updated_at) "
                "VALUES (?, ?, ?)",
                (checkpoint_type, value, self._now()),
            )
        self.conn.commit()

    def get_checkpoint(self, checkpoint_type: str) -> str | None:
        """Get a checkpoint value by type."""
        row = self.conn.execute(
            "SELECT value FROM system_checkpoints WHERE checkpoint_type = ?",
            (checkpoint_type,),
        ).fetchone()
        if row is None:
            return None
        return row["value"] if isinstance(row, dict) else row[0]
