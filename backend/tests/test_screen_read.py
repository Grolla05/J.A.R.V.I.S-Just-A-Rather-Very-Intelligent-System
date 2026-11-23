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


ARTICLE = "\n".join(f"Parágrafo {i}: a fotossíntese converte luz em energia química nas plantas." for i in range(40))
BROWSER = {"hwnd": 7, "title": "Fotossíntese – Wikipédia - Opera", "process": "opera.exe"}


class TestBrowserPage(unittest.TestCase):
    """Navegador em foco: a página vem pela URL da aba; o OCR é só a reserva."""

    def run_skill(self, url, page_text, win=BROWSER, command="resume essa página"):
        self.capture = MagicMock(return_value=("IMG", win["title"]))
        self.recognize = MagicMock(return_value=PROSE)
        self.ask = MagicMock(return_value=iter(["ok"]))
        self.fetch = MagicMock(return_value=page_text)
        self.page_url = MagicMock(return_value=url)
        with patch.object(sr, "capture", self.capture), patch.object(sr, "recognize", self.recognize),                 patch.object(sr, "ask", self.ask), patch.object(sr, "target", MagicMock(return_value=win)),                 patch.object(sr, "page_url", self.page_url), patch.object(sr, "fetch", self.fetch):
            return list(sr.execute(None, command))

    def prompt(self):
        return self.ask.call_args.args[0][0]["content"]

    def test_public_page_is_downloaded_and_ocr_skipped(self):
        url = "https://pt.wikipedia.org/wiki/Fotoss%C3%ADntese"
        self.assertEqual(self.run_skill(url, ARTICLE), ["ok"])
        self.fetch.assert_called_once()
        self.assertEqual(self.fetch.call_args.args[0], url)
        self.capture.assert_not_called()
        self.recognize.assert_not_called()
        self.assertIn(url, self.prompt())
        self.assertIn("Parágrafo 39", self.prompt())   # o que estava fora da tela
        self.assertIn("resume essa página", self.prompt())

    def test_unsafe_url_goes_to_ocr_without_download(self):
        self.run_skill("https://site.com/reset?token=abc123", ARTICLE)
        self.fetch.assert_not_called()
        self.capture.assert_called_once()

    def test_private_host_goes_to_ocr(self):
        self.run_skill("http://192.168.0.1/admin", ARTICLE)
        self.fetch.assert_not_called()
        self.recognize.assert_called_once()

    def test_short_page_falls_back_to_ocr(self):
        self.run_skill("https://mail.google.com/mail/u/0/", "Faça login para continuar")
        self.fetch.assert_called_once()
        self.recognize.assert_called_once()
        self.assertIn("OCR", self.prompt())

    def test_no_url_falls_back_to_ocr(self):
        self.run_skill("", ARTICLE)
        self.fetch.assert_not_called()
        self.recognize.assert_called_once()

    def test_non_browser_never_asks_url(self):
        self.run_skill("https://x.com", ARTICLE, win={"hwnd": 2, "title": "VS Code", "process": "code.exe"})
        self.page_url.assert_not_called()
        self.recognize.assert_called_once()

    def test_monitor_scope_skips_page(self):
        self.run_skill("https://pt.wikipedia.org/wiki/X", ARTICLE, command="lê a tela inteira")
        self.page_url.assert_not_called()

    def test_secrets_in_page_are_masked(self):
        self.run_skill("https://blog.dev/post", ARTICLE + "\nTOKEN: ghp_AbCdEf1234567890XyZ")
        self.assertNotIn("ghp_AbCdEf1234567890XyZ", self.prompt())

    def test_page_error_falls_back_to_ocr(self):
        with patch.object(sr, "read_page", side_effect=RuntimeError("uia")):
            self.run_skill("https://pt.wikipedia.org/wiki/X", ARTICLE)
        self.recognize.assert_called_once()


class TestContract(unittest.TestCase):
    def test_skill_contract(self):
        self.assertEqual(sr.INTENT, "SCREEN_READ")
        self.assertTrue(sr.PROMPT_TEXT.strip())
        self.assertIn("tela", sr.KEYWORDS)
        self.assertIn("SCREEN_CONTROL", sr.PROMPT_TEXT)  # "NÃO use para…" evita confundir


if __name__ == "__main__":
    unittest.main()
