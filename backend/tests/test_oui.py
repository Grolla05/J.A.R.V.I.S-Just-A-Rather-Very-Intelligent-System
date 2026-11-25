"""core/oui.py: fabricante pelo MAC (base offline) e MAC privado."""
import unittest

from tests._stubs import install

install()

from core import oui  # noqa: E402

TABLE = {"F0D5BF": "Intel Corporate", "0016 32".replace(" ", ""): "Samsung Electronics Co.,Ltd",
         "B827EB": "Raspberry Pi Foundation"}


class TestOui(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(oui.normalize("f0:d5:bf:00:00:01"), "F0D5BF000001")
        self.assertEqual(oui.normalize("F0-D5-BF-00-00-01"), "F0D5BF000001")
        self.assertEqual(oui.normalize("zz"), "")

    def test_private_bit(self):
        self.assertTrue(oui.is_private("da-a1-19-00-00-00"))   # 0xDA tem o bit 0x02
        self.assertTrue(oui.is_private("02-00-00-00-00-01"))
        self.assertFalse(oui.is_private("f0-d5-bf-00-00-01"))
        self.assertFalse(oui.is_private("lixo"))

    def test_vendor_short_names(self):
        self.assertEqual(oui.vendor("f0-d5-bf-00-00-01", TABLE), "Intel")
        self.assertEqual(oui.vendor("00:16:32:aa:bb:cc", TABLE), "Samsung Electronics")
        self.assertEqual(oui.vendor("b8-27-eb-11-22-33", TABLE), "Raspberry Pi Foundation")

    def test_unknown_private_or_invalid_is_none(self):
        self.assertIsNone(oui.vendor("00-11-22-33-44-55", TABLE))
        self.assertIsNone(oui.vendor("f2-d5-bf-00-00-01", TABLE))  # privado: sem fabricante
        self.assertIsNone(oui.vendor("", TABLE))

    def test_short_name(self):
        self.assertEqual(oui.short_name("Foo Technologies Co., Ltd."), "Foo Technologies")
        self.assertEqual(oui.short_name("Apple, Inc."), "Apple")
        self.assertEqual(oui.short_name("TP-LINK TECHNOLOGIES CO.,LTD."), "TP-LINK TECHNOLOGIES")
        self.assertEqual(oui.short_name("Ltd"), "Ltd")  # não apaga tudo

    def test_bundled_file_loads(self):
        table = oui._load()
        self.assertGreater(len(table), 10_000)
        self.assertEqual(oui.vendor("b8-27-eb-11-22-33", table), "Raspberry Pi Foundation")


if __name__ == "__main__":
    unittest.main()
