"""Fix #1/#61 — PROCESS_JUDGEMENT_CACHE em TTLCache (expira, remove vencidas, limita tamanho)."""
import sys
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

# alerts importa services.listen/speak de forma tardia (dentro de _announce).
# Mesmo assim stub os submódulos (não o pacote namespace `services`, senão
# quebra services.intent em outros testes) para nunca tocar hardware.
sys.modules["services.listen"] = MagicMock()
sys.modules["services.speak"] = MagicMock()

import core.alerts as alerts

# Mensagem proativa com culpado extraível pelo regex (Consumo: <app> ()
_MSG = "Processo pesado detectado. Consumo: chrome.exe (95%)"


class TestJudgementCacheTTL(unittest.TestCase):
    def setUp(self):
        alerts.PROCESS_JUDGEMENT_CACHE.clear()
        # Sem reunião/tela cheia/DND: o filtro de notificações deixa o alerta passar
        import services.notify_filter as nf
        quiet = {"dnd": False, "meeting": False, "fullscreen": False}
        self._ctx = patch.object(nf, "context", return_value=quiet)
        self._ctx.start()
        self.addCleanup(self._ctx.stop)

    def _run(self, judge_return="NÃO"):
        with patch.object(alerts, "query_ollama", return_value=judge_return) as q, \
             patch.object(alerts, "_announce"), \
             patch.object(alerts, "load_prompt", return_value="prompt"):
            alerts.process_system_alert(_MSG, is_proactive=True)
            return q

    def test_stores_decision_in_ttl_cache(self):
        self._run()
        self.assertEqual(alerts.PROCESS_JUDGEMENT_CACHE.get("chrome.exe"), "NÃO")

    def test_cache_hit_skips_ollama(self):
        self._run()                       # 1ª chamada consulta o LLM
        q2 = self._run()                  # 2ª deve servir do cache
        q2.assert_not_called()

    def test_expired_entry_recomputes_and_is_evicted(self):
        clock = [1000.0]
        cache = alerts.TTLCache(maxsize=256, ttl=alerts.JUDGEMENT_TTL, time_fn=lambda: clock[0])
        with patch.object(alerts, "PROCESS_JUDGEMENT_CACHE", cache):
            self._run()
            clock[0] += alerts.JUDGEMENT_TTL + 1
            q = self._run()
            q.assert_called_once()        # vencido → reconsulta o LLM
            self.assertEqual(len(cache._store), 1)  # vencida saiu, nova entrou

    def test_ttl_is_one_hour(self):
        self.assertEqual(alerts.JUDGEMENT_TTL, 3600)
        self.assertEqual(alerts.PROCESS_JUDGEMENT_CACHE.ttl, 3600)


class TestJudgeDecision(unittest.TestCase):
    """#61: só a primeira palavra do veredito conta."""

    def test_first_word_only(self):
        self.assertTrue(alerts._is_yes("SIM"))
        self.assertTrue(alerts._is_yes("sim, é seguro."))
        self.assertTrue(alerts._is_yes("**SIM**"))
        self.assertFalse(alerts._is_yes("SIMPLESMENTE NÃO"))
        self.assertFalse(alerts._is_yes("NÃO, SIM SERIA ERRADO"))
        self.assertFalse(alerts._is_yes("ASSIM NÃO"))
        self.assertFalse(alerts._is_yes(""))
        self.assertFalse(alerts._is_yes(None))


if __name__ == "__main__":
    unittest.main()
