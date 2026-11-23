"""services.local_files — achar um arquivo do usuário para anexar, com bloqueios."""
import os
import tempfile
import time
import unittest
from pathlib import Path

from tests._stubs import install

install()

from services import local_files  # noqa: E402


class FilesCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        for d in ("Desktop", "Documents", "Downloads", ".ssh", "AppData/Local"):
            (self.home / d).mkdir(parents=True)
        self.roots = [self.home / "Desktop", self.home / "Documents", self.home / "Downloads"]

    def tearDown(self):
        self.tmp.cleanup()

    def _file(self, rel, text="x"):
        path = self.home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _find(self, query):
        return local_files.find(query, home=self.home, roots=self.roots)


class TestFind(FilesCase):
    def test_finds_by_name_in_user_folders(self):
        path = self._file("Documents/Propostas/proposta.txt")
        self.assertEqual(self._find("proposta.txt"), (local_files.FOUND, path))
        self.assertEqual(self._find("PROPOSTA.TXT")[1], path)

    def test_several_matches_ask(self):
        a = self._file("Desktop/proposta.txt")
        time.sleep(0.01)
        b = self._file("Downloads/proposta.txt")
        status, items = self._find("proposta.txt")
        self.assertEqual(status, local_files.MANY)
        self.assertEqual(items[0], b)          # mais recente primeiro
        self.assertIn(a, items)

    def test_absolute_path(self):
        path = self._file("Documents/relatorio.pdf")
        self.assertEqual(self._find(str(path)), (local_files.FOUND, path))
        self.assertEqual(self._find(str(self.home / "nao_existe.pdf"))[0], local_files.NONE)

    def test_not_found(self):
        self.assertEqual(self._find("fantasma.docx"), (local_files.NONE, None))

    def test_blocks_sensitive_and_outside(self):
        for rel in (".env", "Documents/.env", ".ssh/id_rsa", "Documents/cofre.kdbx", "Documents/chave.pem",
                    "AppData/Local/token.txt"):
            path = self._file(rel)
            status, reason = self._find(str(path))
            self.assertEqual(status, local_files.BLOCKED, rel)
            self.assertTrue(reason)
        outside = Path(tempfile.gettempdir()) / f"fora_{os.getpid()}.txt"
        outside.write_text("x", encoding="utf-8")
        try:
            self.assertEqual(self._find(str(outside))[0], local_files.BLOCKED)
        finally:
            outside.unlink()

    def test_blocks_big_files(self):
        path = self._file("Documents/grande.bin")
        with open(path, "wb") as f:
            f.truncate(local_files.MAX_BYTES + 1)
        self.assertEqual(self._find(str(path))[0], local_files.BLOCKED)

    def test_sensitive_name_search_is_not_found(self):
        self._file("Documents/.env")
        self.assertEqual(self._find(".env")[0], local_files.BLOCKED)

    def test_human_size(self):
        self.assertEqual(local_files.human_size(512), "512 B")
        self.assertEqual(local_files.human_size(2048), "2,0 KB")
        self.assertEqual(local_files.human_size(3 * 1024 * 1024), "3,0 MB")


if __name__ == "__main__":
    unittest.main()
