"""#52 — skills desligadas lidas uma vez por classificação (cache invalidado no toggle)."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import services.intent as intent
from services import skill_settings


class TestDisabledCache(unittest.TestCase):
    def setUp(self):
        skill_settings.invalidate_cache()
        intent._intent_cache.clear()
        self.store = {"disabled_skills": ["WEB_SEARCH"], "disabled_categories": ["system"]}
        self.get = MagicMock(side_effect=lambda k: self.store.get(k))
        self.save = MagicMock(side_effect=lambda k, v: self.store.__setitem__(k, list(v)))
        skills = {
            "APP_CONTROL": MagicMock(CATEGORY="automation", PROMPT_TEXT="APP"),
            "SYSTEM_CLEANUP": MagicMock(CATEGORY="system", PROMPT_TEXT="CLEAN"),
            "CALENDAR": MagicMock(CATEGORY="productivity", PROMPT_TEXT="CAL"),
            "WEB_SEARCH": MagicMock(CATEGORY="web", PROMPT_TEXT="WEB"),
        }
        self._patches = [
            patch.object(skill_settings.db, "get_config", self.get),
            patch.object(skill_settings.db, "save_config", self.save),
            patch.dict(intent.manager.skills, skills, clear=True),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        skill_settings.invalidate_cache()
        intent._intent_cache.clear()

    def test_classify_reads_config_at_most_twice(self):
        with patch.object(intent, "query_ollama", return_value='{"intent": "CHAT"}') as q:
            intent.classify_intent("qualquer coisa nova")
        self.assertLessEqual(self.get.call_count, 2)
        content = q.call_args.args[0][0]["content"]
        # só a linha de opções do schema (os exemplos fixos do .md citam WEB_SEARCH)
        prompt = next(line for line in content.splitlines() if line.strip().startswith('"intent":'))
        self.assertIn('"CALENDAR"', prompt)
        self.assertNotIn('"WEB_SEARCH"', prompt)      # skill desligada
        self.assertNotIn('"SYSTEM_CLEANUP"', prompt)  # categoria desligada

    def test_second_message_uses_cache(self):
        with patch.object(intent, "query_ollama", return_value='{"intent": "CHAT"}'):
            intent.classify_intent("mensagem um")
            intent.classify_intent("mensagem dois")
        self.assertEqual(self.get.call_count, 2)

    def test_is_skill_enabled(self):
        self.assertTrue(intent.is_skill_enabled("CALENDAR"))
        self.assertFalse(intent.is_skill_enabled("WEB_SEARCH"))
        self.assertFalse(intent.is_skill_enabled("SYSTEM_CLEANUP"))

    def test_toggle_invalidates_cache(self):
        self.assertFalse(intent.is_skill_enabled("WEB_SEARCH"))
        self.assertEqual(skill_settings.set_enabled("web_search", True), "skill")
        self.assertTrue(intent.is_skill_enabled("WEB_SEARCH"))
        self.assertEqual(skill_settings.set_enabled("system", True), "category")
        self.assertTrue(intent.is_skill_enabled("SYSTEM_CLEANUP"))


if __name__ == "__main__":
    unittest.main()
