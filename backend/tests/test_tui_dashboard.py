"""TUI — protocolo crítico, /status e /log (lógica pura)."""
import unittest

from tests._stubs import install

install()

from core.logger import dotted_module  # noqa: E402
from core.SystemInfo import critical_reasons  # noqa: E402
from frontend import sprites  # noqa: E402
from frontend.screens.log import clean_message, count_text, filter_records, log_title, timeline_steps  # noqa: E402
from frontend.screens.status import _uptime_text, human_bytes, human_rate, net_detail, num, window_label  # noqa: E402

PLUGGED = {"plugged": True, "percent": 100}


class TestCriticalReasons(unittest.TestCase):
    def test_normal_system_has_no_reason(self):
        disks = [{"mount": "C:\\", "free_gb": 20.9, "free_percent": 9.4}]
        self.assertEqual(critical_reasons(44, 69, 60, disks, PLUGGED), [])

    def test_disk_uses_free_gb_not_percent(self):
        self.assertEqual(critical_reasons(10, 10, 40, [{"mount": "C:\\", "free_gb": 8.2}], PLUGGED),
                         ["disco C:\\ com 8.2 GB livres"])

    def test_cpu_ram_gpu_and_battery(self):
        reasons = critical_reasons(95, 92, 90, [], {"plugged": False, "percent": 10})
        self.assertEqual(reasons, ["CPU 95%", "RAM 92%", "GPU 90°C", "bateria 10%"])

    def test_plugged_low_battery_is_fine(self):
        self.assertEqual(critical_reasons(1, 1, 1, [], {"plugged": True, "percent": 5}), [])


class TestDottedModule(unittest.TestCase):
    def test_backend_and_frontend_paths(self):
        self.assertEqual(dotted_module(r"D:\GitHub\J.A.R.V.I.S\backend\services\listen.py"), "services.listen")
        self.assertEqual(dotted_module("/x/J.A.R.V.I.S/backend/core/llm.py"), "core.llm")
        self.assertEqual(dotted_module(r"D:\GitHub\J.A.R.V.I.S\frontend\app.py"), "frontend.app")
        self.assertEqual(dotted_module("/usr/lib/python/thing.py", "thing"), "thing")


class TestSpacedBarChart(unittest.TestCase):
    def test_bars_have_gaps_and_are_right_aligned(self):
        lines, shown = sprites.spaced_bar_chart([100, 50], 7, 2)
        self.assertEqual(sprites.bar_slots(7), 4)
        self.assertEqual(shown, [None, None, 100, 50])
        self.assertEqual(lines, ["    █  ", "    █ █"])

    def test_keeps_only_what_fits(self):
        _, shown = sprites.spaced_bar_chart(list(range(10)), 5, 1)
        self.assertEqual(shown, [7, 8, 9])


class TestStatusFormatting(unittest.TestCase):
    def test_numbers_in_pt_br(self):
        self.assertEqual(num(22.7), "22,7")
        self.assertEqual(num(32.0), "32")
        self.assertEqual(human_rate(1.2 * 1024 * 1024), "1,2 MB/s")
        self.assertEqual(human_rate(92), "92 B/s")
        self.assertEqual(net_detail(1.1 * 1024 ** 2, 0.1 * 1024 ** 2), "↓ 1,1 · ↑ 0,1 MB/s")
        self.assertEqual(human_bytes(2.1 * 1024 ** 3), "2,1 GB")
        self.assertEqual(human_bytes(380 * 1024 ** 2), "380 MB")

    def test_dashboard_texts_and_processes(self):
        from frontend.screens.status import dashboard_texts, top_processes
        info = {"cores": 8, "freq_ghz": 3.6, "ram_used_gb": 22.7, "ram_total_gb": 32.0,
                "gpu_name": "NVIDIA GeForce RTX 3060", "vram_used_gb": 7.1, "vram_total_gb": 12.0,
                "top_memory": [("ollama.exe", 2.1 * 1024 ** 3), ("lixo", "x")]}
        self.assertEqual(dashboard_texts(info), {"CPU": "8 núcleos · 3,6 GHz", "RAM": "22,7 / 32 GB",
                                                 "GPU": "RTX 3060 · VRAM 7,1 / 12 GB"})
        self.assertEqual(top_processes(info), [("ollama.exe", 2.1 * 1024 ** 3)])
        self.assertEqual(dashboard_texts(object()), {})

    def test_window_and_uptime(self):
        self.assertEqual(window_label(20, 3.0), "últimos 60 s")
        self.assertEqual(window_label(40, 3.0), "últimos 2 min")
        self.assertEqual(_uptime_text("4:52:12"), "04:52:12")
        self.assertEqual(_uptime_text("1 day, 2:03:04"), "26:03:04")


class TestLogHelpers(unittest.TestCase):
    RECORDS = [
        {"time": "14:02:10.112", "level": "INFO", "module": "services.listen", "message": "wake word detectada"},
        {"time": "14:02:40.007", "level": "WARN", "module": "core.obsidian", "message": "vault lento"},
        {"time": "14:04:12.204", "level": "ERROR", "module": "skills.audio_control", "message": "pycaw falhou"},
    ]

    def test_clean_message_drops_emojis(self):
        self.assertEqual(clean_message("✅ Skills Carregadas"), "Skills Carregadas")
        self.assertEqual(clean_message("🧠 Modelo: gemma"), "Modelo: gemma")
        self.assertEqual(clean_message("✓ ok"), "✓ ok")

    def test_counts_in_pt_br(self):
        self.assertEqual(count_text(self.RECORDS), "3 linhas · 1 aviso · 1 erro")
        self.assertEqual(count_text(self.RECORDS * 500).split(" · ")[0], "1.500 linhas")

    def test_filter_by_level_and_query(self):
        self.assertEqual(len(filter_records(self.RECORDS, "TODOS", "vault")), 1)
        self.assertEqual(len(filter_records(self.RECORDS, "TODOS", "SKILLS.audio")), 1)
        self.assertEqual(filter_records(self.RECORDS, "ERROR")[0]["module"], "skills.audio_control")

    def test_title_and_timeline(self):
        self.assertEqual(log_title(None), "Atividade do J.A.R.V.I.S")
        turn = {"voice": True, "intent": "APP_CONTROL", "status": "ok", "result": "✅ Spotify aberto",
                "command": "abre o spotify"}
        self.assertEqual(timeline_steps(turn)[-2:], [("✓ SPOTIFY ABERTO", "ok"), ("FALA", "speech")])


if __name__ == "__main__":
    unittest.main()
