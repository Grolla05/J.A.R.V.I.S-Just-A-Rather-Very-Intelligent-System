"""core.briefing + core.weather — fontes isoladas, controle diário e fallback sem LLM."""
import datetime
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.database as database  # noqa: E402
from core import briefing, github_client, google_calendar, traffic, weather  # noqa: E402
from core.config import settings  # noqa: E402


class TestWeather(unittest.TestCase):
    def test_greeting_by_hour(self):
        at = lambda h: datetime.datetime(2026, 11, 8, h)  # noqa: E731
        self.assertIn("Madrugada", weather.get_time_greeting("F", at(3)))
        self.assertEqual(weather.get_time_greeting("F", at(9)), "Bom dia, F.")
        self.assertEqual(weather.get_time_greeting("F", at(14)), "Boa tarde, F.")
        self.assertEqual(weather.get_time_greeting("F", at(20)), "Boa noite, F.")

    def test_condition(self):
        self.assertEqual(weather._condition(0), "céu limpo")
        self.assertEqual(weather._condition(45), "nublado")
        self.assertEqual(weather._condition(61), "chuva leve")
        self.assertEqual(weather._condition(95), "chuva forte")
        self.assertEqual(weather._condition(None), "condição desconhecida")


class TestDailyControl(unittest.TestCase):
    def setUp(self):
        fd, self._path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._orig = settings.DB_PATH
        settings.DB_PATH = Path(self._path)
        self.db = database.DatabaseManager()

    def tearDown(self):
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass

    def test_runs_once_per_day(self):
        self.assertTrue(briefing.should_run_today(self.db))
        briefing.mark_ran(self.db)
        self.assertFalse(briefing.should_run_today(self.db))
        self.db.save_config(briefing.LAST_DATE_KEY, "2000-01-01")
        self.assertTrue(briefing.should_run_today(self.db))


class TestRecentFiles(unittest.TestCase):
    def test_finds_recent_skips_old_hidden_and_deep(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            old = time.time() - 3 * 86400
            (root / "novo.txt").write_text("x")
            (root / "velho.txt").write_text("x")
            os.utime(root / "velho.txt", (old, old))
            (root / ".oculto").write_text("x")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "lib.js").write_text("x")
            deep = root / "a" / "b" / "c" / "d"
            deep.mkdir(parents=True)
            (deep / "fundo.txt").write_text("x")
            (root / "a" / "perto.md").write_text("x")
            names = [p.name for p in briefing.recent_files([root], limit=10)]
        self.assertCountEqual(names, ["novo.txt", "perto.md"])

    def test_missing_dir_is_ignored(self):
        self.assertEqual(briefing.recent_files([Path("Z:/nao/existe")]), [])

    def test_default_dirs_from_settings(self):
        with patch.object(settings, "BRIEFING_DIRS", "C:/a; C:/b"):
            self.assertEqual(briefing.briefing_dirs(), [Path("C:/a"), Path("C:/b")])
        with patch.object(settings, "BRIEFING_DIRS", ""):
            self.assertEqual(briefing.briefing_dirs()[0].name, "Desktop")


class TestCollectAndBuild(unittest.TestCase):
    def _patches(self, **overrides):
        values = dict(weather="22°C com céu limpo.", system="CPU 5%, RAM 40%",
                      files=[Path("relatorio.docx")], github="1 PR(s) seus abertos",
                      agenda="2 eventos hoje: 09:00 Daily · 14:00 Dentista",
                      traffic="Casa → trabalho: 34 min (+9 pelo trânsito, TomTom).")
        values.update(overrides)
        return [
            patch.object(weather, "get_weather_context", side_effect=_maybe_raise(values["weather"])),
            patch.object(briefing, "_system_line", side_effect=_maybe_raise(values["system"])),
            patch.object(briefing, "recent_files", side_effect=_maybe_raise(values["files"])),
            patch.object(github_client, "summary", side_effect=_maybe_raise(values["github"])),
            patch.object(google_calendar, "summary", side_effect=_maybe_raise(values["agenda"])),
            patch.object(traffic, "commute_line", side_effect=_maybe_raise(values["traffic"])),
            patch.object(briefing, "_user_name", return_value="Felipe"),
        ]

    def _collect(self, **overrides):
        ps = self._patches(**overrides)
        for p in ps:
            p.start()
        try:
            return briefing.collect(now=datetime.datetime(2026, 11, 9, 8, 0))
        finally:
            for p in reversed(ps):
                p.stop()

    def test_collect_all_sources(self):
        data = self._collect()
        self.assertEqual(data["greeting"], "Bom dia, Felipe.")
        self.assertEqual(data["weekday"], "segunda-feira")
        self.assertEqual(data["files"], ["relatorio.docx"])
        self.assertNotIn("news", data)
        self.assertIn("Daily", data["agenda"])
        self.assertIn("**Agenda:** 2 eventos hoje", briefing.to_markdown(data))
        self.assertIn("**Trânsito:** Casa → trabalho: 34 min", briefing.to_markdown(data))

    def test_traffic_only_on_weekdays(self):
        ps = self._patches()
        for p in ps:
            p.start()
        try:
            data = briefing.collect(now=datetime.datetime(2026, 11, 14, 9, 0))  # sábado
        finally:
            for p in reversed(ps):
                p.stop()
        self.assertNotIn("traffic", data)

    def test_agenda_absent_when_not_connected(self):
        data = self._collect(agenda=None)
        self.assertIsNone(data["agenda"])
        self.assertNotIn("Agenda", briefing.to_markdown(data))

    def test_failing_source_is_isolated(self):
        data = self._collect(weather=RuntimeError("offline"), github=RuntimeError("401"))
        self.assertIsNone(data["weather"])
        self.assertIsNone(data["github"])
        self.assertEqual(data["system"], "CPU 5%, RAM 40%")
        md = briefing.to_markdown(data)
        self.assertNotIn("Clima", md)
        self.assertIn("Sistema", md)

    def test_news_only_when_asked(self):
        with patch.object(briefing, "_news", return_value=["Manchete A"]):
            ps = self._patches()
            for p in ps:
                p.start()
            try:
                data = briefing.collect(include_news=True)
            finally:
                for p in reversed(ps):
                    p.stop()
        self.assertEqual(data["news"], ["Manchete A"])
        self.assertIn("Manchete A", briefing.to_markdown(data))

    def test_build_uses_llm_and_falls_back(self):
        data = self._collect()
        with patch("core.llm.query_ollama", return_value="  Bom dia, Felipe. Tudo nominal.  ") as llm:
            self.assertEqual(briefing.build(data), "Bom dia, Felipe. Tudo nominal.")
        self.assertIn("relatorio.docx", llm.call_args[0][0][0]["content"])
        with patch("core.llm.query_ollama", return_value=None):
            fallback = briefing.build(data)
        self.assertIn("**Bom dia, Felipe.**", fallback)
        self.assertIn("relatorio.docx", fallback)

    def test_no_recent_files_message(self):
        md = briefing.to_markdown(self._collect(files=[]))
        self.assertIn("nada modificado", md)


class TestSkill(unittest.TestCase):
    def test_skill_generates_and_marks(self):
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "skills", "productivity", "daily_briefing.py")
        spec = importlib.util.spec_from_file_location("daily_briefing", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        prefs = MagicMock()
        prefs.get.return_value = False
        with patch.object(briefing, "generate", return_value="briefing!") as gen, \
             patch.object(briefing, "mark_ran") as mark, \
             patch("services.user_prefs.get", return_value=False):
            self.assertEqual(mod.execute(None, "bom dia"), "briefing!")
        gen.assert_called_once_with(include_news=False)
        mark.assert_called_once()


def _maybe_raise(value):
    def fn(*_a, **_k):
        if isinstance(value, Exception):
            raise value
        return value
    return fn


if __name__ == "__main__":
    unittest.main()
