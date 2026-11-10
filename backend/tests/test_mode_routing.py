"""TUI — execute_command_stream respeita o modo: CHAT só executa skills fora de
automation/system, COPILOT executa todas. Também cobre a confirmação de ação crítica."""
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

# Sentidos nunca devem ser tocados aqui (hardware)
sys.modules["services.listen"] = MagicMock()
sys.modules["services.speak"] = MagicMock()

import core.state as state
import services.brain as brain


class TestModeRouting(unittest.TestCase):
    def setUp(self):
        self.skill = MagicMock(CATEGORY="automation")
        self.skill.execute.return_value = "Spotify aberto."
        self.calendar = MagicMock(CATEGORY="productivity")
        self.calendar.execute.return_value = "Amanhã: reunião às 10h."
        self.cleanup = MagicMock(CATEGORY="system")
        self.cleanup.execute.return_value = "Limpo."
        self.web = MagicMock(CATEGORY="web")
        self.web.execute.return_value = "Resultados."
        skills = {"APP_CONTROL": self.skill, "CALENDAR": self.calendar,
                  "SYSTEM_CLEANUP": self.cleanup, "WEB_SEARCH": self.web}
        self._patches = [
            patch.dict(brain.manager.skills, skills, clear=True),
            patch.object(brain, "is_skill_enabled", return_value=True),
            patch.object(brain, "get_vault_context", return_value=("", "")),
            patch.object(brain, "ask_local_ai_stream", side_effect=lambda *a, **k: iter(["resposta ", "do chat"])),
        ]
        for p in self._patches:
            p.start()
        state.pending_critical_action = None

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        state.pending_critical_action = None

    def _run(self, mode, intent="APP_CONTROL"):
        decision = {"intent": intent, "entity": "spotify", "confidence": 0.9}
        with patch.object(brain, "classify_intent", return_value=decision) as classify:
            out = "".join(brain.execute_command_stream("abre o spotify", "s1", mode=mode))
        return out, classify

    def test_chat_mode_skips_automation_skills(self):
        out, classify = self._run(brain.MODE_CHAT)
        self.assertEqual(out, "resposta do chat")
        self.skill.execute.assert_not_called()
        self.assertEqual(classify.call_args.kwargs["exclude_categories"], ("automation", "system"))

    def test_chat_mode_skips_system_skills(self):
        out, _ = self._run(brain.MODE_CHAT, intent="SYSTEM_CLEANUP")
        self.assertEqual(out, "resposta do chat")
        self.cleanup.execute.assert_not_called()

    def test_chat_mode_runs_productivity_and_web_skills(self):
        routed = []
        decision = {"intent": "CALENDAR", "entity": "amanhã", "confidence": 0.9}
        with patch.object(brain, "classify_intent", return_value=decision):
            out = "".join(brain.execute_command_stream("o que tenho amanhã?", "s1", mode=brain.MODE_CHAT,
                                                       on_route=routed.append))
        self.assertEqual(out, "Amanhã: reunião às 10h.")
        self.assertEqual(routed, ["CALENDAR"])
        out, _ = self._run(brain.MODE_CHAT, intent="WEB_SEARCH")
        self.assertEqual(out, "Resultados.")

    def test_chat_mode_resolves_pending_action(self):
        on_confirm = MagicMock(return_value="Issue criada.")
        state.pending_critical_action = {"type": "github", "on_confirm": on_confirm, "timeout": time.time() + 30}
        out = "".join(brain.execute_command_stream("sim", "s1", mode=brain.MODE_CHAT))
        self.assertEqual(out, "Issue criada.")

    def test_copilot_mode_executes_skill(self):
        out, classify = self._run(brain.MODE_COPILOT)
        self.assertEqual(out, "Spotify aberto.")
        self.skill.execute.assert_called_once_with("spotify", "abre o spotify")
        self.assertEqual(classify.call_args.kwargs["exclude_categories"], ())

    def test_mode_is_forwarded_to_chat_prompt(self):
        with patch.object(brain, "classify_intent", return_value={"intent": "CHAT"}):
            list(brain.execute_command_stream("oi", "s1", mode=brain.MODE_COPILOT))
        self.assertEqual(brain.ask_local_ai_stream.call_args.kwargs["mode"], "copilot")

    def test_confirm_pending_action_approved(self):
        state.pending_critical_action = {"target": "chrome.exe", "timeout": time.time() + 30}
        self.assertEqual(brain.confirm_pending_action(True), "Spotify aberto.")
        self.skill.execute.assert_called_once_with("chrome.exe", "fechar chrome.exe")
        self.assertIsNone(state.pending_critical_action)

    def test_confirm_pending_action_denied_or_expired(self):
        state.pending_critical_action = {"target": "chrome.exe", "timeout": time.time() + 30}
        self.assertIsNone(brain.confirm_pending_action(False))
        state.pending_critical_action = {"target": "chrome.exe", "timeout": time.time() - 1}
        self.assertIsNone(brain.confirm_pending_action(True))
        self.skill.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
