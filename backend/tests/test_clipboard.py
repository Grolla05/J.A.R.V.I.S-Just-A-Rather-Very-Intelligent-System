"""core.clipboard + skill CLIPBOARD — classificação, monitor e ações (sem clipboard real)."""
import importlib.util
import os
import time
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

from core import clipboard  # noqa: E402

CODE = """def soma(a, b):
    return a + b

print(soma(1, 2))"""
JS = "const total = items.reduce((acc, x) => acc + x.price, 0);"
ENGLISH = "The quick brown fox jumps over the lazy dog and it is not afraid of the hunter."
PORTUGUES = "O relatório de vendas do mês passado está na pasta compartilhada da equipe."


class TestClassify(unittest.TestCase):
    def test_cases(self):
        cases = {
            "https://github.com/Jarvis-Project-2026/J.A.R.V.I.S": "url",
            CODE: "code",
            JS: "code",
            ENGLISH: "english",
            PORTUGUES: None,
            "curto": None,
            "": None,
            "x" * (clipboard.MAX_CHARS + 1): None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text[:30]):
                self.assertEqual(clipboard.classify(text), expected)

    def test_resolve_action(self):
        self.assertEqual(clipboard.resolve_action("code"), "explain")
        self.assertEqual(clipboard.resolve_action("english"), "translate")
        self.assertEqual(clipboard.resolve_action("url"), "summarize")
        self.assertEqual(clipboard.resolve_action(None), "explain")
        self.assertEqual(clipboard.resolve_action("code", "traduzir"), "translate")
        self.assertIsNone(clipboard.resolve_action("code", "dançar"))


class TestMonitor(unittest.TestCase):
    def test_suggests_once_per_new_relevant_content(self):
        feed = ["antigo", CODE, CODE, PORTUGUES, ENGLISH, ""]
        seen = []
        mon = clipboard.ClipboardMonitor(lambda k, t: seen.append(k), read_fn=lambda: feed.pop(0) if feed else "")
        mon._last = None
        results = [mon.check_once() for _ in range(6)]
        self.assertEqual(results, [None, "code", None, None, "english", None])
        self.assertEqual(seen, ["code", "english"])
        self.assertEqual([k for k, _ in mon.history], ["code", "english"])

    def test_preexisting_content_is_ignored_on_start(self):
        seen = []
        mon = clipboard.ClipboardMonitor(lambda k, t: seen.append(k), read_fn=lambda: CODE, interval=0.01)
        mon.start()
        try:
            time.sleep(0.1)
        finally:
            mon.stop()
        self.assertEqual(seen, [])

    def test_start_stop_idempotent_and_thread_is_daemon(self):
        feed = iter(["", ENGLISH] + [ENGLISH] * 1000)
        seen = []
        mon = clipboard.ClipboardMonitor(lambda k, t: seen.append(k), read_fn=lambda: next(feed, ENGLISH), interval=0.01)
        mon.start()
        mon.start()
        self.assertTrue(mon._thread.daemon)
        deadline = time.time() + 2
        while not seen and time.time() < deadline:
            time.sleep(0.01)
        mon.stop()
        mon.stop()
        self.assertFalse(mon.running)
        self.assertEqual(seen, ["english"])

    def test_callback_error_does_not_break(self):
        def boom(kind, text):
            raise RuntimeError("ui fechada")
        mon = clipboard.ClipboardMonitor(boom, read_fn=lambda: ENGLISH)
        self.assertEqual(mon.check_once(), "english")


class TestAct(unittest.TestCase):
    def test_empty(self):
        self.assertIn("vazio", clipboard.act("explain", ""))

    def test_explain_and_translate_use_prompts(self):
        with patch("core.llm.query_ollama", return_value=" explicação ") as llm:
            self.assertEqual(clipboard.act("explain", CODE), "explicação")
        self.assertIn("def soma", llm.call_args[0][0][0]["content"])
        with patch("core.llm.query_ollama", return_value="tradução") as llm:
            clipboard.act("translate", ENGLISH)
        self.assertIn("Traduza", llm.call_args[0][0][0]["content"])

    def test_llm_down(self):
        with patch("core.llm.query_ollama", return_value=None):
            self.assertIn("não respondeu", clipboard.act("explain", CODE))

    def test_url_summary_reads_page(self):
        from core import web
        with patch.object(web, "fetch_text", return_value="conteúdo") as fetch, \
             patch.object(web, "summarize", return_value="resumo") as summ:
            self.assertEqual(clipboard.act("summarize", "https://x.example/a"), "resumo")
        fetch.assert_called_once_with("https://x.example/a")
        self.assertEqual(summ.call_args[0][1][0]["text"], "conteúdo")

    def test_unknown_action(self):
        self.assertIn("desconhecida", clipboard.act("dançar", CODE))


class TestSkill(unittest.TestCase):
    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "skills", "automation", "clipboard_assistant.py")
        spec = importlib.util.spec_from_file_location("clipboard_assistant", path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_requested_action(self):
        self.assertEqual(self.mod.requested_action(None, "traduz o que eu copiei"), "translate")
        self.assertEqual(self.mod.requested_action("resumir", "x"), "summarize")
        self.assertIsNone(self.mod.requested_action(None, "o que tem no clipboard"))

    def test_execute_uses_detected_kind(self):
        with patch.object(clipboard, "read", return_value=ENGLISH), \
             patch.object(clipboard, "act", return_value="ok") as act:
            self.assertEqual(self.mod.execute(None, "o que tem no clipboard"), "ok")
        act.assert_called_once_with("translate", ENGLISH)


if __name__ == "__main__":
    unittest.main()
