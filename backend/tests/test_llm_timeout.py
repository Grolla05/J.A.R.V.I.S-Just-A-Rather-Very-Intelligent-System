"""Fix #3 — query_ollama propaga `timeout` ao Client (fallback 120s se None)."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import llm


def _fake_client_factory():
    client = MagicMock()
    client.chat.return_value = {"message": {"content": "ok"}}
    return MagicMock(return_value=client), client


class TestQueryOllamaTimeout(unittest.TestCase):
    def test_custom_timeout_forwarded(self):
        Client, _ = _fake_client_factory()
        with patch("ollama.Client", Client):
            out = llm.query_ollama([{"role": "user", "content": "hi"}], timeout=7)
        self.assertEqual(out, "ok")
        self.assertEqual(Client.call_args.kwargs["timeout"], 7)

    def test_default_timeout_is_120(self):
        Client, _ = _fake_client_factory()
        with patch("ollama.Client", Client):
            llm.query_ollama([{"role": "user", "content": "hi"}])
        self.assertEqual(Client.call_args.kwargs["timeout"], 120)

    def test_error_returns_none(self):
        Client = MagicMock(side_effect=RuntimeError("boom"))
        with patch("ollama.Client", Client):
            self.assertIsNone(llm.query_ollama([{"role": "user", "content": "hi"}]))


class TestClassifyIntentFallback(unittest.TestCase):
    def test_fallback_chat_when_ollama_returns_none(self):
        import services.intent as intent
        with patch.object(intent, "query_ollama", return_value=None):
            res = intent.classify_intent("qualquer coisa", skip_skills=True)
        self.assertEqual(res["intent"], "CHAT")
        self.assertEqual(res["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
