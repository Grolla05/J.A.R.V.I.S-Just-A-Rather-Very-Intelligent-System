"""core/power.py: estimativa, nvidia-smi, integração em kWh e textos."""
import os
import sys
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import power  # noqa: E402


def _reset_gpu_cache():
    power._gpu_cache.update(at=0.0, value=None, missing=False)


def _meter(initial=None):
    saved = []
    return power.PowerMeter(load=lambda: dict(initial or {}), save=saved.append), saved


class TestEstimate(unittest.TestCase):
    def test_idle_and_full_load(self):
        idle = power.estimate(0, None, tdp=100, base=40, eff=1.0)
        self.assertEqual(idle["cpu"], 15.0)
        self.assertEqual(idle["total"], 55.0)
        self.assertFalse(idle["gpu_real"])
        full = power.estimate(100, 50, tdp=100, base=40, eff=1.0)
        self.assertEqual(full["total"], 190.0)
        self.assertTrue(full["gpu_real"])

    def test_psu_efficiency_and_bad_values(self):
        self.assertEqual(power.estimate(0, 0, tdp=0, base=85, eff=0.85)["total"], 100.0)
        self.assertEqual(power.estimate(250, 0, tdp=100, base=0, eff=0)["cpu"], 100.0)  # carga e eff saneadas

    def test_cost_and_texts(self):
        self.assertEqual(power.cost(2, tariff=0.9), 1.8)
        self.assertEqual(power.brl(1.8), "R$ 1,80")
        self.assertEqual(power.kwh_text(0.425), "0,42 kWh")


class TestGpuWatts(unittest.TestCase):
    def setUp(self):
        _reset_gpu_cache()

    def tearDown(self):
        _reset_gpu_cache()

    def test_parse(self):
        self.assertEqual(power.parse_power_draw("17.52\n"), 17.5)
        self.assertEqual(power.parse_power_draw("10.0\n[N/A]\n5.5"), 15.5)
        self.assertIsNone(power.parse_power_draw("[N/A]"))
        self.assertIsNone(power.parse_power_draw(""))

    def test_reads_without_shell_and_caches(self):
        run = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="20.1\n"))
        clock = iter([100.0, 101.0, 104.0])
        kw = dict(run=run, which=lambda _: "nvidia-smi.exe", now=lambda: next(clock))
        self.assertEqual(power.gpu_watts(**kw), 20.1)
        self.assertEqual(power.gpu_watts(**kw), 20.1)  # dentro do cache
        self.assertEqual(run.call_count, 1)
        power.gpu_watts(**kw)
        self.assertEqual(run.call_count, 2)
        self.assertIsInstance(run.call_args.args[0], list)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_missing_nvidia_smi_is_none_forever(self):
        which = MagicMock(return_value=None)
        self.assertIsNone(power.gpu_watts(which=which, now=lambda: 0.0))
        self.assertIsNone(power.gpu_watts(which=which, now=lambda: 99.0))
        self.assertEqual(which.call_count, 1)

    def test_error_is_none(self):
        run = MagicMock(side_effect=OSError("boom"))
        self.assertIsNone(power.gpu_watts(run=run, which=lambda _: "x", now=lambda: 50.0))


class TestMeter(unittest.TestCase):
    def test_integrates_watts_into_kwh(self):
        meter, _ = _meter()
        t0 = datetime(2026, 11, 24, 10, 0, 0)
        meter.add({"total": 3600.0}, t0)               # 1ª amostra só marca o tempo
        meter.add({"total": 3600.0}, t0 + timedelta(seconds=30))
        self.assertAlmostEqual(meter.day_kwh(date(2026, 11, 24)), 0.03)
        self.assertEqual(meter.last["total"], 3600.0)

    def test_big_gap_is_ignored(self):
        meter, _ = _meter()
        t0 = datetime(2026, 11, 24, 10, 0, 0)
        meter.add(1000.0, t0)
        meter.add(1000.0, t0 + timedelta(hours=2))  # PC suspenso / TUI fechada
        self.assertEqual(meter.day_kwh(date(2026, 11, 24)), 0.0)

    def test_midnight_splits_between_days(self):
        meter, _ = _meter()
        meter.add(3600.0, datetime(2026, 11, 24, 23, 59, 50))
        meter.add(3600.0, datetime(2026, 11, 25, 0, 0, 20))
        self.assertAlmostEqual(meter.day_kwh(date(2026, 11, 24)), 0.01)
        self.assertAlmostEqual(meter.day_kwh(date(2026, 11, 25)), 0.02)

    def test_saves_periodically_and_prunes(self):
        meter, saved = _meter({"2026-09-01": 9.0, "2026-11-20": 1.5})
        t = datetime(2026, 11, 24, 10, 0, 0)
        meter.add(100.0, t)
        for _ in range(10):  # 10 × 30 s = 300 s → grava uma vez
            t += timedelta(seconds=30)
            meter.add(100.0, t)
        self.assertEqual(len(saved), 1)
        self.assertNotIn("2026-09-01", saved[0])        # mais velho que KEEP_DAYS
        self.assertIn("2026-11-20", saved[0])
        self.assertAlmostEqual(meter.month_kwh(date(2026, 11, 24)), 1.5 + 100 * 300 / 3_600_000)

    def test_broken_store_does_not_raise(self):
        def boom(*_):
            raise RuntimeError("db fora")
        meter = power.PowerMeter(load=boom, save=boom)
        meter.add(100.0, datetime(2026, 11, 24, 10, 0, 0))
        meter.flush()
        self.assertEqual(meter.day_kwh(), 0.0)


class TestSummary(unittest.TestCase):
    def test_summary_mentions_now_today_and_month(self):
        meter, _ = _meter({date.today().isoformat(): 1.0})
        reading = power.estimate(50, 30, tdp=65, base=45, eff=0.85)
        old = power.meter
        power.meter = meter
        try:
            text = power.summary_text(reading)
        finally:
            power.meter = old
        self.assertIn("W na tomada", text)
        self.assertIn("GPU 30 W medidos", text)
        self.assertIn("Hoje: 1,00 kWh", text)
        self.assertIn("Estimativa", text)

    def test_skill_contract(self):
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "skills", "system", "power_report.py")
        spec = importlib.util.spec_from_file_location("power_report_skill", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.INTENT, "POWER_REPORT")
        self.assertIn("POWER_REPORT", mod.PROMPT_TEXT)
        old = power.summary_text
        power.summary_text = lambda: "ok"
        try:
            self.assertEqual(mod.execute(None, "quanto estou gastando de energia"), "ok")
        finally:
            power.summary_text = old


if __name__ == "__main__":
    unittest.main()
