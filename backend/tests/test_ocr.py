"""core/ocr.py — preparo da imagem, idiomas, máscara de segredos e falha sem winrt."""
import builtins
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

from core import ocr


class TestSizing(unittest.TestCase):
    def test_upscale_only_short_images(self):
        self.assertTrue(ocr.should_upscale(600))
        self.assertFalse(ocr.should_upscale(1080))
        self.assertFalse(ocr.should_upscale(0))

    def test_target_size_doubles_then_fits_limit(self):
        self.assertEqual(ocr.target_size(800, 400), (1600, 800))
        self.assertEqual(ocr.target_size(1920, 1080), (1920, 1080))
        w, h = ocr.target_size(20000, 1080)
        self.assertLessEqual(max(w, h), ocr.MAX_DIMENSION)


class TestLanguages(unittest.TestCase):
    def test_order_without_duplicates(self):
        self.assertEqual(ocr.language_order(""), ["pt-BR", "en-US"])
        self.assertEqual(ocr.language_order("en-US"), ["en-US", "pt-BR"])
        self.assertEqual(ocr.language_order("es-ES"), ["es-ES", "pt-BR", "en-US"])


class TestMaskSecrets(unittest.TestCase):
    def test_lines_with_tokens_are_hidden(self):
        text = "Erro na linha 3\nOPENAI_KEY = sk-AbC123xYz789QwE\nfim do arquivo"
        self.assertEqual(ocr.mask_secrets(text), "Erro na linha 3\n[oculto]\nfim do arquivo")

    def test_long_random_token_and_key_value_hidden(self):
        self.assertEqual(ocr.mask_secrets("senha: Xk9#mP2$vL7qR4!wZ8tY"), "[oculto]")
        self.assertEqual(ocr.mask_secrets("GITHUB_TOKEN=ghp_abc123DEF456ghi789"), "[oculto]")

    def test_error_and_code_tokens_are_not_secrets(self):
        text = ("NameError: name 'x' is not defined\n  File \"C:\\Proj\\main.py\", line 3, in <module>\n"
                "self.assertEqual(Foo.Bar(1), 2)\nhttps://exemplo.com/a?b=C1d2E3f4G5h6I7j8")
        self.assertEqual(ocr.mask_secrets(text), text)

    def test_normal_text_untouched(self):
        text = "def soma(a, b):\n    return a + b"
        self.assertEqual(ocr.mask_secrets(text), text)
        self.assertEqual(ocr.mask_secrets(""), "")


class TestRecognize(unittest.TestCase):
    def test_none_image(self):
        self.assertEqual(ocr.recognize(None), "")

    def test_missing_winrt_returns_empty(self):
        from PIL import Image
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("winrt"):
                raise ImportError("sem winrt")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            self.assertEqual(ocr.recognize(Image.new("RGB", (100, 100), "white")), "")


if __name__ == "__main__":
    unittest.main()
