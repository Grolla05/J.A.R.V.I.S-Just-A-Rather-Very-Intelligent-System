"""Wake word configurável: WAKE_WORDS no .env + busca por palavra inteira."""
import unittest

from tests._stubs import install

install()

import importlib.util
from pathlib import Path

from core.config import DEFAULT_WAKE_WORDS, parse_word_list, settings

# test_alerts_cache troca services.listen por um MagicMock em sys.modules:
# carrega o arquivo real com outro nome para não depender da ordem dos testes.
_spec = importlib.util.spec_from_file_location(
    "_listen_real", Path(__file__).resolve().parents[1] / "services" / "listen.py")
_listen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_listen)
clean_phrase, find_wake_word = _listen.clean_phrase, _listen.find_wake_word


class TestParseWordList(unittest.TestCase):
    def test_empty_uses_default(self):
        self.assertEqual(parse_word_list("", DEFAULT_WAKE_WORDS), DEFAULT_WAKE_WORDS)
        self.assertEqual(parse_word_list(" , ,", ("jarvis",)), ("jarvis",))

    def test_normalizes_case_spaces_and_duplicates(self):
        self.assertEqual(parse_word_list(" Jarvis ,  Sexta   Feira,jarvis"), ("jarvis", "sexta feira"))

    def test_settings_exposes_tuple(self):
        self.assertIsInstance(settings.WAKE_WORDS, tuple)
        self.assertTrue(settings.WAKE_WORDS)


class TestFindWakeWord(unittest.TestCase):
    def test_whole_word_only(self):
        self.assertIsNone(find_wake_word("vamos viajar amanhã", ("jar",)))
        self.assertEqual(find_wake_word("jar abre o spotify", ("jar",)), "jar")

    def test_longest_wins(self):
        phrase = clean_phrase("Jair vis, abre o chrome")
        self.assertEqual(find_wake_word(phrase, ("jair", "jair vis")), "jair vis")

    def test_punctuation_in_configured_word(self):
        phrase = clean_phrase("Sexta-Feira, abre o Spotify!")
        self.assertEqual(phrase, "sexta feira abre o spotify")
        self.assertEqual(find_wake_word(phrase, ("sexta-feira",)), "sexta feira")

    def test_regex_chars_are_escaped(self):
        self.assertIsNone(find_wake_word("jarvis", ("j.rvis+",)))
        self.assertIsNone(find_wake_word("qualquer coisa", ("",)))

    def test_no_match(self):
        self.assertIsNone(find_wake_word("abre o spotify", DEFAULT_WAKE_WORDS))


if __name__ == "__main__":
    unittest.main()
