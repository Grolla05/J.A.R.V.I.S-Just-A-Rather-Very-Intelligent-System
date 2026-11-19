"""#49 — perfil só entra no prompt por palavra inteira; nota irrelevante é descartada."""
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

import sys  # noqa: E402

from core.utils import plain, word_regex  # noqa: E402

obsidian_mod = sys.modules["core.obsidian"]
client = obsidian_mod.obsidian
PROFILE = "# Identidade\nFelipe\n# Família\nPai e mãe\n# Educação\nFaculdade de engenharia"


class TestHelpers(unittest.TestCase):
    def test_plain_strips_accents(self):
        self.assertEqual(plain("Família ÇÃO"), "familia cao")

    def test_word_regex_whole_word(self):
        rx = word_regex(["age", "meta", "quem sou"])
        self.assertIsNone(rx.search(plain("minha agenda")))
        self.assertIsNone(rx.search(plain("metade do dia")))
        self.assertTrue(rx.search(plain("Quem sou eu?")))
        self.assertTrue(rx.search(plain("bateu a meta")))


class TestProfileLayer(unittest.TestCase):
    def setUp(self):
        obsidian_mod._search_warned = False

    def _profile_requested(self, text):
        with patch.object(client, "get_file", return_value=PROFILE) as get_file, \
             patch.object(client, "search_scored", return_value=[]):
            obsidian_mod.get_vault_context(text)
        return any(c.args and c.args[0] == obsidian_mod._PROFILE_FILE for c in get_file.call_args_list)

    def test_unrelated_questions_do_not_pull_profile(self):
        for text in ("qual minha agenda hoje", "mande uma mensagem pro João", "falta recurso no servidor",
                     "metade do arquivo sumiu", "por que demora tanto?", "abre a imagem",
                     "quem ganhou o jogo ontem?", "preciso de um mouse novo"):
            with self.subTest(text=text):
                self.assertFalse(self._profile_requested(text))

    def test_personal_questions_pull_profile(self):
        for text in ("qual o meu nome?", "fale sobre mim", "onde moro?", "Qual é a minha família?",
                     "em que semestre da faculdade eu estou?", "qual meu hobby"):
            with self.subTest(text=text):
                self.assertTrue(self._profile_requested(text))

    def test_section_matched_by_whole_word(self):
        with patch.object(client, "get_file", return_value=PROFILE):
            _, content = obsidian_mod.get_vault_context("quem é minha família?")
        self.assertIn("Pai e mãe", content)
        self.assertNotIn("Faculdade", content)


class TestSearchLayerRelevance(unittest.TestCase):
    def test_note_without_query_words_is_dropped(self):
        results = [{"filename": "Receitas/bolo.md", "score": 3.0}]
        with patch.object(client, "search_scored", return_value=results), \
             patch.object(client, "get_file", return_value="farinha, ovos e açúcar"):
            self.assertEqual(obsidian_mod.get_vault_context("arquitetura do servidor kubernetes"), ("", ""))

    def test_relevant_note_is_kept(self):
        results = [{"filename": "Infra/cluster.md", "score": 3.0}]
        with patch.object(client, "search_scored", return_value=results), \
             patch.object(client, "get_file", return_value="O servidor roda Kubernetes 1.30"):
            name, _ = obsidian_mod.get_vault_context("arquitetura do servidor kubernetes")
        self.assertEqual(name, "Infra/cluster.md")

    def test_below_min_score_is_dropped(self):
        results = [{"filename": "Infra/cluster.md", "score": 0.2}]
        with patch.object(obsidian_mod.settings, "VAULT_MIN_SCORE", 0.5), \
             patch.object(client, "search_scored", return_value=results), \
             patch.object(client, "get_file", return_value="servidor kubernetes") as get_file:
            self.assertEqual(obsidian_mod.get_vault_context("servidor kubernetes"), ("", ""))
        get_file.assert_not_called()

    def test_small_talk_skips_search(self):
        with patch.object(client, "search_scored") as search:
            self.assertEqual(obsidian_mod.get_vault_context("oi, tudo bem?"), ("", ""))
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
