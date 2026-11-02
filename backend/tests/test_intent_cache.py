"""Feature 2 — classify_intent memoiza via TTLCache (não reconsulta o LLM em
comandos repetidos dentro do TTL)."""
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

import services.intent as intent

_OLLAMA_JSON = '{"intent": "CHAT", "entity": null, "confidence": 0.9}'


class TestIntentCache(unittest.TestCase):
    def setUp(self):
        intent._intent_cache.clear()
        # skip_skills=True não itera manager; zeramos por segurança.
        intent.manager.skills = {}

    def _run(self, text="abrir o spotify"):
        with patch.object(intent, "query_ollama", return_value=_OLLAMA_JSON) as q, \
             patch.object(intent, "load_prompt", return_value="prompt"):
            result = intent.classify_intent(text, skip_skills=True)
            return result, q

    def test_first_call_hits_ollama(self):
        result, q = self._run()
        q.assert_called_once()
        self.assertEqual(result["intent"], "CHAT")

    def test_repeated_call_served_from_cache(self):
        self._run()                       # 1ª: consulta o LLM e cacheia
        _, q2 = self._run()               # 2ª (mesmo texto): serve do cache
        q2.assert_not_called()

    def test_normalization_case_and_space(self):
        self._run("Abrir o Spotify")
        _, q2 = self._run("  abrir o spotify  ")  # mesma chave normalizada
        q2.assert_not_called()

    def test_different_text_recomputes(self):
        self._run("abrir o spotify")
        _, q2 = self._run("fechar o chrome")      # chave diferente → LLM de novo
        q2.assert_called_once()

    def test_expired_entry_recomputes(self):
        self._run("abrir o spotify")
        # Força expiração da entrada cacheada
        key = ("abrir o spotify", True)
        value, _ = intent._intent_cache._store[key]
        intent._intent_cache._store[key] = (value, intent._intent_cache._time() - 1)
        _, q2 = self._run("abrir o spotify")
        q2.assert_called_once()

    def test_cached_copy_is_isolated(self):
        result, _ = self._run("abrir o spotify")
        result["intent"] = "MUTADO"               # muta o retorno do chamador
        result2, _ = self._run("abrir o spotify")  # cache não deve refletir a mutação
        self.assertEqual(result2["intent"], "CHAT")


if __name__ == "__main__":
    unittest.main()
