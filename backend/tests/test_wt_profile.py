"""core.wt_profile — fragment do Windows Terminal com a logo do JARVIS."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import wt_profile
from core.config import settings


class TestWtProfile(unittest.TestCase):
    def test_fragment_path(self):
        path = wt_profile.fragment_path("C:/Users/x/AppData/Local")
        self.assertEqual(path.parts[-4:], ("Windows Terminal", "Fragments", "JARVIS", "jarvis.json"))
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(wt_profile.fragment_path())

    def test_icon_path_dev_and_installed(self):
        with patch.object(settings, "IS_INSTALLED", False):
            self.assertEqual(wt_profile.icon_path(), settings.DIR_ROOT / "installer" / "assets" / "jarvis.ico")
        with patch.object(settings, "IS_INSTALLED", True), patch.object(settings, "DIR_ROOT", Path("C:/J/app")):
            self.assertEqual(wt_profile.icon_path(), Path("C:/J/jarvis.ico"))

    def test_build_fragment(self):
        frag = wt_profile.build_fragment(Path("C:/J/jarvis.ico"), Path("C:/J/app/backend"))
        prof = frag["profiles"][0]
        self.assertEqual(prof["name"], "JARVIS")
        self.assertEqual(prof["guid"], wt_profile.PROFILE_GUID)
        self.assertTrue(prof["icon"].endswith("jarvis.ico"))

    def test_ensure_profile_writes_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "jarvis.ico"
            icon.write_bytes(b"ico")
            with patch.object(wt_profile, "icon_path", return_value=icon):
                self.assertTrue(wt_profile.ensure_profile(tmp))
                path = wt_profile.fragment_path(tmp)
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["profiles"][0]["icon"], str(icon))
                mtime = path.stat().st_mtime_ns
                with patch.object(Path, "write_text") as write:
                    self.assertTrue(wt_profile.ensure_profile(tmp))
                write.assert_not_called()
                self.assertEqual(path.stat().st_mtime_ns, mtime)

    def test_ensure_profile_without_icon(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(wt_profile, "icon_path", return_value=Path(tmp) / "nao_existe.ico"):
                self.assertFalse(wt_profile.ensure_profile(tmp))
            self.assertFalse(wt_profile.fragment_path(tmp).exists())


if __name__ == "__main__":
    unittest.main()
