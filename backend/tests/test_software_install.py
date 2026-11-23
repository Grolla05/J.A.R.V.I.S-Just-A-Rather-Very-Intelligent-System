"""Skill SOFTWARE_INSTALL + services.software — busca no winget e instala/baixa só com confirmação."""
import importlib.util
import os
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.state as state  # noqa: E402
import services.brain as brain  # noqa: E402
from core import pending, winget  # noqa: E402
from services import software  # noqa: E402

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "automation",
                    "software_install.py")
RESULTS = [{"name": "7-Zip", "id": "7zip.7zip", "version": "26.06"},
           {"name": "NanaZip", "id": "M2Team.NanaZip", "version": "7.0"}]


def load():
    spec = importlib.util.spec_from_file_location("software_install_skill", PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InstallCase(unittest.TestCase):
    def setUp(self):
        self._saved = state.pending_critical_action
        state.pending_critical_action = None
        self._patches = [patch.object(winget, "available", return_value=True),
                         patch.object(winget, "search", return_value=list(RESULTS)),
                         patch.object(software, "_run_background", side_effect=lambda fn: fn())]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        state.pending_critical_action = self._saved


class TestService(InstallCase):
    def test_install_asks_then_installs(self):
        announce = MagicMock()
        with patch.object(winget, "install", return_value=(True, "ok")) as inst, \
             patch.object(software, "_announce", announce):
            text = software.request("7zip", action=software.INSTALL)
            inst.assert_not_called()
            self.assertIn("7zip.7zip", text)
            self.assertEqual(state.pending_critical_action["type"], "SOFTWARE_INSTALL")
            reply = brain._check_pending_action("sim")
        inst.assert_called_once_with("7zip.7zip")
        self.assertIn("Instalando", reply)
        self.assertIn("instalado", announce.call_args[0][0])

    def test_decline_installs_nothing(self):
        with patch.object(winget, "install") as inst:
            software.request("7zip")
            brain._check_pending_action("não")
        inst.assert_not_called()

    def test_download_uses_downloads_folder(self):
        with patch.object(winget, "download", return_value=(True, "ok")) as down, \
             patch.object(software, "_announce"):
            software.request("7zip", action=software.DOWNLOAD)
            brain._check_pending_action("sim")
        self.assertEqual(down.call_args[0][0], "7zip.7zip")
        self.assertTrue(str(down.call_args[0][1]).endswith("Downloads"))

    def test_no_match_lists_options(self):
        with patch.object(winget, "search", return_value=list(RESULTS)):
            text = software.request("compactador")
        self.assertIn("NanaZip", text)
        self.assertIsNone(state.pending_critical_action)

    def test_nothing_found_and_no_winget(self):
        with patch.object(winget, "search", return_value=[]):
            self.assertIn("Não encontrei", software.request("photoshop"))
        with patch.object(winget, "available", return_value=False):
            self.assertIn("winget", software.request("7zip"))

    def test_busy(self):
        pending.arm("X", "outra?", lambda: "x")
        self.assertEqual(software.request("7zip"), pending.BUSY_REPLY)

    def test_parse_command(self):
        self.assertEqual(software.parse_command("instala o 7-zip pra mim"), (software.INSTALL, "7-zip"))
        self.assertEqual(software.parse_command("baixa o instalador do vlc"), (software.DOWNLOAD, "vlc"))
        self.assertEqual(software.parse_command("baixe o discord"), (software.DOWNLOAD, "discord"))


class TestSkill(InstallCase):
    def test_skill_contract(self):
        skill = load()
        self.assertEqual(skill.INTENT, "SOFTWARE_INSTALL")
        with patch.object(software, "request", return_value="pergunta") as req:
            self.assertEqual(skill.execute("vlc", "instala o vlc"), "pergunta")
        req.assert_called_once_with("vlc", action=software.INSTALL)
        with patch.object(software, "request", return_value="pergunta") as req:
            skill.execute(None, "baixa o instalador do vlc")
        req.assert_called_once_with("vlc", action=software.DOWNLOAD)


if __name__ == "__main__":
    unittest.main()
