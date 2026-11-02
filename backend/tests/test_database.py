"""Fix #6/#7 — SQLite em WAL + context manager (commit/rollback/close)."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests._stubs import install

install()

import core.database as database
from core.config import settings


class TestDatabaseWalAndContextManager(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path = path
        self._orig = settings.DB_PATH
        settings.DB_PATH = Path(path)
        self.db = database.DatabaseManager()  # __init__ chama _initialize_tables

    def tearDown(self):
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass

    def test_wal_mode_enabled(self):
        with self.db.connection() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode.lower(), "wal")

    def test_config_roundtrip_str_and_json(self):
        self.db.save_config("a", "hello")
        self.assertEqual(self.db.get_config("a"), "hello")
        self.db.save_config("b", {"x": 1})
        self.assertEqual(self.db.get_config("b"), {"x": 1})

    def test_context_manager_commits(self):
        with self.db.connection() as conn:
            conn.execute("INSERT INTO config (key, value) VALUES ('k','v')")
        # Nova conexão deve enxergar o commit feito pelo CM ao sair do bloco
        self.assertEqual(self.db.get_config("k"), "v")

    def test_context_manager_rollback_on_error(self):
        with self.assertRaises(sqlite3.Error):
            with self.db.connection() as conn:
                conn.execute("INSERT INTO config (key, value) VALUES ('z','1')")
                conn.execute("INSERT INTO tabela_inexistente VALUES (1)")  # erro
        # Rollback descartou o primeiro insert
        self.assertIsNone(self.db.get_config("z"))

    def test_missing_config_returns_none(self):
        self.assertIsNone(self.db.get_config("nao_existe"))


if __name__ == "__main__":
    unittest.main()
