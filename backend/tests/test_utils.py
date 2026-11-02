"""Fix #4 — escape_js centralizado cobre \\, aspas, \\n, \\r, \\t."""
import unittest

from tests._stubs import install

install()

from core.utils import escape_js


class TestEscapeJs(unittest.TestCase):
    def test_backslash_first(self):
        # Barra deve ser escapada antes de tudo (senão duplica os outros escapes)
        self.assertEqual(escape_js("a\\b"), "a\\\\b")

    def test_single_quote(self):
        self.assertEqual(escape_js("it's"), "it\\'s")

    def test_double_quote(self):
        self.assertEqual(escape_js('say "hi"'), 'say \\"hi\\"')

    def test_newline_carriage_tab(self):
        # \r e \t eram os casos não cobertos pela sequência inline antiga
        self.assertEqual(escape_js("a\nb\rc\td"), "a\\nb\\rc\\td")

    def test_none_returns_empty(self):
        self.assertEqual(escape_js(None), "")

    def test_non_string_coerced(self):
        self.assertEqual(escape_js(42), "42")

    def test_no_raw_quote_survives(self):
        # Aspa simples crua paralisa o frontend — não pode sobrar nenhuma sem barra
        out = escape_js("O'Brien disse: \"olá\"\n")
        self.assertNotIn("'", out.replace("\\'", ""))
        self.assertNotIn('"', out.replace('\\"', ""))


if __name__ == "__main__":
    unittest.main()
