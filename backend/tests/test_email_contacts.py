"""services.email_contacts — "Guilherme" → endereço (apelidos no SQLite + histórico do Gmail)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.database as database  # noqa: E402
from core.config import settings  # noqa: E402
from services import email_contacts as contacts  # noqa: E402


class ContactsCase(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path, self._orig = path, settings.DB_PATH
        settings.DB_PATH = Path(path)
        self.db = database.DatabaseManager()
        self._patch = patch.object(contacts, "db", self.db)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass

    def test_address_passes_through(self):
        finder = MagicMock()
        self.assertEqual(contacts.resolve("gui@empresa.com", finder=finder), (contacts.FOUND, "gui@empresa.com"))
        finder.assert_not_called()

    def test_single_candidate_from_gmail(self):
        finder = MagicMock(return_value=[{"name": "Guilherme Souza", "address": "gui@empresa.com", "count": 3}])
        self.assertEqual(contacts.resolve("Guilherme", finder=finder), (contacts.FOUND, "gui@empresa.com"))

    def test_several_candidates_ask(self):
        finder = MagicMock(return_value=[{"name": "Guilherme Souza", "address": "gui@empresa.com", "count": 3},
                                         {"name": "Guilherme Lima", "address": "glima@outra.com", "count": 1}])
        status, items = contacts.resolve("Guilherme", finder=finder)
        self.assertEqual(status, contacts.MANY)
        self.assertEqual(len(items), 2)
        self.assertIn("glima@outra.com", contacts.ask_text("Guilherme", items))

    def test_none(self):
        self.assertEqual(contacts.resolve("Zé", finder=MagicMock(return_value=[])), (contacts.NONE, None))
        self.assertEqual(contacts.resolve("Zé", finder=MagicMock(side_effect=RuntimeError("off"))),
                         (contacts.NONE, None))

    def test_saved_alias_wins_and_is_case_insensitive(self):
        self.assertTrue(contacts.remember("Guilherme", "gui@empresa.com"))
        finder = MagicMock()
        self.assertEqual(contacts.resolve("guilherme", finder=finder), (contacts.FOUND, "gui@empresa.com"))
        self.assertEqual(contacts.resolve("o Guilherme", finder=finder), (contacts.FOUND, "gui@empresa.com"))
        finder.assert_not_called()
        self.assertFalse(contacts.remember("Bob", "nao-e-email"))


if __name__ == "__main__":
    unittest.main()
