"""Feature 1 — warm_up_ollama pré-carrega o modelo (chama chat 1×) e engole
exceções sem propagar (se o Ollama ainda não subiu, o boot segue)."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.llm as llm


class TestWarmUp(unittest.TestCase):
    def test_calls_chat_once_with_keep_alive(self):
        client = MagicMock()
        with patch.object(llm, "_get_client", return_value=client):
            llm.warm_up_ollama()
        client.chat.assert_called_once()
        # keep_alive deve ser repassado para manter o modelo residente
        _, kwargs = client.chat.call_args
        self.assertIn("keep_alive", kwargs)
        self.assertEqual(kwargs["keep_alive"], llm.settings.OLLAMA_KEEP_ALIVE)

    def test_swallows_exception(self):
        with patch.object(llm, "_get_client", side_effect=ConnectionError("offline")):
            try:
                llm.warm_up_ollama()  # não deve propagar
            except Exception as e:
                self.fail(f"warm_up_ollama propagou exceção: {e}")

    def test_query_ollama_passes_keep_alive(self):
        client = MagicMock()
        client.chat.return_value = {"message": {"content": "ok"}}
        with patch.object(llm, "_get_client", return_value=client):
            out = llm.query_ollama([{"role": "user", "content": "oi"}])
        self.assertEqual(out, "ok")
        _, kwargs = client.chat.call_args
        self.assertEqual(kwargs["keep_alive"], llm.settings.OLLAMA_KEEP_ALIVE)


if __name__ == "__main__":
    unittest.main()
