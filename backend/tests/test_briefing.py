"""core.briefing + core.weather — fontes isoladas, controle diário e fallback sem LLM."""
import datetime
import os
import tempfile
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


class TestCollectAndBuild(unittest.TestCase):
    def _patches(self, **overrides):
        values = dict(weather="22°C com céu limpo.",
                      computer={"cpu": "5%", "ram": "40%", "gpu": "12% · 50°C",
                                "net": "↓ 1.2 MB/s · ↑ 80.0 KB/s", "battery": None},
                      github="1 PR(s) seus abertos",
                      agenda="2 eventos hoje: 09:00 Daily · 14:00 Dentista",
                      traffic="Casa → trabalho: 34 min (+9 pelo trânsito, TomTom).")
        values.update(overrides)
        return [
            patch.object(weather, "get_weather_context", side_effect=_maybe_raise(values["weather"])),
            patch.object(briefing, "_computer", side_effect=_maybe_raise(values["computer"])),
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
        self.assertNotIn("files", data)
        self.assertNotIn("news", data)
        self.assertIn("Daily", data["agenda"])

    def test_markdown_sections_in_order_one_theme_per_block(self):
        md = briefing.to_markdown(self._collect())
        blocks = md.split("\n\n")
        self.assertTrue(blocks[0].startswith("**Bom dia, Felipe.**"))
        titles = [b.split(":**")[0] + ":**" for b in blocks[1:]]
        self.assertEqual(titles, ["**Clima:**", "**Computador:**", "**GitHub:**", "**Agenda:**", "**Trânsito:**"])
        self.assertIn("**Clima:**" + briefing.BR + "22°C com céu limpo.", md)
        self.assertIn(briefing.BR.join(["CPU → 5%", "RAM → 40%", "GPU → 12% · 50°C",
                                        "INTERNET → ↓ 1.2 MB/s · ↑ 80.0 KB/s"]), md)
        self.assertNotIn("BATERIA", md)
        self.assertNotIn("Arquivos", md)

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
        md = briefing.to_markdown(data)
        self.assertNotIn("Clima", md)
        self.assertNotIn("GitHub", md)
        self.assertIn("Computador", md)

    def test_news_section_one_line_per_source(self):
        news = [("G1", "Ibovespa despenca 3%"), ("BBC", "Earthquake hits Japan")]
        with patch.object(briefing, "_news", return_value=news):
            ps = self._patches()
            for p in ps:
                p.start()
            try:
                data = briefing.collect(include_news=True)
            finally:
                for p in reversed(ps):
                    p.stop()
        md = briefing.to_markdown(data)
        self.assertTrue(md.endswith("**Manchetes e últimas notícias:**\n\n"
                                    "- **G1:** Ibovespa despenca 3%\n- **BBC:** Earthquake hits Japan"))

    def test_build_appends_llm_closing_and_keeps_body(self):
        data = self._collect()
        body = briefing.to_markdown(data)
        with patch("core.llm.query_ollama", return_value="  Leve um guarda-chuva,\n Senhor.  ") as llm:
            self.assertEqual(briefing.build(data), body + "\n\nLeve um guarda-chuva, Senhor.")
        self.assertIn("CPU → 5%", llm.call_args[0][0][0]["content"])
        with patch("core.llm.query_ollama", return_value=None):
            self.assertEqual(briefing.build(data), body)
        with patch("core.llm.query_ollama", side_effect=RuntimeError("ollama off")):
            self.assertEqual(briefing.build(data), body)


class TestComputer(unittest.TestCase):
    def test_format_rate(self):
        self.assertEqual(briefing.format_rate(512), "512 B/s")
        self.assertEqual(briefing.format_rate(1536), "1.5 KB/s")
        self.assertEqual(briefing.format_rate(3 * 1024 ** 2), "3.0 MB/s")
        self.assertEqual(briefing.format_rate(-5), "0 B/s")

    def test_computer_reads_monitor(self):
        import core.state as state
        monitor = MagicMock()
        monitor.get_cpu_usage.return_value = 31.0
        monitor.get_ram_usage.return_value = {"percent": 85.4}
        monitor.get_gpu_info.return_value = {"name": "RTX", "load": 7.0, "temp": 48}
        monitor.get_battery_status.return_value = {"percent": 90, "plugged": True, "time_left": "x"}
        with patch.object(state, "sys_monitor", monitor), patch.object(briefing, "_net_rate", return_value="↓ 1 KB/s · ↑ 2 KB/s"):
            info = briefing._computer()
        self.assertEqual(info, {"cpu": "31.0%", "ram": "85.4%", "gpu": "7.0% · 48°C",
                                "net": "↓ 1 KB/s · ↑ 2 KB/s", "battery": "90% (na tomada)"})

    def test_no_gpu_no_battery(self):
        import core.state as state
        monitor = MagicMock()
        monitor.get_cpu_usage.return_value = 1
        monitor.get_ram_usage.return_value = {"percent": 2}
        monitor.get_gpu_info.return_value = {"name": "Integrada/N/A", "load": 0, "temp": 0}
        monitor.get_battery_status.return_value = {"percent": 100, "time_left": "Desktop"}
        with patch.object(state, "sys_monitor", monitor), patch.object(briefing, "_net_rate", side_effect=OSError("sem rede")):
            info = briefing._computer()
        self.assertIsNone(info["gpu"])
        self.assertIsNone(info["net"])
        self.assertIsNone(info["battery"])


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
