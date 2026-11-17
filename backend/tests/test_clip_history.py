"""services.clip_history — histórico persistente do clipboard (SQLite temporário)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._stubs import install

install()

import core.database as database  # noqa: E402
from core.config import settings  # noqa: E402
from services import clip_history  # noqa: E402

CODE = "def soma(a, b):\n    return a + b"
TEXT = "O relatório de vendas do mês passado está na pasta da equipe."


class ClipHistoryCase(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path = path
        self._orig = settings.DB_PATH
        settings.DB_PATH = Path(path)
        self.db = database.DatabaseManager()
        self._patch = patch.object(clip_history, "db", self.db)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass


class TestStore(ClipHistoryCase):
    def test_add_recent_and_get(self):
        self.assertTrue(clip_history.add("code", CODE))
        self.assertTrue(clip_history.add("text", TEXT))
        items = clip_history.recent()
        self.assertEqual([i["text"] for i in items], [TEXT, CODE])
        self.assertEqual(items[1]["kind"], "code")
        self.assertEqual(clip_history.get(1)["text"], TEXT)
        self.assertEqual(clip_history.get(2)["text"], CODE)
        self.assertIsNone(clip_history.get(3))
        self.assertIsNone(clip_history.get(0))

    def test_survives_new_manager(self):
        """Persistência: outro DatabaseManager (outra sessão) enxerga as cópias."""
        clip_history.add("code", CODE)
        with patch.object(clip_history, "db", database.DatabaseManager()):
            self.assertEqual(clip_history.recent()[0]["text"], CODE)

    def test_recopy_moves_to_top_without_duplicating(self):
        clip_history.add("code", CODE)
        clip_history.add("text", TEXT)
        clip_history.add("code", CODE)
        items = clip_history.recent()
        self.assertEqual([i["text"] for i in items], [CODE, TEXT])

    def test_prunes_to_max_rows(self):
        with patch.object(clip_history, "MAX_ROWS", 3):
            for i in range(6):
                clip_history.add("text", f"cópia número {i} com texto suficiente")
        items = clip_history.recent(limit=10)
        self.assertEqual(len(items), 3)
        self.assertIn("número 5", items[0]["text"])

    def test_empty_and_secret_are_dropped(self):
        self.assertFalse(clip_history.add("text", "   "))
        self.assertFalse(clip_history.add("text", "S3nh@Forte!2026"))
        self.assertEqual(clip_history.recent(), [])

    def test_search(self):
        clip_history.add("code", CODE)
        clip_history.add("text", TEXT)
        clip_history.add("text", "desconto de 100% no fechamento do trimestre")
        self.assertEqual([i["text"] for i in clip_history.search("vendas")], [TEXT])
        self.assertEqual([i["text"] for i in clip_history.search("SOMA")], [CODE])
        self.assertEqual(clip_history.search("inexistente"), [])
        self.assertEqual(clip_history.search("  "), [])
        self.assertEqual(len(clip_history.search("100%")), 1)  # % é literal, não curinga
        self.assertEqual(clip_history.search("%"), clip_history.search("100%"))

    def test_clear(self):
        clip_history.add("code", CODE)
        clip_history.add("text", TEXT)
        self.assertEqual(clip_history.clear(), 2)
        self.assertEqual(clip_history.recent(), [])

    def test_to_markdown_numbers_items(self):
        clip_history.add("code", CODE)
        clip_history.add("text", TEXT)
        text = clip_history.to_markdown(clip_history.recent(), "Últimas cópias:")
        self.assertIn("1. *texto*", text)
        self.assertIn("2. *código*", text)
        self.assertIn("def soma", text)


class TestLooksSecret(unittest.TestCase):
    def test_cases(self):
        cases = {
            "S3nh@Forte!2026": True,
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789": True,
            "sk-proj-abcdefghijklmnop": True,
            "https://github.com/Jarvis-Project-2026/J.A.R.V.I.S": False,
            "palavra": False,
            "relatorio_de_vendas": False,
            "uma frase comum com Espaços e 1 número!": False,
            "": False,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(clip_history.looks_secret(text), expected)


if __name__ == "__main__":
    unittest.main()
