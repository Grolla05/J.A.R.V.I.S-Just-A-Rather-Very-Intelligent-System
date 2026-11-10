"""services.notify_filter + core.alerts — prioridade × contexto, backlog e silêncio automático."""
import sys
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

sys.modules.setdefault("services.listen", MagicMock())
sys.modules.setdefault("services.speak", MagicMock())

import core.alerts as alerts  # noqa: E402
import core.state as state  # noqa: E402
import services.notify_filter as nf  # noqa: E402
from core.window_utils import covers_monitor, looks_fullscreen  # noqa: E402

QUIET = {"dnd": False, "meeting": False, "fullscreen": False}


class _StateCase(unittest.TestCase):
    def setUp(self):
        self._saved = (state.dnd_active, list(state.dnd_backlog), state.auto_quiet)
        state.dnd_active, state.auto_quiet = False, None
        state.dnd_backlog.clear()

    def tearDown(self):
        state.dnd_active, backlog, state.auto_quiet = self._saved
        state.dnd_backlog[:] = backlog


class TestPriority(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(nf.priority("[SISTEMA CRÍTICO] Disco C:\\ CRÍTICO (1.2 GB livres)"), nf.CRITICAL)
        self.assertEqual(nf.priority("[SISTEMA CRÍTICO] Bateria crítica: 8%"), nf.CRITICAL)
        self.assertEqual(nf.priority("[SISTEMA CRÍTICO] GPU superaquecendo a 92°C"), nf.CRITICAL)
        self.assertEqual(nf.priority("[SISTEMA CRÍTICO] Disco D:\\ com pouco espaço (9 GB livres)"), nf.HIGH)
        # o prefixo "[SISTEMA CRÍTICO]" vem em todo alerta: não pode virar critical sozinho
        self.assertEqual(nf.priority("[SISTEMA CRÍTICO] RAM crítica: 95% (Consumo: chrome.exe (40%))"), nf.NORMAL)

    def test_mixed_message_takes_highest(self):
        self.assertEqual(nf.priority("Processador em 99%. Bateria crítica: 5%"), nf.CRITICAL)


class TestDecide(_StateCase):
    def test_matrix(self):
        for ctx_key in ("dnd", "meeting", "fullscreen"):
            ctx = {**QUIET, ctx_key: True}
            self.assertEqual(nf.decide(nf.CRITICAL, ctx), nf.DELIVER, ctx_key)
            self.assertEqual(nf.decide(nf.HIGH, ctx), nf.DEFER, ctx_key)
            self.assertEqual(nf.decide(nf.NORMAL, ctx), nf.DEFER, ctx_key)
        for prio in (nf.CRITICAL, nf.HIGH, nf.NORMAL):
            self.assertEqual(nf.decide(prio, QUIET), nf.DELIVER)

    def test_context_respects_prefs(self):
        prefs = {"dnd_auto_meeting": False, "dnd_auto_fullscreen": True}
        ctx = nf.context(meeting_fn=lambda: True, fullscreen_fn=lambda: True, pref=prefs.get)
        self.assertEqual(ctx, {"dnd": False, "meeting": False, "fullscreen": True})
        state.dnd_active = True
        self.assertTrue(nf.context(lambda: False, lambda: False, prefs.get)["dnd"])

    def test_reason_order(self):
        self.assertEqual(nf.quiet_reason({"dnd": True, "meeting": True, "fullscreen": False}), "DND")
        self.assertEqual(nf.quiet_reason({**QUIET, "fullscreen": True}), "TELA CHEIA")
        self.assertIsNone(nf.quiet_reason(QUIET))


class TestAutoQuiet(_StateCase):
    def test_enters_and_summarises_when_leaving(self):
        self.assertEqual(nf.poll_auto_quiet({**QUIET, "meeting": True}), "")
        self.assertEqual(state.auto_quiet, "REUNIÃO")
        self.assertEqual(nf.badge(), "☾ REUNIÃO")
        state.dnd_backlog.append("RAM crítica: 95%")
        summary = nf.poll_auto_quiet(QUIET)
        self.assertIn("modo reunião", summary)
        self.assertIn("RAM crítica", summary)
        self.assertEqual(state.dnd_backlog, [])
        self.assertIsNone(state.auto_quiet)
        self.assertEqual(nf.badge(), "")

    def test_manual_dnd_owns_the_backlog(self):
        nf.poll_auto_quiet({**QUIET, "fullscreen": True})
        state.dnd_active = True
        state.dnd_backlog.append("x")
        self.assertEqual(nf.poll_auto_quiet({**QUIET, "dnd": True}), "")
        self.assertEqual(state.dnd_backlog, ["x"])  # o FocusManager resume quando o DND sair


class TestAlertsIntegration(_StateCase):
    def _run(self, message, ctx):
        with patch.object(nf, "context", return_value=ctx), \
             patch.object(alerts, "_announce") as announce, \
             patch.object(alerts, "query_ollama", return_value="NÃO"), \
             patch.object(alerts, "load_prompt", return_value="p"):
            alerts.process_system_alert(message, is_proactive=True)
        return announce

    def test_normal_alert_deferred_in_meeting(self):
        announce = self._run("[SISTEMA CRÍTICO] RAM crítica: 95% (Consumo: chrome.exe (40%))",
                             {**QUIET, "meeting": True})
        announce.assert_not_called()
        self.assertEqual(len(state.dnd_backlog), 1)

    def test_critical_disk_passes_in_fullscreen(self):
        announce = self._run("[SISTEMA CRÍTICO] Disco C:\\ CRÍTICO (1.0 GB livres)", {**QUIET, "fullscreen": True})
        announce.assert_called_once()
        self.assertEqual(state.dnd_backlog, [])


class TestFullscreenGeometry(unittest.TestCase):
    def test_covers_monitor(self):
        self.assertTrue(covers_monitor((0, 0, 1920, 1080), (0, 0, 1920, 1080)))
        self.assertTrue(covers_monitor((-8, -8, 1928, 1088), (0, 0, 1920, 1080)))  # borda de janela
        self.assertFalse(covers_monitor((0, 0, 1920, 1040), (0, 0, 1920, 1080)))  # maximizada com barra
        self.assertFalse(covers_monitor((1920, 0, 3840, 1080), (0, 0, 1920, 1080)))

    def test_maximized_window_is_not_fullscreen(self):
        monitor = (1920, 0, 3840, 1080)
        self.assertFalse(looks_fullscreen((1912, -8, 3848, 1088), monitor, zoomed=True, caption=True))
        self.assertTrue(looks_fullscreen((1920, 0, 3840, 1080), monitor, zoomed=False, caption=False))  # F11/jogo


if __name__ == "__main__":
    unittest.main()
