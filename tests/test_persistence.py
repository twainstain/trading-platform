"""Tests for persistence — DbConnection, init_db, BaseRepository."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_platform.persistence.db import DbConnection, close_db, init_db
from trading_platform.persistence.base_repository import BaseRepository

_TEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS system_checkpoints (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_type TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class TestDbConnection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = init_db(db_path=self.tmp.name, schema=_TEST_SCHEMA)

    def tearDown(self):
        close_db()
        os.unlink(self.tmp.name)

    def test_execute_insert_and_select(self):
        self.db.execute(
            "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
            ("test", "active", "2026-01-01"),
        )
        self.db.commit()
        row = self.db.execute("SELECT * FROM items WHERE name = ?", ("test",)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "test")

    def test_batch_suppresses_commits(self):
        with self.db.batch():
            self.db.execute(
                "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
                ("batch1", "active", "2026-01-01"),
            )
            self.db.commit()  # Should be suppressed
            self.db.execute(
                "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
                ("batch2", "active", "2026-01-01"),
            )
        # After batch context, both should be committed
        rows = self.db.execute("SELECT * FROM items").fetchall()
        self.assertEqual(len(rows), 2)

    def test_nested_batch(self):
        with self.db.batch():
            with self.db.batch():
                self.db.execute(
                    "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
                    ("nested", "active", "2026-01-01"),
                )
            # Inner batch ends but outer is still open — no commit yet
        # Now both batches are closed — commit happens
        row = self.db.execute("SELECT * FROM items WHERE name = ?", ("nested",)).fetchone()
        self.assertIsNotNone(row)

    def test_adapt_sql_sqlite(self):
        # SQLite: ? stays as ?
        sql = self.db._adapt_sql("SELECT * FROM items WHERE name = ?")
        self.assertIn("?", sql)

    def test_raw_property(self):
        self.assertIsNotNone(self.db.raw)

    def test_backend_is_sqlite(self):
        self.assertEqual(self.db.backend, "sqlite")

    def test_wal_mode_enabled(self):
        row = self.db.execute("PRAGMA journal_mode").fetchone()
        self.assertEqual(row[0], "wal")


class TestDbConnectionPostgresAdapt(unittest.TestCase):
    """Test SQL adaptation for PostgreSQL without an actual PG connection."""

    def test_placeholder_conversion(self):
        db = DbConnection.__new__(DbConnection)
        db.backend = "postgres"
        sql = db._adapt_sql("SELECT * FROM items WHERE id = ? AND name = ?")
        self.assertNotIn("?", sql)
        self.assertEqual(sql.count("%s"), 2)

    def test_insert_or_ignore_conversion(self):
        db = DbConnection.__new__(DbConnection)
        db.backend = "postgres"
        sql = db._adapt_sql("INSERT OR IGNORE INTO items (name) VALUES (?)")
        self.assertNotIn("INSERT OR IGNORE", sql)
        self.assertIn("ON CONFLICT DO NOTHING", sql)
        self.assertIn("%s", sql)


class TestInitDb(unittest.TestCase):
    def test_init_with_schema(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            db = init_db(db_path=path, schema=_TEST_SCHEMA)
            db.execute(
                "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
                ("hello", "active", "2026-01-01"),
            )
            db.commit()
            row = db.execute("SELECT name FROM items").fetchone()
            self.assertEqual(row["name"], "hello")
        finally:
            close_db()
            os.unlink(path)

    def test_init_without_schema(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            db = init_db(db_path=path)
            # Should work but no tables exist
            self.assertEqual(db.backend, "sqlite")
        finally:
            close_db()
            os.unlink(path)

    def test_no_path_no_env_raises(self):
        close_db()
        old = os.environ.pop("DATABASE_URL", None)
        try:
            with self.assertRaises(ValueError):
                init_db()
        finally:
            if old is not None:
                os.environ["DATABASE_URL"] = old


class TestBaseRepository(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = init_db(db_path=self.tmp.name, schema=_TEST_SCHEMA)
        self.repo = BaseRepository(self.db)

    def tearDown(self):
        close_db()
        os.unlink(self.tmp.name)

    def test_now_returns_iso_string(self):
        now = self.repo._now()
        self.assertIn("T", now)
        self.assertIn("-", now)

    def test_row_to_dict(self):
        self.db.execute(
            "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
            ("x", "active", "2026-01-01"),
        )
        self.db.commit()
        row = self.db.execute("SELECT * FROM items").fetchone()
        d = self.repo._row_to_dict(row)
        self.assertIsInstance(d, dict)
        self.assertEqual(d["name"], "x")

    def test_row_to_dict_none(self):
        self.assertIsNone(self.repo._row_to_dict(None))

    def test_update_status(self):
        self.db.execute(
            "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
            ("y", "active", "2026-01-01"),
        )
        self.db.commit()
        row = self.db.execute("SELECT item_id FROM items WHERE name = ?", ("y",)).fetchone()
        item_id = str(row["item_id"])
        self.repo.update_status("items", "item_id", item_id, "completed")
        updated = self.db.execute(
            "SELECT status FROM items WHERE item_id = ?", (item_id,)
        ).fetchone()
        self.assertEqual(updated["status"], "completed")

    def test_checkpoint_save_and_get(self):
        self.repo.save_checkpoint("last_block", "12345")
        val = self.repo.get_checkpoint("last_block")
        self.assertEqual(val, "12345")

    def test_checkpoint_upsert(self):
        self.repo.save_checkpoint("last_block", "100")
        self.repo.save_checkpoint("last_block", "200")
        val = self.repo.get_checkpoint("last_block")
        self.assertEqual(val, "200")

    def test_checkpoint_missing_returns_none(self):
        self.assertIsNone(self.repo.get_checkpoint("nonexistent"))

    def test_cached_count(self):
        self.db.execute(
            "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
            ("a", "active", "2026-01-01"),
        )
        self.db.execute(
            "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
            ("b", "active", "2026-01-01"),
        )
        self.db.commit()
        count = self.repo._cached_count(
            "items_active",
            "SELECT COUNT(*) as cnt FROM items WHERE status = ?",
            ("active",),
        )
        self.assertEqual(count, 2)
        # Second call hits cache
        count2 = self.repo._cached_count(
            "items_active",
            "SELECT COUNT(*) as cnt FROM items WHERE status = ?",
            ("active",),
        )
        self.assertEqual(count2, 2)

    def test_rows_to_dicts(self):
        self.db.execute(
            "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
            ("p", "active", "2026-01-01"),
        )
        self.db.execute(
            "INSERT INTO items (name, status, updated_at) VALUES (?, ?, ?)",
            ("q", "done", "2026-01-02"),
        )
        self.db.commit()
        rows = self.db.execute("SELECT * FROM items").fetchall()
        dicts = self.repo._rows_to_dicts(rows)
        self.assertEqual(len(dicts), 2)
        self.assertIsInstance(dicts[0], dict)


if __name__ == "__main__":
    unittest.main()
