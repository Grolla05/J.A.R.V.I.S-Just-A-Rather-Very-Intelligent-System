"""TUI — execute_command_stream respeita o modo: CHAT nunca executa skill,
COPILOT executa. Também cobre a confirmação de ação crítica."""
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
        self.skill = MagicMock()
        self.skill.execute.return_value = "Spotify aberto."
        self._patches = [
            patch.dict(brain.manager.skills, {"APP_CONTROL": self.skill}, clear=True),
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

    def test_chat_mode_skips_skills(self):
        out, classify = self._run(brain.MODE_CHAT)
        self.assertEqual(out, "resposta do chat")
        self.skill.execute.assert_not_called()
        self.assertTrue(classify.call_args.kwargs["skip_skills"])

    def test_copilot_mode_executes_skill(self):
        out, classify = self._run(brain.MODE_COPILOT)
        self.assertEqual(out, "Spotify aberto.")
        self.skill.execute.assert_called_once_with("spotify", "abre o spotify")
        self.assertFalse(classify.call_args.kwargs["skip_skills"])

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
