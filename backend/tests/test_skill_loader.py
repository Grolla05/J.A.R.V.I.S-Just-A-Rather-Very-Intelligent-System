"""#56 — skill_loader independe do CWD, avisa INTENT duplicado e `import core` é leve."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._stubs import install

install()

from core import skill_loader  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


def _skill(folder, name, intent):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.py").write_text(textwrap.dedent(f"""
        INTENT = "{intent}"
        PROMPT_TEXT = "{name}"
        def execute(entity, command):
            return "{name}"
    """), encoding="utf-8")


class TestSkillLoader(unittest.TestCase):
    def test_root_is_absolute_and_independent_of_cwd(self):
        self.assertTrue(skill_loader.SKILLS_ROOT.is_absolute())
        self.assertEqual(skill_loader.SKILLS_ROOT, BACKEND / "skills")
        old = os.getcwd()
        try:
            os.chdir(BACKEND.parent)  # `python backend/main.py` da raiz
            manager = skill_loader.SkillManager()
            manager.ensure_loaded()
        finally:
            os.chdir(old)
        self.assertGreater(len(manager.skills), 0)

    def test_duplicate_intent_warns_and_keeps_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _skill(root / "automation", "a_first", "DUP")
            _skill(root / "web", "z_second", "DUP")
            _skill(root / "web", "other", "OTHER")
            manager = skill_loader.SkillManager(root)
            with patch.object(skill_loader.log, "warning") as warning:
                manager.ensure_loaded()
        self.assertEqual(manager.skills["DUP"].FILE_NAME, "a_first.py")
        self.assertEqual(set(manager.skills), {"DUP", "OTHER"})
        self.assertEqual(warning.call_count, 1)
        self.assertIn("DUP", warning.call_args[0][0])

    def test_loads_lazily_and_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            _skill(Path(tmp) / "web", "one", "ONE")
            manager = skill_loader.SkillManager(tmp)
            self.assertFalse(manager._loaded)
            with patch.object(manager, "load_skills", wraps=manager.load_skills) as load:
                self.assertIn("ONE", manager.skills)
                manager.ensure_loaded()
                _ = manager.prompts
            load.assert_called_once()

    def test_assigning_skills_marks_loaded(self):
        manager = skill_loader.SkillManager("nao-existe")
        manager.skills = {"X": object()}
        self.assertEqual(list(manager.skills), ["X"])


class TestCoreImportIsLight(unittest.TestCase):
    def test_import_core_does_not_open_db_or_load_skills(self):
        code = textwrap.dedent("""
            import sys
            from tests._stubs import install
            install()
            import core
            heavy = [m for m in ("core.database", "core.SystemInfo") if m in sys.modules]
            loaded = "core.skill_loader" in sys.modules and sys.modules["core.skill_loader"].manager._loaded
            print("HEAVY=" + ",".join(heavy), "LOADED=" + str(loaded))
            from core import manager  # não toca `db` aqui: abriria o banco real de dev
            print("LAZY_OK=" + str(hasattr(manager, "ensure_loaded") and "db" in dir(core)))
        """)
        out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True,
                             text=True, timeout=120).stdout
        self.assertIn("HEAVY= LOADED=False", out)
        self.assertIn("LAZY_OK=True", out)


if __name__ == "__main__":
    unittest.main()
