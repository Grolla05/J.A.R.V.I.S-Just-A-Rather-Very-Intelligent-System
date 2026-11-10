"""Modo Apresentação: detecção, filtro de alertas, selo [SILENT], TTS mudo, mic fechado e skill."""
import sys
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.state as state
from core import window_utils
from services import notify_filter, presentation


def _reset():
    state.presentation_active = False
    state.auto_quiet = None
    state.dnd_active = False
    state.dnd_backlog.clear()


class TestDetection(unittest.TestCase):
    def test_looks_presenting(self):
        self.assertTrue(window_utils.looks_presenting("POWERPNT.EXE", True))
        self.assertTrue(window_utils.looks_presenting("AcroRd32.exe", True))
        self.assertFalse(window_utils.looks_presenting("chrome.exe", True))   # vídeo em tela cheia não
        self.assertFalse(window_utils.looks_presenting("POWERPNT.EXE", False))  # editando slides não
        self.assertFalse(window_utils.looks_presenting("", True))


class TestFilter(unittest.TestCase):
    def setUp(self):
        _reset()

    tearDown = setUp

    def _ctx(self, presenting=False, prefs=None):
        prefs = {"presentation_auto": True, **(prefs or {})}
        return notify_filter.context(meeting_fn=lambda: False, fullscreen_fn=lambda: False,
                                     pref=lambda k: prefs.get(k, False), presenting_fn=lambda: presenting)

    def test_auto_presentation_defers_and_badge(self):
        ctx = self._ctx(presenting=True)
        self.assertEqual(notify_filter.evaluate("CPU alta", ctx)[0], notify_filter.DEFER)
        self.assertEqual(notify_filter.evaluate("Disco C: CRÍTICO", ctx)[0], notify_filter.DELIVER)
        notify_filter.poll_auto_quiet(ctx)
        self.assertEqual(state.auto_quiet, "SILENT")
        self.assertEqual(notify_filter.badge(), "[SILENT]")
        self.assertTrue(presentation.is_silent())

    def test_pref_off_ignores_detection(self):
        ctx = self._ctx(presenting=True, prefs={"presentation_auto": False})
        self.assertEqual(notify_filter.evaluate("CPU alta", ctx)[0], notify_filter.DELIVER)

    def test_leaving_presentation_summarizes_backlog(self):
        notify_filter.poll_auto_quiet(self._ctx(presenting=True))
        state.dnd_backlog.append("CPU alta")
        summary = notify_filter.poll_auto_quiet(self._ctx(presenting=False))
        self.assertIn("Durante a apresentação", summary)
        self.assertEqual(notify_filter.badge(), "")
        self.assertFalse(presentation.is_silent())

    def test_manual_presentation(self):
        ctx = self._ctx()
        presentation.set_manual(True)
        self.assertEqual(notify_filter.evaluate("CPU alta", ctx)[0], notify_filter.DEFER)
        self.assertEqual(notify_filter.badge(), "[SILENT]")
        state.dnd_backlog.append("RAM alta")
        self.assertEqual(notify_filter.poll_auto_quiet(ctx), "")  # manual: resumo só ao desligar
        text = presentation.set_manual(False)
        self.assertIn("RAM alta", text)
        self.assertEqual(state.dnd_backlog, [])
        self.assertIn("já está desligado", presentation.set_manual(False))


class TestSpeakAndEar(unittest.TestCase):
    def setUp(self):
        _reset()

    tearDown = setUp

    def test_speak_is_muted_even_with_force(self):
        sys.modules.pop("services.speak", None)
        import services.speak as speak
        with patch.object(speak, "speak_online") as online, patch.object(speak, "speak_offline") as offline, \
             patch.object(speak, "_show"):
            state.presentation_active = True
            speak.speak("Bom dia", force=True)
            online.assert_not_called()
            offline.assert_not_called()
            state.presentation_active = False
            online.return_value = True
            speak.speak("Bom dia", force=True)
            online.assert_called_once()

    def test_ear_reports_silence(self):
        sys.modules.pop("services.listen", None)
        try:
            import services.listen as listen
        except Exception as e:  # speech_recognition ausente no ambiente de teste
            self.skipTest(f"listen indisponível: {e}")
        self.assertFalse(listen._silenced())
        state.presentation_active = True
        self.assertTrue(listen._silenced())


class TestSkill(unittest.TestCase):
    def setUp(self):
        _reset()

    tearDown = setUp

    def test_skill_toggles(self):
        from skills.productivity import presentation_mode as skill
        self.assertEqual(skill.INTENT, "PRESENTATION_MODE")
        self.assertIn("ligado", skill.execute(None, "liga o modo apresentação"))
        self.assertTrue(state.presentation_active)
        self.assertIn("(manual)", skill.execute("status", "o modo apresentação está ligado?"))
        self.assertIn("desligado", skill.execute(None, "acabou a apresentação, pode voltar"))
        self.assertFalse(state.presentation_active)

    def test_decide(self):
        from skills.productivity import presentation_mode as skill
        self.assertEqual(skill.decide(None, "vou apresentar agora"), "on")
        self.assertEqual(skill.decide("off", "modo apresentação"), "off")
        self.assertEqual(skill.decide(None, "sai do modo apresentação"), "off")


class TestSilentCommand(unittest.TestCase):
    def test_parse(self):
        from frontend.commands import COMMANDS, parse_silent_arg
        self.assertIn("silent", COMMANDS)
        self.assertEqual(parse_silent_arg(""), "toggle")
        self.assertEqual(parse_silent_arg("ON"), "on")
        self.assertEqual(parse_silent_arg("desliga"), "off")
        self.assertIsNone(parse_silent_arg("talvez"))


if __name__ == "__main__":
    unittest.main()
