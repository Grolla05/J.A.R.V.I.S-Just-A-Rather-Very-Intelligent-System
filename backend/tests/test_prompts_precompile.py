"""Feature 4 — load_prompt pré-compila o string.Template (reusa o mesmo objeto
enquanto o mtime não muda; recompila quando o .md é editado em runtime)."""
import os
import tempfile
import unittest

from tests._stubs import install

install()

import core.prompts as prompts


class TestPromptPrecompile(unittest.TestCase):
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

    def test_template_object_reused_on_cache_hit(self):
        self._write("Olá $nome", mtime=1000)
        prompts.load_prompt("p.md", nome="A")
        tmpl1 = prompts._prompt_cache[self._file][2]
        prompts.load_prompt("p.md", nome="B")
        tmpl2 = prompts._prompt_cache[self._file][2]
        self.assertIs(tmpl1, tmpl2)  # mesmo objeto → sem reparse

    def test_template_recompiled_on_mtime_change(self):
        self._write("Olá $nome", mtime=1000)
        prompts.load_prompt("p.md", nome="A")
        tmpl1 = prompts._prompt_cache[self._file][2]
        self._write("Oi $nome", mtime=2000)  # edição em runtime
        self.assertEqual(prompts.load_prompt("p.md", nome="A"), "Oi A")
        tmpl2 = prompts._prompt_cache[self._file][2]
        self.assertIsNot(tmpl1, tmpl2)        # novo objeto compilado

    def test_substitution_still_correct(self):
        self._write("Olá $nome", mtime=1000)
        self.assertEqual(prompts.load_prompt("p.md", nome="Felipe"), "Olá Felipe")

    def test_cache_tuple_keeps_mtime_first(self):
        # Garante retrocompatibilidade com test_prompts.py (índice 0 == mtime)
        self._write("v1", mtime=1000)
        prompts.load_prompt("p.md")
        self.assertEqual(prompts._prompt_cache[self._file][0], 1000)


if __name__ == "__main__":
    unittest.main()
