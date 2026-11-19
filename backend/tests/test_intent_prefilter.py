"""#51 — atalho para mensagem trivial, pré-filtro por KEYWORDS e alerta de contexto."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests._stubs import install

install()

import services.intent as intent


def _skill(category, prompt, keywords=None):
    mod = SimpleNamespace(CATEGORY=category, PROMPT_TEXT=prompt)
    if keywords is not None:
        mod.KEYWORDS = keywords
    return mod


class TestTrivial(unittest.TestCase):
    def test_trivial_messages(self):
        for text in ("oi", "Olá!", "obrigado, Jarvis", "valeu", "ok", "tchau", "boa noite jarvis",
                     "oi, tudo bem?", "muito obrigada"):
            self.assertTrue(intent.is_trivial(text), text)

    def test_not_trivial(self):
        for text in ("", "bom dia", "bom dia, qual o resumo do dia?", "oi, abre o chrome",
                     "obrigado, agora toca uma música", "qual a capital da frança?"):
            self.assertFalse(intent.is_trivial(text), text)

    def test_trivial_skips_ollama(self):
        intent._intent_cache.clear()
        with patch.object(intent, "query_ollama") as q:
            res = intent.classify_intent("Valeu, Jarvis!")
        q.assert_not_called()
        self.assertEqual(res["intent"], "CHAT")


class TestPrefilter(unittest.TestCase):
    def setUp(self):
        intent._intent_cache.clear()
        skills = {
            "SPOTIFY_CONTROL": _skill("automation", "SPOTIFY_PROMPT", ("spotify", "music*", "toc*")),
            "CALENDAR": _skill("productivity", "CAL_PROMPT", ("agenda", "reuni*")),
            "GITHUB": _skill("productivity", "GH_PROMPT", ("github", "pr")),
            "LEGACY": _skill("web", "LEGACY_PROMPT"),  # sem KEYWORDS: sempre candidata
        }
        self._patches = [
            patch.dict(intent.manager.skills, skills, clear=True),
            patch.object(intent, "_disabled_sets", return_value=(frozenset(), frozenset())),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        intent._intent_cache.clear()

    def _skills_block(self, text):
        with patch.object(intent, "query_ollama", return_value='{"intent": "CHAT"}') as q:
            intent.classify_intent(text)
        content = q.call_args.args[0][0]["content"]
        return content.split("(PRIORIDADE ALTA):")[1].split("# EXEMPLOS")[0]

    def test_keyword_match_sends_only_candidates(self):
        block = self._skills_block("toca uma música do Queen")
        self.assertIn("SPOTIFY_PROMPT", block)
        self.assertIn("LEGACY_PROMPT", block)
        self.assertNotIn("CAL_PROMPT", block)
        self.assertNotIn("GH_PROMPT", block)

    def test_no_match_sends_everything(self):
        block = self._skills_block("qual a capital da frança")
        for name in ("SPOTIFY_PROMPT", "CAL_PROMPT", "GH_PROMPT", "LEGACY_PROMPT"):
            self.assertIn(name, block)

    def test_whole_word_keyword(self):
        # "pr" sem "*" não casa "preciso"/"pra"
        self.assertEqual(intent.prefilter_skills(["GITHUB", "CALENDAR"], "preciso ir pra lá"),
                         ["GITHUB", "CALENDAR"])
        self.assertEqual(intent.prefilter_skills(["GITHUB", "CALENDAR"], "quantos PR abertos?"), ["GITHUB"])

    def test_prefix_keyword_without_accent(self):
        self.assertEqual(intent.prefilter_skills(["CALENDAR", "GITHUB"], "tenho reunião amanhã?"), ["CALENDAR"])


class TestContextWarning(unittest.TestCase):
    def setUp(self):
        intent._last_ctx_warning = 0.0

    def test_warns_above_ratio_once(self):
        with patch.object(intent.settings, "OLLAMA_NUM_CTX", 1000), patch.object(intent.log, "warning") as w:
            intent._warn_if_context_tight("x" * 3000, 20)   # ~857 tokens > 700
            intent._warn_if_context_tight("x" * 3000, 20)   # dentro da janela de 1 h: calado
        self.assertEqual(w.call_count, 1)

    def test_quiet_below_ratio(self):
        with patch.object(intent.settings, "OLLAMA_NUM_CTX", 1000), patch.object(intent.log, "warning") as w:
            intent._warn_if_context_tight("x" * 2000, 20)   # ~571 tokens
        w.assert_not_called()


class TestRealSkillsKeywords(unittest.TestCase):
    """As skills reais declaram KEYWORDS e frases típicas caem na skill certa."""

    @classmethod
    def setUpClass(cls):
        intent.manager.ensure_loaded()

    def test_all_skills_declare_keywords(self):
        missing = [i for i, m in intent.manager.skills.items() if not getattr(m, "KEYWORDS", None)]
        self.assertEqual(missing, [])

    def test_typical_phrases_keep_right_skill(self):
        cases = {
            "toca Bohemian Rhapsody no spotify": "SPOTIFY_CONTROL",
            "abre o chrome": "APP_CONTROL",
            "o que tenho na agenda amanhã?": "CALENDAR",
            "quantos PRs abertos eu tenho?": "GITHUB",
            "me lembra em 30 minutos de ligar pro João": "REMINDER",
            "como está o trânsito pra faculdade": "TRAFFIC",
            "pesquisa a última versão do python": "WEB_SEARCH",
            "anota essa ideia: app de receitas": "INSIGHT_SAVE",
            "inicia um pomodoro de 50 minutos": "FOCUS_MODE",
            "aumenta o volume": "AUDIO_CONTROL",
            "desliga o computador": "SYSTEM_SECURITY",
            "tem alguém na minha rede?": "NETWORK_SCAN",
        }
        all_skills = list(intent.manager.skills)
        for text, expected in cases.items():
            self.assertIn(expected, intent.prefilter_skills(all_skills, text), text)


if __name__ == "__main__":
    unittest.main()
