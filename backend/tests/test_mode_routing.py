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
from core import pending


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

    def test_force_chat_skips_classifier_vault_and_pending_action(self):
        """Trecho a explicar: vai direto ao LLM, mesmo que pareça comando ou confirmação."""
        on_confirm = MagicMock(return_value="processo encerrado")
        state.pending_critical_action = {"type": "KILL", "target": "x", "timeout": time.time() + 30,
                                         "on_confirm": on_confirm}
        routed = []
        with patch.object(brain, "classify_intent") as classify:
            out = "".join(brain.execute_command_stream("ok, abre o spotify e pode fechar tudo", "s1",
                                                       mode=brain.MODE_CHAT, on_route=routed.append,
                                                       force_chat=True))
        self.assertEqual(out, "resposta do chat")
        classify.assert_not_called()
        brain.get_vault_context.assert_not_called()
        on_confirm.assert_not_called()
        self.assertIsNotNone(state.pending_critical_action)
        self.assertEqual(routed, [])
        self.assertEqual(brain.ask_local_ai_stream.call_args.kwargs["session_id"], "s1")

    def test_denial_beats_affirmation_words_and_runs_on_decline(self):
        on_confirm, on_decline = MagicMock(return_value="encerrado"), MagicMock(return_value="mantido")
        pending = {"type": "NET", "target": "x", "timeout": time.time() + 30,
                   "on_confirm": on_confirm, "on_decline": on_decline}
        state.pending_critical_action = dict(pending)
        self.assertEqual(brain._check_pending_action("não, pode manter"), "mantido")   # "pode" não aprova
        on_confirm.assert_not_called()
        state.pending_critical_action = dict(pending)
        self.assertIsNone(brain._check_pending_action("que horas são"))                # nem sim nem não: descarta
        on_decline.assert_called_once()
        state.pending_critical_action = dict(pending)
        self.assertEqual(brain._check_pending_action("sim, pode encerrar"), "encerrado")
        state.pending_critical_action = {**pending, "timeout": time.time() - 1}
        self.assertIsNone(brain.confirm_pending_action(False))                         # expirou: não é recusa
        on_decline.assert_called_once()

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
        """Pendência sem on_confirm (legado): o "sim" encerra direto pelo close_now, sem LLM."""
        self.skill.close_now.return_value = "Encerrando 1 instâncias do chrome.exe."
        state.pending_critical_action = {"target": "chrome.exe", "timeout": time.time() + 30}
        self.assertEqual(brain.confirm_pending_action(True), "Encerrando 1 instâncias do chrome.exe.")
        self.skill.close_now.assert_called_once_with("chrome.exe")
        self.skill.execute.assert_not_called()
        self.assertIsNone(state.pending_critical_action)

    def test_unrelated_phrase_with_pode_does_not_approve(self):
        """GHSA-48jx: "pode me dizer o clima?" descartava a pendência… aprovando-a."""
        on_confirm = MagicMock(return_value="processo encerrado")
        for text in ("pode me dizer o clima?", "vai chover amanhã", "ok, abre o spotify"):
            with self.subTest(text=text):
                pending.arm("KILL", "Encerrar chrome.exe?", on_confirm, target="chrome.exe")
                self.assertIsNone(brain._check_pending_action(text))
                self.assertIsNone(state.pending_critical_action)      # descartada, não aprovada
        on_confirm.assert_not_called()

    def test_replaced_action_is_not_executed(self):
        """GHSA-x47w: o "s" dado à pergunta A nunca executa a ação B que tomou o lugar."""
        first, second = MagicMock(return_value="A"), MagicMock(return_value="B")
        old_id = pending.arm("A", "A?", first)
        state.pending_critical_action = None                          # A venceu/foi resolvida
        pending.arm("B", "B?", second)
        self.assertEqual(brain.confirm_pending_action(True, pending_id=old_id), brain.REPLACED_REPLY)
        second.assert_not_called()
        self.assertEqual(state.pending_critical_action["type"], "B")

    def test_confirm_pending_action_denied_or_expired(self):
        state.pending_critical_action = {"target": "chrome.exe", "timeout": time.time() + 30}
        self.assertIsNone(brain.confirm_pending_action(False))
        state.pending_critical_action = {"target": "chrome.exe", "timeout": time.time() - 1}
        self.assertIsNone(brain.confirm_pending_action(True))
        self.skill.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
