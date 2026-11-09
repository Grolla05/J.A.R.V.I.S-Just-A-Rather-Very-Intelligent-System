"""services.focus — Pomodoro + Não Perturbe, com relógio/timer/registro falsos."""
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

import core.state as state
from core.config import settings
from services import focus as focus_mod
from services.focus import FOCUS, IDLE, LONG_BREAK, SHORT_BREAK, FocusManager


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeTimer:
    def __init__(self, seconds, fn):
        self.seconds, self.fn, self.cancelled = seconds, fn, False

    def cancel(self):
        self.cancelled = True


class FakeToasts:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.calls = []

    def get(self):
        return self.enabled

    def set(self, enabled):
        self.calls.append(enabled)
        self.enabled = enabled
        return True


class FakeStore(dict):
    def set(self, key, value):
        self[key] = value


class FocusTestCase(unittest.TestCase):
    def setUp(self):
        state.dnd_active = False
        state.dnd_backlog.clear()
        self.clock = FakeClock()
        self.timers = []
        self.toasts = FakeToasts()
        self.store = FakeStore()
        self.said = []
        self.patches = [patch.object(settings, "POMODORO_FOCUS_MIN", 25),
                        patch.object(settings, "POMODORO_SHORT_BREAK_MIN", 5),
                        patch.object(settings, "POMODORO_LONG_BREAK_MIN", 15),
                        patch.object(settings, "POMODORO_CYCLES", 2)]
        for p in self.patches:
            p.start()
        self.fm = FocusManager(clock=self.clock, timer_factory=self._timer,
                               toasts=self.toasts, store=self.store, announce=self.said.append)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        state.dnd_active = False
        state.dnd_backlog.clear()

    def _timer(self, seconds, fn):
        t = FakeTimer(seconds, fn)
        self.timers.append(t)
        return t

    def _fire(self):
        """Avança o relógio até o último timer e dispara."""
        t = self.timers[-1]
        self.clock.now += t.seconds
        t.fn()


class TestPomodoro(FocusTestCase):
    def test_start_enters_focus_with_dnd(self):
        text = self.fm.start()
        self.assertIn("25 minutos", text)
        self.assertEqual(self.fm.phase, FOCUS)
        self.assertTrue(state.dnd_active)
        self.assertEqual(self.toasts.calls, [False])
        self.assertEqual(self.store["dnd_restore"], "1")
        self.assertEqual(self.timers[-1].seconds, 25 * 60)
        self.assertEqual(self.fm.badge(), "◷ FOCO 25m 1/2")

    def test_full_cycle_with_long_break(self):
        self.fm.start()
        self._fire()  # foco 1 -> pausa curta (DND desliga)
        self.assertEqual(self.fm.phase, SHORT_BREAK)
        self.assertFalse(state.dnd_active)
        self.assertTrue(self.toasts.enabled)
        self.assertEqual(self.fm.badge(), "☕ PAUSA 5m")
        self._fire()  # pausa -> foco 2
        self.assertEqual((self.fm.phase, self.fm.cycle), (FOCUS, 2))
        self.assertTrue(state.dnd_active)
        self._fire()  # foco 2 (último) -> pausa longa
        self.assertEqual(self.fm.phase, LONG_BREAK)
        self.assertEqual(self.timers[-1].seconds, 15 * 60)
        self._fire()  # fim
        self.assertEqual(self.fm.phase, IDLE)
        self.assertEqual(self.fm.badge(), "")
        self.assertEqual(len(self.said), 4)
        self.assertIn("concluído", self.said[-1])

    def test_custom_minutes_and_remaining(self):
        self.fm.start(focus_min=50)
        self.clock.now += 10 * 60 + 1
        self.assertEqual(self.fm.status()["remaining_min"], 40)

    def test_stop_restores_toasts(self):
        self.toasts.enabled = False  # usuário já tinha notificações desligadas
        self.fm.start()
        text = self.fm.stop()
        self.assertIn("encerrado", text)
        self.assertEqual(self.fm.phase, IDLE)
        self.assertFalse(self.toasts.enabled)  # volta como estava
        self.assertEqual(self.store["dnd_restore"], "")
        self.assertTrue(self.timers[0].cancelled)

    def test_skip_advances(self):
        self.assertFalse(self.fm.skip())
        self.fm.start()
        self.assertTrue(self.fm.skip())
        self.assertEqual(self.fm.phase, SHORT_BREAK)


class TestDnd(FocusTestCase):
    def test_manual_dnd_with_deadline(self):
        text = self.fm.dnd_on(30)
        self.assertIn("30 minutos", text)
        self.assertTrue(state.dnd_active)
        self.assertEqual(self.fm.badge(), "☾ DND 30m")
        self._fire()
        self.assertFalse(state.dnd_active)
        self.assertIn("desativado", self.said[-1])

    def test_backlog_is_summarized(self):
        self.fm.dnd_on()
        focus_mod.remember_alert("**CPU** em 95%")
        focus_mod.remember_alert("Disco quase cheio")
        text = self.fm.dnd_off()
        self.assertIn("2 alertas", text)
        self.assertIn("CPU em 95%", text)
        self.assertEqual(state.dnd_backlog, [])

    def test_backlog_is_capped(self):
        for i in range(focus_mod.BACKLOG_MAX + 5):
            focus_mod.remember_alert(f"alerta {i}")
        self.assertEqual(len(state.dnd_backlog), focus_mod.BACKLOG_MAX)
        self.assertEqual(state.dnd_backlog[-1], f"alerta {focus_mod.BACKLOG_MAX + 4}")

    def test_restore_after_crash(self):
        self.store["dnd_restore"] = "1"
        self.toasts.enabled = False  # o app caiu com o DND ligado
        self.assertTrue(self.fm.restore_after_crash())
        self.assertTrue(self.toasts.enabled)
        self.assertEqual(self.store["dnd_restore"], "")
        self.assertFalse(self.fm.restore_after_crash())  # nada pendente

    def test_toggle(self):
        self.fm.apply("dnd_toggle")
        self.assertTrue(state.dnd_active)
        self.fm.apply("dnd_toggle")
        self.assertFalse(state.dnd_active)


class TestAlertsDuringDnd(FocusTestCase):
    def test_alert_goes_to_backlog_silently(self):
        from core import alerts
        state.pending_critical_action = None  # outros testes deixam lixo aqui
        state.dnd_active = True
        with patch.object(alerts, "_announce") as announce:
            alerts.process_system_alert("Alerta: Disco CRÍTICO", is_proactive=True)
        announce.assert_not_called()
        self.assertIsNone(state.pending_critical_action)
        self.assertEqual(state.dnd_backlog, ["Alerta: Disco CRÍTICO"])


class TestFocusSkill(unittest.TestCase):
    def setUp(self):
        from skills.productivity import focus_mode
        self.skill = focus_mode

    def test_parse_minutes(self):
        p = self.skill.parse_minutes
        self.assertEqual(p("foco de 50 minutos"), 50)
        self.assertEqual(p("não perturbe por 2 horas"), 120)
        self.assertEqual(p("por meia hora"), 30)
        self.assertIsNone(p("inicia um pomodoro"))

    def test_parse_fast(self):
        f = self.skill.parse_fast
        self.assertEqual(f("inicia um pomodoro"), {"action": "start", "minutes": None})
        self.assertEqual(f("foco de 40 minutos")["minutes"], 40)
        self.assertEqual(f("modo não perturbe por 1 hora"), {"action": "dnd_on", "minutes": 60})
        self.assertEqual(f("desliga o não perturbe")["action"], "dnd_off")
        self.assertEqual(f("encerra o pomodoro")["action"], "stop")
        self.assertEqual(f("quanto falta?")["action"], "status")
        self.assertEqual(f("pula a pausa")["action"], "skip")
        self.assertIsNone(f("me concentra aí"))

    def test_llm_fallback(self):
        with patch.object(self.skill, "query_ollama", return_value='{"action": "start", "minutes": 45}'):
            self.assertEqual(self.skill.decide("me concentra aí"), {"action": "start", "minutes": 45})
        with patch.object(self.skill, "query_ollama", return_value='{"action": "voar"}'):
            self.assertIsNone(self.skill.decide("me concentra aí"))

    def test_run_dispatches_to_manager(self):
        class Manager:
            def apply(self, action, minutes):
                return f"{action}:{minutes}"
        self.assertEqual(self.skill.run({"action": "dnd_on", "minutes": 10}, Manager()), "dnd_on:10")


if __name__ == "__main__":
    unittest.main()
