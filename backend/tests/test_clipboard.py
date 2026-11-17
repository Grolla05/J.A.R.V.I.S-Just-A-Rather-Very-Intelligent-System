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
TRACEBACK = """Traceback (most recent call last):
  File "main.py", line 12, in <module>
    run()
ValueError: invalid literal for int() with base 10: 'x'"""
JS_ERROR = """TypeError: Cannot read properties of undefined (reading 'map')
    at render (app.js:42:13)"""
RUST_ERROR = "error[E0382]: borrow of moved value: `nomes`"


class TestClassify(unittest.TestCase):
    def test_cases(self):
        cases = {
            "https://github.com/Jarvis-Project-2026/J.A.R.V.I.S": "url",
            CODE: "code",
            JS: "code",
            ENGLISH: "english",
            TRACEBACK: "error",
            JS_ERROR: "error",
            RUST_ERROR: "error",
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
        self.assertEqual(clipboard.resolve_action("error"), "explain")
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

    def test_capture_gets_every_new_text(self):
        """O histórico recebe também o que não gera sugestão (tipo "text"); curto demais fica fora."""
        feed = ["antigo", CODE, CODE, PORTUGUES, TRACEBACK]
        captured = []
        mon = clipboard.ClipboardMonitor(lambda k, t: None, read_fn=lambda: feed.pop(0) if feed else "",
                                         on_capture=lambda k, t: captured.append((k, t)))
        for _ in range(5):
            mon.check_once()
        self.assertEqual(captured, [("code", CODE), ("text", PORTUGUES), ("error", TRACEBACK)])

    def test_capture_error_does_not_break(self):
        def boom(kind, text):
            raise RuntimeError("banco fora")
        mon = clipboard.ClipboardMonitor(lambda k, t: None, read_fn=lambda: ENGLISH, on_capture=boom)
        self.assertEqual(mon.check_once(), "english")

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


class TestRead(unittest.TestCase):
    def test_win32_first_keeps_accents(self):
        from core import selection
        text = "Reunião às 15h — levar o relatório"
        with patch.object(selection, "read_clipboard", return_value=f"  {text}\n"), \
             patch.object(clipboard.subprocess, "run") as run:
            self.assertEqual(clipboard.read(), text)
        run.assert_not_called()

    def test_powershell_fallback_forces_utf8(self):
        from unittest.mock import MagicMock

        from core import selection
        with patch.object(selection, "read_clipboard", side_effect=OSError("sem user32")), \
             patch.object(clipboard.subprocess, "run", return_value=MagicMock(stdout="relatório\n")) as run:
            self.assertEqual(clipboard.read(), "relatório")
        self.assertIn("UTF8", run.call_args[0][0][-1])
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")


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
