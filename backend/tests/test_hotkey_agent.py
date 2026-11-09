"""Atalho global, presença TUI⇄agente, início com o Windows e decisão do Win+J."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import autostart, launcher, presence
from core.config import settings
from core.hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, parse_hotkey


class TestParseHotkey(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_hotkey("win+j"), (MOD_WIN, ord("J")))
        self.assertEqual(parse_hotkey("Ctrl + Alt + J"), (MOD_CONTROL | MOD_ALT, ord("J")))
        self.assertEqual(parse_hotkey("shift+win+f12"), (MOD_SHIFT | MOD_WIN, 0x7B))
        self.assertEqual(parse_hotkey("ctrl+5"), (MOD_CONTROL, ord("5")))

    def test_invalid(self):
        for spec in ("", "j", "win+", "hyper+j", "win+enter", "ctrl+f30"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                parse_hotkey(spec)


class TestPresence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(settings, "DIR_DATA", Path(self.tmp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_register_read_unregister(self):
        with patch.object(presence, "_pid_alive", return_value=True):
            presence.register_tui(1234, pid=42)
            self.assertEqual(presence.read_tui(), {"pid": 42, "hwnd": 1234})
            presence.unregister_tui(pid=7)  # outra TUI: não apaga
            self.assertTrue(presence.presence_path().exists())
            presence.unregister_tui(pid=42)
            self.assertIsNone(presence.read_tui())

    def test_dead_pid_is_cleaned(self):
        presence.presence_path().write_text(json.dumps({"pid": 99999, "hwnd": 1}), encoding="utf-8")
        with patch.object(presence, "_pid_alive", return_value=False):
            self.assertIsNone(presence.read_tui())
        self.assertFalse(presence.presence_path().exists())

    def test_garbage_file(self):
        presence.presence_path().write_text("{oops", encoding="utf-8")
        self.assertIsNone(presence.read_tui())


class FakeWinreg:
    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ = "HKCU", 2, 1

    def __init__(self):
        self.values = {}

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, *a):
        return self._Key()

    CreateKeyEx = OpenKey

    def QueryValueEx(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], 1

    def SetValueEx(self, _key, name, _r, _t, value):
        self.values[name] = value

    def DeleteValue(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class TestAutostart(unittest.TestCase):
    def test_enable_disable(self):
        reg = FakeWinreg()
        with patch.object(autostart, "_winreg", return_value=reg):
            self.assertFalse(autostart.is_enabled())
            self.assertTrue(autostart.enable())
            self.assertTrue(autostart.is_enabled())
            self.assertIn("agent.py", reg.values["JARVIS"])
            self.assertTrue(autostart.disable())
            self.assertFalse(autostart.is_enabled())
            self.assertTrue(autostart.disable())  # já desligado = ok

    def test_installed_uses_runtime_pythonw(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp)
            (app / "runtime").mkdir()
            (app / "runtime" / "pythonw.exe").write_text("")
            with patch.object(settings, "IS_INSTALLED", True), patch.object(settings, "DIR_ROOT", app / "app"):
                self.assertEqual(autostart.pythonw_path(), app / "runtime" / "pythonw.exe")


class TestLauncher(unittest.TestCase):
    def test_dev_command_with_wt(self):
        with patch.object(settings, "IS_INSTALLED", False):
            argv, cwd = launcher.tui_command(copilot=True, wt="wt.exe")
        self.assertEqual(argv[:5], ["wt.exe", "-w", "new", "--title", "JARVIS"])
        self.assertEqual(argv[-2:], ["main.py", "--copilot"])
        self.assertEqual(cwd, settings.DIR_BACKEND)

    def test_installed_command_without_wt(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp)
            (app / "jarvis.cmd").write_text("")
            with patch.object(settings, "IS_INSTALLED", True), patch.object(settings, "DIR_ROOT", app / "app"):
                argv, _cwd = launcher.tui_command(copilot=False, wt=None)
        self.assertEqual(argv, ["cmd.exe", "/c", str(app / "jarvis.cmd"), "--here"])


class TestAgentDecision(unittest.TestCase):
    def setUp(self):
        import agent
        self.handle = agent.handle_hotkey
        self.launch, self.focus, self.signal = MagicMock(), MagicMock(), MagicMock()

    def _run(self, tui, foreground=0):
        return self.handle(lambda: tui, self.launch, lambda: foreground, self.focus, self.signal)

    def test_no_tui_launches(self):
        self.assertEqual(self._run(None), "launch")
        self.launch.assert_called_once()
        self.signal.assert_not_called()

    def test_tui_in_background_is_summoned(self):
        self.assertEqual(self._run({"pid": 1, "hwnd": 50}, foreground=99), "summon")
        self.focus.assert_called_once_with(50)
        self.signal.assert_called_once_with("SUMMON")

    def test_tui_in_foreground_goes_back_to_chat(self):
        self.assertEqual(self._run({"pid": 1, "hwnd": 50}, foreground=50), "to_chat")
        self.focus.assert_not_called()
        self.signal.assert_called_once_with("TO_CHAT")


if __name__ == "__main__":
    unittest.main()
