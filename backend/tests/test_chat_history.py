"""#53 — histórico do chat para a IA: ordem por id, conexão fechada e limite."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._stubs import install

install()

import core.database as database
import services.chat as chat
from core.config import settings


class TestChatHistory(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path = path
        self._orig = settings.DB_PATH
        settings.DB_PATH = Path(path)
        self.db = database.DatabaseManager()
        self._patch = patch.object(chat, "db", self.db)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass

    def _same_second(self, rows):
        # Todas as linhas com o mesmo timestamp: só o id desempata
        with self.db.connection() as conn:
            for role, content in rows:
                conn.execute("INSERT INTO history (session_id, role, content, timestamp) "
                             "VALUES ('s', ?, ?, '2026-01-01 10:00:00')", (role, content))

    def test_order_by_id_when_timestamps_tie(self):
        self._same_second([("user", "p1"), ("assistant", "r1"), ("user", "p2"),
                           ("assistant", "r2"), ("user", "atual")])
        msgs = chat.get_session_history_for_ai("s", limit=10)
        self.assertEqual([m["content"] for m in msgs], ["p1", "r1", "p2", "r2"])
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "user", "assistant"])

    def test_limit_keeps_most_recent(self):
        self._same_second([("user", "p1"), ("assistant", "r1"), ("user", "p2"),
                           ("assistant", "r2"), ("user", "atual")])
        msgs = chat.get_session_history_for_ai("s", limit=2)
        self.assertEqual([m["content"] for m in msgs], ["p2", "r2"])

    def test_default_limit_from_settings(self):
        rows = []
        for i in range(30):
            rows += [("user", f"p{i}"), ("assistant", f"r{i}")]
        self._same_second(rows + [("user", "atual")])
        with patch.object(settings, "CHAT_HISTORY_TURNS", 3):
            msgs = chat.get_session_history_for_ai("s")
        self.assertEqual([m["content"] for m in msgs], ["p27", "r27", "p28", "r28", "p29", "r29"])

    def test_db_error_returns_empty(self):
        with patch.object(self.db, "connection", side_effect=RuntimeError("boom")):
            self.assertEqual(chat.get_session_history_for_ai("s"), [])

    def test_composite_index_exists(self):
        with self.db.connection() as conn:
            names = [r[1] for r in conn.execute("PRAGMA index_list(history)")]
        self.assertIn("idx_history_session_id", names)


if __name__ == "__main__":
    unittest.main()
