"""services.memory — resposta honesta quando a nota já existe (issue #29)."""
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.obsidian  # noqa: E402,F401

obsidian_mod = sys.modules["core.obsidian"]
import services.memory as memory  # noqa: E402
from core.obsidian import MEMORY_KEPT, MEMORY_SAVED  # noqa: E402


def _llm(key, value):
    return json.dumps({"key": key, "value": value})


class TestSaveMemoryResult(unittest.TestCase):
    def setUp(self):
        self.client = obsidian_mod.ObsidianClient.__new__(obsidian_mod.ObsidianClient)

    def test_existing_note_is_kept(self):
        with patch.object(self.client, "get_memory", return_value="Campinas"), \
             patch.object(self.client, "_req") as req:
            self.assertEqual(self.client.save_memory("cidade", "Santos"), MEMORY_KEPT)
            req.assert_not_called()

    def test_new_note_is_saved(self):
        with patch.object(self.client, "get_memory", return_value=None), \
             patch.object(self.client, "_req", return_value=MagicMock()):
            self.assertEqual(self.client.save_memory("cidade", "Santos"), MEMORY_SAVED)

    def test_write_failure_is_none(self):
        with patch.object(self.client, "get_memory", return_value=None), \
             patch.object(self.client, "_req", return_value=None):
            self.assertIsNone(self.client.save_memory("cidade", "Santos"))


class TestExtractFactReply(unittest.TestCase):
    def _run(self, save_result, current=None):
        fake = MagicMock()
        fake.save_memory.return_value = save_result
        fake.get_memory.return_value = current
        with patch.object(memory, "obsidian", fake), \
             patch.object(memory, "query_ollama", return_value=_llm("Cidade", "Santos")), \
             patch.object(memory, "load_prompt", return_value="p"):
            return memory.extract_fact_to_memory("me mudei para Santos")

    def test_saved(self):
        self.assertIn("Memorizado no vault: cidade = Santos", self._run(MEMORY_SAVED))

    def test_kept_with_different_value_does_not_claim_memorized(self):
        reply = self._run(MEMORY_KEPT, current="Campinas")
        self.assertNotIn("Memorizado", reply)
        self.assertIn("Campinas", reply)
        self.assertIn("mantive a versão do vault", reply)

    def test_kept_with_same_value(self):
        self.assertIn("Já estava memorizado", self._run(MEMORY_KEPT, current="santos"))

    def test_write_failure(self):
        reply = self._run(None)
        self.assertNotIn("Memorizado", reply)
        self.assertIn("Não consegui gravar", reply)


if __name__ == "__main__":
    unittest.main()
