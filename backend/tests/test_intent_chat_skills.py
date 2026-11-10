"""classify_intent no modo Chat: oferece só skills fora de automation/system."""
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
        prompt = self._prompt(exclude_categories=intent.CHAT_BLOCKED_CATEGORIES)
        self.assertIn('"CALENDAR"', prompt)
        self.assertIn('"WEB_SEARCH"', prompt)
        self.assertIn("CAL_PROMPT", prompt)
        self.assertNotIn('"APP_CONTROL"', prompt)
        self.assertNotIn('"SYSTEM_CLEANUP"', prompt)
        self.assertNotIn("CLEAN_PROMPT", prompt)

    def test_copilot_offers_everything(self):
        prompt = self._prompt()
        for name in ("APP_CONTROL", "SYSTEM_CLEANUP", "CALENDAR", "WEB_SEARCH"):
            self.assertIn(f'"{name}"', prompt)

    def test_cache_key_separates_modes(self):
        with patch.object(intent, "query_ollama", return_value='{"intent": "CALENDAR"}') as q:
            intent.classify_intent("agenda", exclude_categories=intent.CHAT_BLOCKED_CATEGORIES)
            intent.classify_intent("agenda")
        self.assertEqual(q.call_count, 2)

    def test_skill_allowed_in_chat(self):
        self.assertTrue(intent.skill_allowed_in_chat("CALENDAR"))
        self.assertTrue(intent.skill_allowed_in_chat("WEB_SEARCH"))
        self.assertFalse(intent.skill_allowed_in_chat("APP_CONTROL"))
        self.assertFalse(intent.skill_allowed_in_chat("SYSTEM_CLEANUP"))
        self.assertFalse(intent.skill_allowed_in_chat("NAO_EXISTE"))


if __name__ == "__main__":
    unittest.main()
