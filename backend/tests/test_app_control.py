"""Skill APP_CONTROL — nada de shell com texto do LLM, encerramento por nome exato,
processos protegidos e confirmação para alvos desconhecidos.

Cobre os Security Advisories GHSA-8j53 (injeção de shell) e GHSA-p7rm (fechar por
substring, sem confirmação). Sem psutil real, sem Ollama e sem abrir nada.
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
from core import pending, processes  # noqa: E402

_SKILL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "skills", "automation", "app_control.py")
_spec = importlib.util.spec_from_file_location("app_control", _SKILL_PATH)
app_control = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app_control)


class FakeProc:
    def __init__(self, pid, name, created=1000.0):
        self.info = {"pid": pid, "name": name}
        self._created = created

    def create_time(self):
        return self._created


PROCS = [FakeProc(10, "Spotify.exe"), FakeProc(11, "Spotify.exe"), FakeProc(20, "chrome.exe"),
         FakeProc(30, "Code.exe"), FakeProc(31, "vscode-helper.exe"), FakeProc(40, "explorer.exe"),
         FakeProc(50, "xpto.exe"), FakeProc(51, "XPTO.EXE")]


def _decision(action, target):
    return json.dumps({"action": action, "target": target})


class AppControlCase(unittest.TestCase):
    def setUp(self):
        self._saved = state.pending_critical_action
        state.pending_critical_action = None
        self.psutil = MagicMock()
        self.psutil.process_iter.side_effect = lambda attrs=None: iter(PROCS)
        self.terminate = MagicMock(return_value="ok")
        self._patches = [patch.object(app_control, "psutil", self.psutil),
                         patch.object(processes, "terminate_if_same", self.terminate),
                         patch.object(app_control, "focus_window", return_value=False)]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        state.pending_critical_action = self._saved

    def _run(self, action, target):
        with patch.object(app_control, "_ask_ollama_app_expert", return_value=_decision(action, target)):
            return app_control.execute(None, f"{action} {target}")


class TestFind(AppControlCase):
    def test_exact_name_not_substring(self):
        found = [p.info["pid"] for p in app_control.find_active_processes("code")]
        self.assertEqual(found, [30])                      # vscode-helper.exe não entra
        self.assertEqual([p.info["pid"] for p in app_control.find_active_processes("chrome.exe")], [20])

    def test_protected_processes_never_returned(self):
        self.assertEqual(app_control.find_active_processes("explorer"), [])
        with patch.object(processes.os, "getpid", return_value=50):   # o próprio JARVIS
            self.assertEqual([p.info["pid"] for p in app_control.find_active_processes("xpto")], [51])


class TestClose(AppControlCase):
    def test_known_app_closes_directly(self):
        reply = self._run("close", "spotify")
        self.assertIn("Encerrando 2 instâncias", reply)
        self.assertEqual([c.args[0] for c in self.terminate.call_args_list], [10, 11])
        self.assertIsNone(state.pending_critical_action)

    def test_unknown_app_asks_and_only_kills_the_snapshot(self):
        reply = self._run("close", "xpto")
        self.assertIn("Diga **sim**", reply)
        self.terminate.assert_not_called()
        action = state.pending_critical_action
        self.assertEqual(action["type"], "APP_CLOSE")
        self.assertEqual(brain.confirm_pending_action(True, pending_id=action["id"]),
                         "Encerrando 2 instâncias do xpto. Memória liberada.")
        self.assertEqual([c.args[:2] for c in self.terminate.call_args_list], [(50, "xpto.exe"), (51, "XPTO.EXE")])

    def test_short_target_is_refused(self):
        for target in ("s", "e.exe", ""):
            with self.subTest(target=target):
                reply = self._run("close", target)
                self.assertNotIn("Encerrando", reply)
        self.terminate.assert_not_called()

    def test_recycled_pid_counts_as_not_closed(self):
        self.terminate.return_value = "changed"
        self.assertIn("Nenhuma instância", self._run("close", "spotify"))

    def test_busy_when_another_confirmation_is_open(self):
        pending.arm("OUTRA", "Outra?", lambda: "x")
        self.assertEqual(self._run("close", "xpto"), pending.BUSY_REPLY)
        self.assertEqual(state.pending_critical_action["type"], "OUTRA")

    def test_close_now_skips_the_question(self):
        self.assertIn("Encerrando 2 instâncias", app_control.close_now("xpto"))
        self.assertIsNone(state.pending_critical_action)


class TestOpenNeverUsesShell(AppControlCase):
    def setUp(self):
        super().setUp()
        self.popen = MagicMock()
        self._patches += [patch.object(app_control.subprocess, "Popen", self.popen),
                          patch.object(app_control, "get_installed_apps", return_value={})]
        for p in self._patches[-2:]:
            p.start()

    def test_malicious_target_is_not_executed(self):
        for target in ("calc & del C:\\x", "notepad | whoami", "a; rm", "\"x\" && y", "..\\..\\evil"):
            with self.subTest(target=target), patch.object(app_control.shutil, "which", return_value="C:\\x.exe"):
                reply = self._run("open", target)
                self.assertIn("Busca negativa", reply)
        self.popen.assert_not_called()

    def test_simple_name_on_path_runs_without_shell(self):
        with patch.object(app_control.shutil, "which", return_value="C:\\Windows\\notepad.exe"):
            self._run("open", "notepad")
        self.popen.assert_called_once()
        args, kwargs = self.popen.call_args
        self.assertEqual(args[0], ["C:\\Windows\\notepad.exe"])
        self.assertFalse(kwargs.get("shell", False))

    def test_apps_folder_uses_argument_list(self):
        with patch.object(app_control, "get_installed_apps", return_value={"calculator": "Microsoft.Calc!App"}):
            self._run("open", "calculadora")
        args, kwargs = self.popen.call_args
        self.assertEqual(args[0], ["explorer.exe", "shell:AppsFolder\\Microsoft.Calc!App"])
        self.assertFalse(kwargs.get("shell", False))

    def test_no_shell_true_left_in_the_skill(self):
        with open(_SKILL_PATH, encoding="utf-8") as f:
            self.assertNotIn("shell=True", f.read())


if __name__ == "__main__":
    unittest.main()
