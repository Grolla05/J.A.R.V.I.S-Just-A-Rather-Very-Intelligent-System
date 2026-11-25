"""classify_intent no modo Chat: oferece só as skills ativas de productivity e web (lista branca)."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import services.intent as intent


class TestChatSkillOffer(unittest.TestCase):
    def setUp(self):
        intent._intent_cache.clear()
        skills = {
            "APP_CONTROL": MagicMock(CATEGORY="automation", PROMPT_TEXT="APP_PROMPT"),
            "SYSTEM_CLEANUP": MagicMock(CATEGORY="system", PROMPT_TEXT="CLEAN_PROMPT"),
            "CALENDAR": MagicMock(CATEGORY="productivity", PROMPT_TEXT="CAL_PROMPT"),
            "WEB_SEARCH": MagicMock(CATEGORY="web", PROMPT_TEXT="WEB_PROMPT"),
            "NOVA_COISA": MagicMock(CATEGORY="experimental", PROMPT_TEXT="NOVA_PROMPT"),
        }
        self._patches = [
            patch.dict(intent.manager.skills, skills, clear=True),
            patch.object(intent, "is_skill_enabled", return_value=True),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        intent._intent_cache.clear()

    def _prompt(self, **kwargs):
        with patch.object(intent, "query_ollama", return_value='{"intent": "CHAT"}') as q:
            intent.classify_intent("o que tenho amanhã?", **kwargs)
        content = q.call_args.args[0][0]["content"]
        # lista de intents do schema + bloco de prompts das skills (os exemplos fixos do .md ficam de fora)
        options = next(line for line in content.splitlines() if line.strip().startswith('"intent":'))
        skills_block = content.split("(PRIORIDADE ALTA):")[1].split("# EXEMPLOS")[0]
        return options + skills_block

    def test_chat_offers_productivity_and_web_only(self):
        prompt = self._prompt(allowed_categories=intent.CHAT_ALLOWED_CATEGORIES)
        self.assertIn('"CALENDAR"', prompt)
        self.assertIn('"WEB_SEARCH"', prompt)
        self.assertIn("CAL_PROMPT", prompt)
        self.assertNotIn('"APP_CONTROL"', prompt)
        self.assertNotIn('"SYSTEM_CLEANUP"', prompt)
        self.assertNotIn("CLEAN_PROMPT", prompt)
        # categoria nova (fora da lista branca) também não vaza para o Chat
        self.assertNotIn('"NOVA_COISA"', prompt)
        self.assertNotIn("NOVA_PROMPT", prompt)

    def test_chat_skips_disabled_productivity_skill(self):
        with patch.object(intent, "is_skill_enabled", side_effect=lambda i, d=None: i != "CALENDAR"):
            prompt = self._prompt(allowed_categories=intent.CHAT_ALLOWED_CATEGORIES)
        self.assertNotIn('"CALENDAR"', prompt)
        self.assertIn('"WEB_SEARCH"', prompt)

    def test_classifier_uses_llm_timeout(self):
        with patch.object(intent, "query_ollama", return_value='{"intent": "CHAT"}') as q:
            intent.classify_intent("o que tenho amanhã?", allowed_categories=intent.CHAT_ALLOWED_CATEGORIES)
        self.assertEqual(q.call_args.kwargs["timeout"], intent.settings.TIMEOUT_LLM)

    def test_copilot_offers_everything(self):
        prompt = self._prompt()
        for name in ("APP_CONTROL", "SYSTEM_CLEANUP", "CALENDAR", "WEB_SEARCH", "NOVA_COISA"):
            self.assertIn(f'"{name}"', prompt)

    def test_cache_key_separates_modes(self):
        with patch.object(intent, "query_ollama", return_value='{"intent": "CALENDAR"}') as q:
            intent.classify_intent("agenda", allowed_categories=intent.CHAT_ALLOWED_CATEGORIES)
            intent.classify_intent("agenda")
        self.assertEqual(q.call_count, 2)

    def test_skill_allowed_in_chat(self):
        self.assertTrue(intent.skill_allowed_in_chat("CALENDAR"))
        self.assertTrue(intent.skill_allowed_in_chat("WEB_SEARCH"))
        self.assertFalse(intent.skill_allowed_in_chat("APP_CONTROL"))
        self.assertFalse(intent.skill_allowed_in_chat("SYSTEM_CLEANUP"))
        self.assertFalse(intent.skill_allowed_in_chat("NOVA_COISA"))
        self.assertFalse(intent.skill_allowed_in_chat("NAO_EXISTE"))


class TestClassifierExamples(unittest.TestCase):
    """Exemplos de cada skill moram no .md dela: só entram quando a skill é oferecida."""

    def test_base_prompt_has_no_skill_examples(self):
        from core.prompts import load_prompt
        base = load_prompt("classify_intent.md", options_str="", skills_prompts="", text="", schema="")
        for name in ("APP_CONTROL", "SPOTIFY_CONTROL", "SYSTEM_SECURITY", "BROWSER_TABS", "CALENDAR", "EMAIL"):
            self.assertNotIn(name, base)
        self.assertIn("MEMORY_READ", base)

    def test_skill_prompts_carry_their_examples(self):
        from core.prompts import load_prompt
        self.assertIn('"fecha o chrome"', load_prompt("skills/app_control.md"))
        self.assertIn('"intent": "EMAIL_MANAGEMENT"', load_prompt("skills/email_management.md"))
        self.assertIn('"intent": "CALENDAR"', load_prompt("skills/calendar.md"))


if __name__ == "__main__":
    unittest.main()
