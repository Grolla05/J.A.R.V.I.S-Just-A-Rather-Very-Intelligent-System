"""core.winget — parser do `winget search`, escolha do pacote e comandos sem shell."""
import unittest
from unittest.mock import MagicMock

from tests._stubs import install

install()

from core import winget  # noqa: E402

EN = (
    "Name                                  Id                                Version          Match\r\n"
    "--------------------------------------------------------------------------------------------------\r\n"
    "7-Zip                                 7zip.7zip                         26.06            Moniker: 7zip\r\n"
    "Advanced Archive Password Recovery Elcomsoft.ArchivePassword 4.66.266.6965 Tag: 7zip\r\n"
    "NanaZip                               M2Team.NanaZip                    7.0.1882.0       Tag: 7zip\r\n"
    "Python 3.11                           Python.Python.3.11                3.11.9\r\n"
)
PT = (
    "Nome            Id                 Versão   Correspondência\n"
    "-----------------------------------------------------------\n"
    "VLC media player VideoLAN.VLC      3.0.21   Moniker: vlc\n"
    "VLC Nightly     VideoLAN.VLC.Nightly 4.0    \n"
)


class TestParse(unittest.TestCase):
    def test_english_columns_and_overflow(self):
        items = winget.parse_search(EN)
        self.assertEqual(items[0], {"name": "7-Zip", "id": "7zip.7zip", "version": "26.06"})
        self.assertEqual(items[1]["id"], "Elcomsoft.ArchivePassword")
        self.assertEqual(items[1]["name"], "Advanced Archive Password Recovery")
        self.assertEqual(items[3], {"name": "Python 3.11", "id": "Python.Python.3.11", "version": "3.11.9"})

    def test_portuguese_header(self):
        items = winget.parse_search(PT)
        self.assertEqual(items[0]["id"], "VideoLAN.VLC")
        self.assertEqual(items[0]["name"], "VLC media player")
        self.assertEqual(items[1]["id"], "VideoLAN.VLC.Nightly")

    def test_no_results(self):
        self.assertEqual(winget.parse_search("No package found matching input criteria.\r\n"), [])
        self.assertEqual(winget.parse_search(""), [])


class TestChoose(unittest.TestCase):
    def test_best_match(self):
        items = winget.parse_search(EN)
        self.assertEqual(winget.best_match("7zip", items)["id"], "7zip.7zip")
        self.assertEqual(winget.best_match("7-zip", items)["id"], "7zip.7zip")
        self.assertEqual(winget.best_match("nanazip", items)["id"], "M2Team.NanaZip")
        self.assertIsNone(winget.best_match("photoshop", items))

    def test_valid_id(self):
        for good in ("7zip.7zip", "Python.Python.3.11", "Microsoft.VisualStudioCode", "Notepad++.Notepad++"):
            self.assertTrue(winget.valid_id(good), good)
        for bad in ("", "x", "a b", "7zip;calc", "--source", "&calc", "a" * 200):
            self.assertFalse(winget.valid_id(bad), bad)


class TestRun(unittest.TestCase):
    def test_search_command_without_shell(self):
        run = MagicMock(return_value=MagicMock(returncode=0, stdout=EN))
        items = winget.search("7zip", run=run)
        self.assertEqual(items[0]["id"], "7zip.7zip")
        args, kwargs = run.call_args
        self.assertEqual(args[0][:3], ["winget", "search", "7zip"])
        self.assertIn("--accept-source-agreements", args[0])
        self.assertNotIn("shell", kwargs)

    def test_install_and_download_commands(self):
        run = MagicMock(return_value=MagicMock(returncode=0, stdout="Successfully installed"))
        self.assertTrue(winget.install("7zip.7zip", run=run)[0])
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[:4], ["winget", "install", "--id", "7zip.7zip"])
        for flag in ("--exact", "--silent", "--accept-package-agreements", "--source"):
            self.assertIn(flag, cmd)
        ok, _ = winget.download("7zip.7zip", "C:/Users/u/Downloads", run=run)
        self.assertTrue(ok)
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[:2], ["winget", "download"])
        self.assertIn("C:/Users/u/Downloads", cmd)

    def test_invalid_id_never_runs(self):
        run = MagicMock()
        self.assertFalse(winget.install("7zip; calc", run=run)[0])
        self.assertFalse(winget.download("--x", "C:/d", run=run)[0])
        run.assert_not_called()

    def test_failure_and_missing_winget(self):
        run = MagicMock(return_value=MagicMock(returncode=1, stdout="Installer failed"))
        ok, text = winget.install("7zip.7zip", run=run)
        self.assertFalse(ok)
        self.assertIn("failed", text)
        missing = MagicMock(side_effect=FileNotFoundError())
        self.assertFalse(winget.available(run=missing))
        self.assertEqual(winget.search("7zip", run=missing), [])


if __name__ == "__main__":
    unittest.main()
