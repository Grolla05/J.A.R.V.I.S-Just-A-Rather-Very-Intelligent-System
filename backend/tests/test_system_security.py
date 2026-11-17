"""Skill SYSTEM_SECURITY — desligar sempre pede confirmação e não apaga nada.

Cobre o Security Advisory GHSA-ph22. Nada é desligado de verdade: subprocess
e ctypes são substituídos por mocks.
"""
import importlib.util
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.state as state  # noqa: E402
import services.brain as brain  # noqa: E402
from core import pending  # noqa: E402

_SKILL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "skills", "system", "system_security.py")
_spec = importlib.util.spec_from_file_location("system_security", _SKILL_PATH)
security = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(security)


class SecurityCase(unittest.TestCase):
    def setUp(self):
        self._saved = state.pending_critical_action
        state.pending_critical_action = None
        self.run = MagicMock()
        self.ctypes = MagicMock()
        self._patches = [patch.object(security.subprocess, "run", self.run),
                         patch.object(security, "ctypes", self.ctypes)]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        state.pending_critical_action = self._saved

    def _execute(self, llm_reply, command="desligar o computador"):
        with patch.object(security, "_ask_ollama_security", return_value=llm_reply):
            return security.execute(None, command)


class TestPowerDown(SecurityCase):
    def test_llm_confirmed_true_does_not_shut_down(self):
        reply = self._execute(json.dumps({"action": "power_down", "confirmed": True}))
        self.assertIn("Diga **sim**", reply)
        self.run.assert_not_called()
        self.assertEqual(state.pending_critical_action["type"], "POWER_DOWN")

    def test_confirmation_runs_shutdown_as_argument_list(self):
        self._execute(json.dumps({"action": "power_down"}))
        action_id = state.pending_critical_action["id"]
        reply = brain.confirm_pending_action(True, pending_id=action_id)
        self.assertIn("desenergização", reply)
        cmd = self.run.call_args.args[0]
        self.assertEqual(cmd[:4], ["shutdown", "/s", "/t", "15"])
        self.assertFalse(self.run.call_args.kwargs.get("shell", False))

    def test_decline_does_nothing(self):
        self._execute(json.dumps({"action": "power_down"}))
        self.assertIsNone(brain._check_pending_action("não"))
        self.run.assert_not_called()

    def test_never_touches_recycle_bin_or_temp(self):
        self._execute(json.dumps({"action": "power_down"}))
        brain.confirm_pending_action(True)
        self.ctypes.windll.shell32.SHEmptyRecycleBinW.assert_not_called()
        self.assertFalse(hasattr(security, "_clean_temp_files"))
        self.assertFalse(hasattr(security, "_empty_recycle_bin"))

    def test_busy_when_another_confirmation_is_open(self):
        pending.arm("OUTRA", "Outra?", lambda: "x")
        self.assertEqual(self._execute(json.dumps({"action": "power_down"})), pending.BUSY_REPLY)


class TestFallback(SecurityCase):
    def test_llm_down_shutdown_word_still_asks(self):
        reply = self._execute(None, "desliga o pc")
        self.assertIn("Diga **sim**", reply)
        self.run.assert_not_called()

    def test_llm_down_unknown_command_does_not_lock(self):
        reply = self._execute(None, "faz alguma coisa aí")
        self.assertIn("Não compreendi", reply)
        self.ctypes.windll.user32.LockWorkStation.assert_not_called()

    def test_unknown_action_from_llm(self):
        self.assertIn("Não compreendi", self._execute(json.dumps({"action": "formatar"})))


if __name__ == "__main__":
    unittest.main()
