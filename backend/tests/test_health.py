"""core.health — checagens de saúde (Ollama, Obsidian, mic, SQLite)."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import health
from core.config import settings


class TestChecks(unittest.TestCase):
    def test_ollama_ok_and_fail(self):
        with patch("core.ollama_server.is_ollama_running", return_value=True):
            self.assertEqual(health.check_ollama()[0], health.OK)
        with patch("core.ollama_server.is_ollama_running", return_value=False):
            self.assertEqual(health.check_ollama()[0], health.FAIL)

    def test_obsidian_unreachable_is_warn(self):
        with patch("core.obsidian.obsidian") as obs:
            obs.list_dir.return_value = None
            self.assertEqual(health.check_obsidian()[0], health.WARN)
            obs.list_dir.return_value = ["a.md", "b/"]
            status, detail = health.check_obsidian()
            self.assertEqual(status, health.OK)
            self.assertIn("2 itens", detail)

    def test_database_ok_and_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "x.db"
            real_connect = sqlite3.connect
            conns = []

            def spy(*args, **kwargs):
                conn = MagicMock(wraps=real_connect(*args, **kwargs))
                conns.append(conn)
                return conn

            with patch.object(settings, "DB_PATH", db_path), patch("core.health.sqlite3.connect", side_effect=spy):
                self.assertEqual(health.check_database()[0], health.OK)
            conns[0].close.assert_called_once()

    def test_database_error_is_fail(self):
        with patch("core.health.sqlite3.connect", side_effect=sqlite3.OperationalError("locked")):
            self.assertEqual(health.check_database()[0], health.FAIL)

    def test_microphone_index(self):
        fake_sr = MagicMock()
        fake_sr.Microphone.list_microphone_names.return_value = ["Mic A", "Mic B"]
        with patch.dict(sys.modules, {"speech_recognition": fake_sr}):
            with patch.object(settings, "MIC_INDEX", 1):
                self.assertEqual(health.check_microphone(), (health.OK, "mic 1: Mic B"))
            with patch.object(settings, "MIC_INDEX", 5):
                self.assertEqual(health.check_microphone()[0], health.FAIL)


class TestAggregation(unittest.TestCase):
    def test_exception_becomes_fail(self):
        def boom():
            raise RuntimeError("quebrou")
        result = health.run_all({"OLL": ("Ollama", boom), "DB": ("SQLite", lambda: (health.OK, "ok"))})
        self.assertEqual(result["OLL"][0], health.FAIL)
        self.assertEqual(result["DB"], (health.OK, "ok"))
        self.assertEqual(list(result), ["OLL", "DB"])

    def test_status_line_glyphs(self):
        result = {"OLL": ("ok", ""), "OBS": ("warn", ""), "MIC": ("fail", ""), "DB": ("ok", "")}
        self.assertEqual(health.status_line(result), "OLL● OBS◐ MIC○ DB●")
        self.assertEqual(health.status_line({}), "")

    def test_newly_failed_skips_first_reading(self):
        after = {"OLL": ("fail", "x"), "DB": ("ok", "")}
        self.assertEqual(health.newly_failed({}, after), [])
        self.assertEqual(health.newly_failed({"OLL": ("ok", ""), "DB": ("ok", "")}, after), ["OLL"])
        self.assertEqual(health.newly_failed({"OLL": ("fail", "")}, after), [])


if __name__ == "__main__":
    unittest.main()
