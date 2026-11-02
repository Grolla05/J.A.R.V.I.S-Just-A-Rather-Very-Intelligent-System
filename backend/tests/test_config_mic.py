"""Fix #5 — MIC_ENERGY_THRESHOLD exposto no Settings (fallback estático do mic)."""
import unittest

from tests._stubs import install

install()

from core.config import settings


class TestMicEnergyThreshold(unittest.TestCase):
    def test_attribute_exists_and_is_int(self):
        self.assertTrue(hasattr(settings, "MIC_ENERGY_THRESHOLD"))
        self.assertIsInstance(settings.MIC_ENERGY_THRESHOLD, int)

    def test_non_negative(self):
        self.assertGreaterEqual(settings.MIC_ENERGY_THRESHOLD, 0)


if __name__ == "__main__":
    unittest.main()
