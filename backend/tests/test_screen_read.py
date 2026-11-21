"""Skill SCREEN_READ — captura → OCR → prompt certo → stream do modelo de texto."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from skills.productivity import screen_read as sr

TRACE = ('Traceback (most recent call last):\n  File "main.py", line 3, in <module>\n'
         '    print(x)\nNameError: name \'x\' is not defined')
CODE = "def soma(a, b):\n    total = a + b\n    return total\n\nfor i in range(3): print(soma(i, 1))"
PROSE = ("Questão 4. Um trem parte de São Paulo às 8h a 80 km/h. Outro parte do Rio às 9h a 100 km/h. "
         "A distância é de 430 km. A que horas eles se encontram?")


class Base(unittest.TestCase):
    def run_skill(self, text, entity=None, command="explica o que está na minha tela", window="VS Code"):
        self.capture = MagicMock(return_value=("IMG", window))
        self.recognize = MagicMock(return_value=text)
        self.ask = MagicMock(return_value=iter(["ok"]))
        with patch.object(sr, "capture", self.capture), patch.object(sr, "recognize", self.recognize), \
                patch.object(sr, "ask", self.ask):
            return sr.execute(entity, command)

    def prompt(self):
        return self.ask.call_args.args[0][0]["content"]


class TestRouting(Base):
    def test_error_uses_explain_error_prompt(self):
        out = self.run_skill(TRACE)
        self.assertEqual(list(out), ["ok"])
        self.assertIn("NameError", self.prompt())
        self.assertIn("Causa provável", self.prompt())
        self.assertIn("OCR", self.prompt())

    def test_code_uses_explain_code_prompt(self):
        self.run_skill(CODE)
        self.assertIn("def soma", self.prompt())
        self.assertNotIn("Causa provável", self.prompt())
        self.assertNotIn("Texto lido da tela", self.prompt())

    def test_prose_uses_screen_read_with_question_and_window(self):
        self.run_skill(PROSE, command="resolve a questão da tela", window="Prova.pdf")
        prompt = self.prompt()
        self.assertIn("Texto lido da tela", prompt)
        self.assertIn("resolve a questão da tela", prompt)
        self.assertIn("Prova.pdf", prompt)
        self.assertIn("430 km", prompt)


class TestGuards(Base):
    def test_little_text_returns_fixed_reply_without_model(self):
        self.assertEqual(self.run_skill("  ok  "), sr.NO_TEXT_REPLY)
        self.ask.assert_not_called()

    def test_capture_failure(self):
        with patch.object(sr, "capture", MagicMock(return_value=(None, ""))), \
                patch.object(sr, "ask") as ask:
            self.assertEqual(sr.execute(None, "lê a tela"), sr.NO_CAPTURE_REPLY)
        ask.assert_not_called()

    def test_secrets_never_reach_model(self):
        self.run_skill(PROSE + "\nTOKEN: ghp_AbCdEf1234567890XyZ")
        self.assertNotIn("ghp_AbCdEf1234567890XyZ", self.prompt())
        self.assertIn("[oculto]", self.prompt())

    def test_long_text_is_cut(self):
        long_text = "\n".join(f"Linha {i} do documento muito comprido." for i in range(2000))
        self.run_skill(long_text)
        self.assertIn(sr.CUT_MARK.strip(), self.prompt())
        self.assertLess(len(self.prompt()), len(long_text))


class TestScope(Base):
    def test_scope_from_phrase(self):
        self.assertEqual(sr.scope_for(None, "explica o erro na minha tela"), ("window", None))
        self.assertEqual(sr.scope_for(None, "lê a tela inteira"), ("monitor", None))
        self.assertEqual(sr.scope_for("monitor 2", "resume o que tem lá"), ("monitor", 2))
        self.assertEqual(sr.scope_for(None, "o que tem no monitor 3?"), ("monitor", 3))

    def test_scope_reaches_capture(self):
        self.run_skill(PROSE, command="lê a tela inteira")
        self.capture.assert_called_once_with(scope="monitor", monitor_idx=None)

    def test_clip_text_cuts_at_line_end(self):
        self.assertEqual(sr.clip_text("abc\ndef\nghi", limit=9), "abc\ndef" + sr.CUT_MARK)
        self.assertEqual(sr.clip_text("curto", limit=100), "curto")


class TestContract(unittest.TestCase):
    def test_skill_contract(self):
        self.assertEqual(sr.INTENT, "SCREEN_READ")
        self.assertTrue(sr.PROMPT_TEXT.strip())
        self.assertIn("tela", sr.KEYWORDS)
        self.assertIn("SCREEN_CONTROL", sr.PROMPT_TEXT)  # "NÃO use para…" evita confundir


if __name__ == "__main__":
    unittest.main()
