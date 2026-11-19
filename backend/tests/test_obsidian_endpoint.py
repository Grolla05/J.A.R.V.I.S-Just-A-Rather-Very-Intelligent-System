"""core.obsidian — RAG pela API REST do plugin Local REST API (#48: sem MCP/uvx)."""
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

import sys  # noqa: E402

from core.obsidian import get_vault_context  # noqa: E402

# `core.obsidian` como atributo é a instância ObsidianClient (core/__init__ a
# reexporta com o mesmo nome); o módulo de verdade fica em sys.modules.
obsidian_mod = sys.modules["core.obsidian"]
client = obsidian_mod.obsidian


class TestVaultContextRest(unittest.TestCase):
    def setUp(self):
        obsidian_mod._search_warned = False

    def test_no_mcp_client_left(self):
        self.assertFalse(hasattr(obsidian_mod, "mcp_client"))
        self.assertFalse(hasattr(obsidian_mod, "ObsidianMCPClient"))

    def test_obsidian_down_warns_once_and_returns_empty(self):
        with patch.object(client, "search_scored", side_effect=ConnectionError("recusado")), \
             patch.object(obsidian_mod.log, "warning") as warning, \
             patch.object(obsidian_mod.log, "error") as error_log:
            self.assertEqual(get_vault_context("projeto jarvis agora"), ("", ""))
            self.assertEqual(get_vault_context("outra pergunta qualquer"), ("", ""))
        self.assertEqual(warning.call_count, 1)
        self.assertIn("Busca indisponível", warning.call_args[0][0])
        error_log.assert_not_called()

    def test_best_scored_file_is_read(self):
        results = [{"filename": "_templates/x.md", "score": 9.0},
                   {"filename": "Projetos/jarvis.md", "score": 5.0},
                   {"filename": "outro.md", "score": 1.0}]
        with patch.object(client, "search_scored", return_value=results) as search, \
             patch.object(client, "get_file", return_value="conteúdo do projeto") as get_file:
            name, content = get_vault_context("projeto jarvis arquitetura")
        self.assertEqual(name, "Projetos/jarvis.md")
        self.assertIn("conteúdo do projeto", content)
        search.assert_called_once()
        get_file.assert_called_once_with("Projetos/jarvis.md", quiet=True)

    def test_no_results_returns_empty(self):
        with patch.object(client, "search_scored", return_value=[]), \
             patch.object(client, "get_file") as get_file:
            self.assertEqual(get_vault_context("projeto jarvis arquitetura"), ("", ""))
        get_file.assert_not_called()

    def test_profile_layer_reads_note_via_rest(self):
        with patch.object(client, "get_file", return_value="# Identidade\nFelipe") as get_file, \
             patch.object(client, "search_scored") as search:
            name, content = get_vault_context("qual o meu nome?")
        self.assertEqual(name, obsidian_mod._PROFILE_FILE)
        self.assertIn("Felipe", content)
        get_file.assert_called_once_with(obsidian_mod._PROFILE_FILE, quiet=True)
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
