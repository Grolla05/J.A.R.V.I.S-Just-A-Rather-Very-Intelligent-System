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

    def test_config_strings_keep_type(self):
        # #55: string que parece JSON volta como string
        for value in ("123", "true", "null", "[]", '{"a": 1}', "", "1"):
            self.db.save_config("s", value)
            self.assertEqual(self.db.get_config("s"), value)
            self.assertIsInstance(self.db.get_config("s"), str)

    def test_config_json_types_roundtrip(self):
        for value in (123, 0, True, False, None, [1, "a"], {"k": [1, 2]}, 1.5, "ç"):
            self.db.save_config("j", value)
            self.assertEqual(self.db.get_config("j"), value)

    def test_config_type_switch_on_upsert(self):
        self.db.save_config("t", 5)
        self.db.save_config("t", "5")
        self.assertEqual(self.db.get_config("t"), "5")
        self.db.save_config("t", 5)
        self.assertEqual(self.db.get_config("t"), 5)

    def test_legacy_rows_keep_old_behaviour(self):
        # Linhas gravadas antes da coluna is_json (NULL): tenta json.loads
        with self.db.connection() as conn:
            conn.execute("INSERT INTO config (key, value) VALUES ('old_json', '[1, 2]')")
            conn.execute("INSERT INTO config (key, value) VALUES ('old_text', 'G1, BBC')")
        self.assertEqual(self.db.get_config("old_json"), [1, 2])
        self.assertEqual(self.db.get_config("old_text"), "G1, BBC")

    def test_migration_adds_is_json_to_old_db(self):
        with self.db.connection() as conn:
            conn.execute("DROP TABLE config")
            conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                         "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("INSERT INTO config (key, value) VALUES ('x', '7')")
        db2 = database.DatabaseManager()
        with db2.connection() as conn:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(config)")]
        self.assertIn("is_json", cols)
        self.assertEqual(db2.get_config("x"), 7)  # legado
        db2.save_config("x", "7")
        self.assertEqual(db2.get_config("x"), "7")


if __name__ == "__main__":
    unittest.main()
