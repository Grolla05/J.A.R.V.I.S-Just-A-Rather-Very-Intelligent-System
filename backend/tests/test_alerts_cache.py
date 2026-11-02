"""Fix #1 — PROCESS_JUDGEMENT_CACHE com TTL (não cresce/serve entrada vencida)."""
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

# alerts importa services.listen (instancia mic) e services.speak no topo.
# Stub só os submódulos (não o pacote namespace `services`, senão quebra
# services.intent em outros testes) para não tocar hardware.
sys.modules["services.listen"] = MagicMock()
sys.modules["services.speak"] = MagicMock()

import core.alerts as alerts

# Mensagem proativa com culpado extraível pelo regex (Consumo: <app> ()
_MSG = "Processo pesado detectado. Consumo: chrome.exe (95%)"


class TestJudgementCacheTTL(unittest.TestCase):
    def setUp(self):
        alerts.PROCESS_JUDGEMENT_CACHE.clear()

    def _run(self, judge_return="NÃO"):
        with patch.object(alerts, "query_ollama", return_value=judge_return) as q, \
             patch.object(alerts, "speak"), \
             patch.object(alerts, "ear_pause"), \
             patch.object(alerts, "ear_resume"), \
             patch.object(alerts, "load_prompt", return_value="prompt"):
            alerts.process_system_alert(_MSG, is_proactive=True)
            return q

    def test_stores_tuple_with_expiry(self):
        self._run()
        entry = alerts.PROCESS_JUDGEMENT_CACHE["chrome.exe"]
        self.assertIsInstance(entry, tuple)
        self.assertEqual(entry[0], "NÃO")
        self.assertGreater(entry[1], time.time())  # expiry no futuro

    def test_cache_hit_skips_ollama(self):
        self._run()                       # 1ª chamada consulta o LLM
        q2 = self._run()                  # 2ª deve servir do cache
        q2.assert_not_called()

    def test_expired_entry_recomputes(self):
        self._run()
        # Força expiração no passado
        alerts.PROCESS_JUDGEMENT_CACHE["chrome.exe"] = ("NÃO", time.time() - 1)
        q = self._run()
        q.assert_called_once()            # vencido → reconsulta o LLM

    def test_ttl_is_one_hour(self):
        self.assertEqual(alerts.JUDGEMENT_TTL, 3600)


if __name__ == "__main__":
    unittest.main()
