"""core.obsidian — protocolo do mcp-obsidian e busca que volta como texto de erro."""
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

import sys  # noqa: E402

from core.obsidian import get_vault_context, mcp_endpoint  # noqa: E402

# `core.obsidian` como atributo é a instância ObsidianClient (core/__init__ a
# reexporta com o mesmo nome); o módulo de verdade fica em sys.modules.
obsidian_mod = sys.modules["core.obsidian"]


class TestMcpEndpoint(unittest.TestCase):
    def test_scheme_decides_protocol(self):
        self.assertEqual(mcp_endpoint("http://127.0.0.1:27123"), ("http", "127.0.0.1", "27123"))
        self.assertEqual(mcp_endpoint("https://127.0.0.1:27124/"), ("https", "127.0.0.1", "27124"))
        self.assertEqual(mcp_endpoint("HTTP://localhost:9000"), ("http", "localhost", "9000"))

    def test_without_scheme_port_decides(self):
        self.assertEqual(mcp_endpoint("127.0.0.1:27124"), ("https", "127.0.0.1", "27124"))
        self.assertEqual(mcp_endpoint("127.0.0.1:27123"), ("http", "127.0.0.1", "27123"))
        self.assertEqual(mcp_endpoint("127.0.0.1"), ("http", "127.0.0.1", "27123"))

    def test_default_ports_and_empty(self):
        self.assertEqual(mcp_endpoint("https://127.0.0.1"), ("https", "127.0.0.1", "27124"))
        self.assertEqual(mcp_endpoint(""), ("http", "127.0.0.1", "27123"))


class TestSearchErrorText(unittest.TestCase):
    def setUp(self):
        obsidian_mod._search_warned = False

    def test_non_json_result_warns_once_and_returns_empty(self):
        error = "Caught Exception. Error: Request failed: SSLError(WRONG_VERSION_NUMBER)"
        with patch.object(obsidian_mod.mcp_client, "call", return_value=error), \
             patch.object(obsidian_mod.log, "warning") as warning, \
             patch.object(obsidian_mod.log, "error") as error_log:
            self.assertEqual(get_vault_context("projeto jarvis agora"), ("", ""))
            self.assertEqual(get_vault_context("outra pergunta qualquer"), ("", ""))
        self.assertEqual(warning.call_count, 1)
        self.assertIn("Busca indisponível", warning.call_args[0][0])
        error_log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
