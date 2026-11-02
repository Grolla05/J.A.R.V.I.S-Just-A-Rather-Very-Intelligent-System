"""Fix #2 — load_prompt invalida cache por mtime quando o .md muda em runtime."""
import os
import tempfile
import unittest

from tests._stubs import install

install()

import core.prompts as prompts


class TestPromptMtimeCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_dir = prompts.PROMPTS_DIR
        prompts.PROMPTS_DIR = self._tmp
        prompts._prompt_cache.clear()
        self._file = os.path.join(self._tmp, "p.md")

    def tearDown(self):
        prompts.PROMPTS_DIR = self._orig_dir
        prompts._prompt_cache.clear()

    def _write(self, content, mtime):
        with open(self._file, "w", encoding="utf-8") as f:
            f.write(content)
        os.utime(self._file, (mtime, mtime))

    def test_reads_and_caches(self):
        self._write("v1", mtime=1000)
        self.assertEqual(prompts.load_prompt("p.md"), "v1")
        # Segundo load com mesmo mtime serve do cache (mtime guardado bate)
        self.assertEqual(prompts.load_prompt("p.md"), "v1")
        self.assertEqual(prompts._prompt_cache[self._file][0], 1000)

    def test_invalidates_on_mtime_change(self):
        self._write("v1", mtime=1000)
        self.assertEqual(prompts.load_prompt("p.md"), "v1")
        # Edição em runtime: novo conteúdo + mtime maior → cache deve recarregar
        self._write("v2", mtime=2000)
        self.assertEqual(prompts.load_prompt("p.md"), "v2")

    def test_template_substitution(self):
        self._write("Olá $nome", mtime=1000)
        self.assertEqual(prompts.load_prompt("p.md", nome="Felipe"), "Olá Felipe")

    def test_missing_file_returns_empty(self):
        self.assertEqual(prompts.load_prompt("inexistente.md"), "")


if __name__ == "__main__":
    unittest.main()
