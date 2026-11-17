"""Issue #47 — skills falam com o Ollama só por core.llm.

Antes 7 skills montavam f"http://{OLLAMA_HOST}/api/generate"; com o padrão
OLLAMA_HOST=http://localhost:11434 a URL virava http://http://... e todas
falhavam na instalação padrão. Teste estático: não importa as skills (algumas
puxam pycaw/pyautogui).
"""
import os
import unittest

_SKILLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
_MIGRATED = ["automation/app_control.py", "automation/audio_control.py", "automation/keyboard_control.py",
             "automation/screen_control.py", "automation/work_macros.py", "system/system_clear.py",
             "system/system_security.py"]


def _read(rel):
    with open(os.path.join(_SKILLS, rel), encoding="utf-8") as f:
        return f.read()


class TestSkillsUseCoreLlm(unittest.TestCase):
    def test_no_skill_calls_ollama_http_directly(self):
        for root, _, files in os.walk(_SKILLS):
            for name in files:
                if not name.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(root, name), _SKILLS)
                src = _read(rel)
                with self.subTest(skill=rel):
                    self.assertFalse("/api/generate" in src, "URL do Ollama montada à mão")
                    self.assertFalse("settings.OLLAMA_HOST" in src, "usa OLLAMA_HOST direto")

    def test_migrated_skills_use_query_ollama_json(self):
        for rel in _MIGRATED:
            src = _read(rel)
            with self.subTest(skill=rel):
                self.assertIn("from core.llm import query_ollama", src)
                self.assertIn('format="json"', src)
                self.assertNotIn("requests.post", src)


if __name__ == "__main__":
    unittest.main()
