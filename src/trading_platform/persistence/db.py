"""Database connection management — SQLite and PostgreSQL.

Provides a unified DbConnection wrapper that normalizes SQL placeholders
(? vs %s) and dialect differences (AUTOINCREMENT vs SERIAL, INSERT OR IGNORE).

Products supply their own schema via init_db(schema=...). The platform
handles connection setup, WAL mode, batching, and backend detection.

The DATABASE_URL environment variable determines the backend:
  - Not set / empty  -> SQLite at the given path
  - "sqlite:///path"  -> SQLite at path
  - "postgres://..."   -> PostgreSQL
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_db: "DbConnection | None" = None


class DbConnection:
    """Unified database connection wrapper for SQLite and PostgreSQL.

    Normalizes:
      - Placeholders: ? (SQLite) vs %s (PostgreSQL)
      - INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING (PG)
      - Batch commit suppression via context manager
    """

    def __init__(self, conn: Any, backend: str) -> None:
        self._conn = conn
        self.backend = backend  # "sqlite" or "postgres"
        self._batch_depth = 0

    def _adapt_sql(self, sql: str) -> str:
        """Convert SQLite-style SQL to PostgreSQL equivalents."""
        if self.backend == "postgres":
            if "INSERT OR IGNORE" in sql:
                sql = sql.replace("INSERT OR IGNORE", "INSERT")
                if "ON CONFLICT" not in sql:
                    sql = sql.rstrip() + " ON CONFLICT DO NOTHING"
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql: str, params: tuple = ()) -> Any:
        if self.backend == "postgres":
            cur = self._conn.cursor()
            cur.execute(self._adapt_sql(sql), params)
            return cur
        return self._conn.execute(self._adapt_sql(sql), params)

    def executescript(self, sql: str) -> None:
        if self.backend == "sqlite":
            self._conn.executescript(sql)
        else:
            cur = self._conn.cursor()
            cur.execute(sql)
            cur.close()

    def commit(self) -> None:
        if self._batch_depth > 0:
            return
        self._conn.commit()

    @contextmanager
    def batch(self):
        """Suppress individual commit() calls; do one commit at the end."""
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @property
    def raw(self) -> Any:
        """Access the underlying connection (for advanced use)."""
        return self._conn


def _parse_database_url(default_path: str = "") -> tuple[str, str]:
    """Parse DATABASE_URL and return (backend, url/path)."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return "sqlite", default_path
    if url.startswith("sqlite:///"):
        return "sqlite", url[len("sqlite:///"):]
    if url.startswith(("postgres://", "postgresql://")):
        return "postgres", url
    return "sqlite", default_path


def _connect_sqlite(path: str) -> DbConnection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA cache_size=-8192")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    return DbConnection(conn, "sqlite")


def _connect_postgres(url: str) -> DbConnection:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        raise ImportError(
            "psycopg2 is required for PostgreSQL. Install with: "
            "pip install psycopg2-binary"
        )
    conn = psycopg2.connect(url)
    conn.autocommit = False
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return DbConnection(conn, "postgres")


def _sqlite_schema_to_postgres(schema: str) -> str:
    """Convert SQLite schema DDL to PostgreSQL equivalent."""
    return schema.replace(
        "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
    )


def init_db(
    db_path: str | Path | None = None,
    schema: str = "",
) -> DbConnection:
    """Initialize a database and return a DbConnection.

    Args:
        db_path: Override path/URL. If None, uses DATABASE_URL env var.
        schema: SQL DDL to execute (CREATE TABLE statements). Written in
                SQLite syntax — auto-converted for PostgreSQL.
    """
    global _db

    if db_path is not None:
        path_str = str(db_path)
        if path_str.startswith(("postgres://", "postgresql://")):
            db = _connect_postgres(path_str)
            if schema:
                db.executescript(_sqlite_schema_to_postgres(schema))
        else:
            db = _connect_sqlite(path_str)
            if schema:
                db.executescript(schema)
    else:
        backend, url = _parse_database_url()
        if backend == "postgres":
            db = _connect_postgres(url)
            if schema:
                db.executescript(_sqlite_schema_to_postgres(schema))
        else:
            if not url:
                raise ValueError(
                    "No database path provided. Pass db_path or set DATABASE_URL."
                )
            db = _connect_sqlite(url)
            if schema:
                db.executescript(schema)

    db.commit()
    _db = db
    return db


def get_db() -> DbConnection:
    """Return the current database connection. Raises if not initialized."""
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        _db.close()
        _db = None
