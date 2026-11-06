"""TUI — services.sessions (SQL extraído da antiga bridge PyWebView)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._stubs import install

install()

import core.database as database
import services.sessions as sessions
from core.config import settings


class TestSessionsService(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path = path
        self._orig = settings.DB_PATH
        settings.DB_PATH = Path(path)
        self.db = database.DatabaseManager()
        self._patch = patch.object(sessions, "db", self.db)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass

    def _chat(self, sid, *pairs):
        for user, assistant in pairs:
            self.db.log_interaction("user", user, sid)
            self.db.log_interaction("assistant", assistant, sid)

    def test_to_local_converts_sqlite_utc(self):
        from datetime import datetime, timezone
        utc = datetime(2026, 11, 3, 12, 44, 0, tzinfo=timezone.utc)
        expected = utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self.assertEqual(sessions.to_local("2026-11-03 12:44:00"), expected)
        self.assertIsNone(sessions.to_local(None))

    def test_new_session_id_is_unique_and_not_voice(self):
        a, b = sessions.new_session_id(), sessions.new_session_id()
        self.assertNotEqual(a, b)
        self.assertFalse(a.startswith("voice_"))

    def test_history_is_chronological_with_roles(self):
        self._chat("s1", ("oi", "olá"), ("tudo bem?", "sim"))
        history = sessions.get_chat_history("s1")
        self.assertEqual([m["content"] for m in history], ["oi", "olá", "tudo bem?", "sim"])
        self.assertEqual([m["role"] for m in history], ["user", "assistant", "user", "assistant"])
        self.assertIsNone(history[0]["attachment"])

    def test_attachment_shows_original_name(self):
        self.db.log_interaction("user", "o que é isso?", "s1", "image", "image/abc123_foto.png")
        self.assertEqual(sessions.get_chat_history("s1")[0]["attachment"], "foto.png")

    def test_delete_history_from_removes_tail(self):
        self._chat("s1", ("a", "b"), ("c", "d"))
        third = sessions.get_chat_history("s1")[2]
        self.assertTrue(sessions.delete_history_from("s1", third["id"]))
        self.assertEqual([m["content"] for m in sessions.get_chat_history("s1")], ["a", "b"])

    def test_title_falls_back_to_first_prompt_then_rename(self):
        self._chat("s1", ("primeira pergunta", "resp"))
        self.assertEqual(sessions.get_session_title("s1"), "primeira pergunta")
        self.assertTrue(sessions.update_session_title("s1", "Meu título"))
        self.assertEqual(sessions.get_session_title("s1"), "Meu título")

    def test_recent_sessions_exclude_voice_and_pinned_first(self):
        self._chat("s_old", ("velha", "x"))
        self._chat("s_new", ("nova", "y"))
        self._chat("voice_abc", ("voz", "z"))
        self.assertTrue(sessions.toggle_session_pin("s_old", True))
        recent = sessions.get_recent_sessions()
        ids = [s["id"] for s in recent]
        self.assertNotIn("voice_abc", ids)
        self.assertEqual(ids[0], "s_old")
        self.assertTrue(recent[0]["is_pinned"])
        self.assertEqual(recent[0]["title"], "velha")

    def test_recent_sessions_bring_count_and_last_message(self):
        self._chat("s1", ("oi", "olá"), ("tudo bem?", "tudo certo, Senhor"))
        recent = sessions.get_recent_sessions()
        self.assertEqual(recent[0]["msg_count"], 4)
        self.assertEqual(recent[0]["last_message"], "tudo certo, Senhor")

    def test_recent_sessions_bring_mode_and_last_reply(self):
        self.db.log_interaction("assistant", "Abrindo VS Code, Senhor.", "s1", mode="copilot")
        self.db.log_interaction("user", "valeu", "s1", mode="copilot")
        self._chat("s0", ("sem modo", "resposta antiga"))
        recent = {s["id"]: s for s in sessions.get_recent_sessions()}
        self.assertEqual(recent["s1"]["mode"], "copilot")
        self.assertEqual(recent["s1"]["last_reply"], "Abrindo VS Code, Senhor.")
        self.assertEqual(recent["s1"]["last_message"], "valeu")
        self.assertEqual(recent["s0"]["mode"], "chat")  # banco antigo: sem modo = chat

    def test_old_history_table_gains_mode_column(self):
        import sqlite3
        conn = sqlite3.connect(self._path)
        conn.execute("DROP TABLE history")
        conn.execute("CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL "
                     "DEFAULT 'default', role TEXT NOT NULL, content TEXT NOT NULL, "
                     "timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.commit()
        conn.close()
        database.DatabaseManager()
        conn = sqlite3.connect(self._path)
        try:
            columns = [c[1] for c in conn.execute("PRAGMA table_info(history)")]
        finally:
            conn.close()
        self.assertIn("mode", columns)

    def test_delete_session_removes_history_and_meta(self):
        self._chat("s1", ("a", "b"))
        self._chat("s2", ("c", "d"))
        sessions.toggle_session_pin("s1", True)
        self.assertTrue(sessions.delete_session("s1"))
        self.assertEqual(sessions.get_chat_history("s1"), [])
        self.assertEqual([s["id"] for s in sessions.get_recent_sessions()], ["s2"])


if __name__ == "__main__":
    unittest.main()
