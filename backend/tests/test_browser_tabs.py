"""Skill BROWSER_TABS — roteamento por regex (sem Ollama), atalhos certos e
confirmação antes de fechar várias abas. core.browser todo mockado."""
import importlib.util
import os
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.state as state

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "skills", "automation", "browser_tabs.py")
_spec = importlib.util.spec_from_file_location("browser_tabs", _PATH)
bt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bt)

WIN = {"hwnd": 9, "title": "GitHub - Opera", "process": "opera.exe"}
TABS = [{"index": 1, "title": "Caixa de entrada - Gmail", "selected": False},
        {"index": 2, "title": "Lo-fi beats - YouTube", "selected": True},
        {"index": 3, "title": "GitHub", "selected": False}]


class TestParse(unittest.TestCase):
    def test_phrases(self):
        cases = {
            "nova aba": ("NEW_TAB", None, None),
            "abre uma aba no github": ("NEW_TAB", "github", None),
            "abre uma aba nova e pesquisa receita de bolo": ("NEW_TAB", None, "receita de bolo"),
            "fecha a aba": ("CLOSE_TAB", None, None),
            "fecha a aba do YouTube": ("CLOSE_TAB", "youtube", None),
            "fecha a aba 3": ("CLOSE_TAB", "3", None),
            "fecha as outras abas": ("CLOSE_OTHERS", None, None),
            "fecha todas as abas": ("CLOSE_ALL", None, None),
            "reabre a última aba fechada": ("REOPEN", None, None),
            "quais abas estão abertas?": ("LIST_TABS", None, None),
            "vai para a aba 2": ("GOTO_TAB", "2", None),
            "vai pra terceira aba": ("GOTO_TAB", "terceira", None),
            "Jarvis, muda para a aba do GitHub": ("GOTO_TAB", "github", None),
            "próxima aba": ("NEXT_TAB", None, None),
            "aba anterior": ("PREV_TAB", None, None),
            "recarrega a página": ("RELOAD", None, None),
            "volta a página": ("BACK", None, None),
            "duplica a aba": ("DUPLICATE", None, None),
            "abre uma janela anônima": ("INCOGNITO", None, None),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(bt.parse(text), expected)

    def test_unknown_goes_to_llm(self):
        self.assertIsNone(bt.parse("me leva pro gmail"))

    def test_tab_ref(self):
        self.assertEqual(bt.tab_ref("3"), 3)
        self.assertEqual(bt.tab_ref("terceira"), 3)
        self.assertEqual(bt.tab_ref("última"), -1)
        self.assertIsNone(bt.tab_ref("github"))

    def test_resolve_site(self):
        self.assertEqual(bt.resolve_site("github"), "https://github.com")
        self.assertEqual(bt.resolve_site("github ponto com"), "https://github.com")
        self.assertEqual(bt.resolve_site("docs.python.org/3"), "https://docs.python.org/3")
        self.assertTrue(bt.resolve_site("receita de bolo").startswith(bt.SEARCH_URL))


class Base(unittest.TestCase):
    def setUp(self):
        state.pending_critical_action = None
        self.b = MagicMock()
        self.b.find_browser_window.return_value = WIN
        self.b.list_tabs.return_value = [dict(t) for t in TABS]
        self.b.send_hotkey.return_value = True
        self.b.select_tab.return_value = True
        self.b.close_tab.return_value = True
        self.b.focus.return_value = True
        self.b.open_url.return_value = True
        from core import browser as real
        self.b.match_tab.side_effect = real.match_tab
        self.b.normalize_url.side_effect = real.normalize_url
        self._p = patch.object(bt, "browser", self.b)
        self._p.start()
        self.llm = patch.object(bt, "_ask_llm", side_effect=AssertionError("não deveria chamar o LLM"))
        self.llm.start()

    def tearDown(self):
        self._p.stop()
        self.llm.stop()
        state.pending_critical_action = None


class TestActions(Base):
    def test_hotkeys_without_llm(self):
        cases = {"próxima aba": ("ctrl", "tab"), "aba anterior": ("ctrl", "shift", "tab"),
                 "reabre a aba": ("ctrl", "shift", "t"), "recarrega a página": ("f5",),
                 "volta a página": ("alt", "left"), "abre uma janela anônima": ("ctrl", "shift", "n"),
                 "fecha a aba": ("ctrl", "w"), "nova aba": ("ctrl", "t")}
        for text, keys in cases.items():
            with self.subTest(text=text):
                self.b.send_hotkey.reset_mock()
                bt.execute(None, text)
                self.b.send_hotkey.assert_called_once_with(WIN, *keys)

    def test_new_tab_with_site_opens_url(self):
        bt.execute(None, "abre uma aba no github")
        self.b.open_url.assert_called_once_with("https://github.com")
        self.b.send_hotkey.assert_not_called()

    def test_close_by_name(self):
        out = bt.execute(None, "fecha a aba do youtube")
        self.b.close_tab.assert_called_once_with(WIN, 2)
        self.assertIn("Lo-fi", out)

    def test_close_by_name_not_found(self):
        out = bt.execute(None, "fecha a aba do netflix")
        self.b.close_tab.assert_not_called()
        self.assertIn("netflix", out)

    def test_goto_number_and_name(self):
        bt.execute(None, "vai para a aba 3")
        self.b.select_tab.assert_called_with(WIN, 3)
        bt.execute(None, "vai para a aba do gmail")
        self.b.select_tab.assert_called_with(WIN, 1)

    def test_goto_missing_site_opens_new(self):
        out = bt.execute(None, "vai para a aba do netflix")
        self.b.open_url.assert_called_once_with("https://www.netflix.com")
        self.assertIn("nova", out)

    def test_list(self):
        out = bt.execute(None, "lista as abas")
        self.assertIn("3 aba(s)", out)
        self.assertIn("2. Lo-fi beats - YouTube  ← ativa", out)

    def test_no_browser(self):
        self.b.find_browser_window.return_value = None
        self.assertEqual(bt.execute(None, "fecha a aba"), bt.NO_BROWSER)

    def test_no_focus_reported(self):
        self.b.send_hotkey.return_value = False
        self.assertEqual(bt.execute(None, "próxima aba"), bt.NO_FOCUS)


class TestCloseMany(Base):
    def test_close_others_asks_first(self):
        out = bt.execute(None, "fecha as outras abas")
        self.assertIn("sim", out)
        self.b.close_tab.assert_not_called()
        action = state.pending_critical_action
        self.assertEqual(action["type"], "BROWSER_CLOSE_OTHERS")
        result = action["on_confirm"]()
        # Da direita para a esquerda, poupando a ativa (2)
        self.assertEqual([c.args[1] for c in self.b.close_tab.call_args_list], [3, 1])
        self.assertIn("2 aba(s)", result)

    def test_close_all_closes_window_after_yes(self):
        bt.execute(None, "fecha todas as abas")
        self.b.send_hotkey.assert_not_called()
        state.pending_critical_action["on_confirm"]()
        self.b.send_hotkey.assert_called_once_with(WIN, "ctrl", "shift", "w")

    def test_busy_pending(self):
        from core import pending
        pending.arm("OUTRA", "outra?", lambda: "x")
        self.assertEqual(bt.execute(None, "fecha as outras abas"), pending.BUSY_REPLY)

    def test_single_tab_nothing_to_close(self):
        self.b.list_tabs.return_value = [{"index": 1, "title": "GitHub", "selected": True}]
        self.assertIn("Só existe", bt.execute(None, "fecha as outras abas"))
        self.assertIsNone(state.pending_critical_action)


class TestLlmFallback(unittest.TestCase):
    def test_invalid_action_rejected(self):
        with patch("core.llm.query_ollama", return_value='{"action": "RM_RF", "target": "/"}'):
            self.assertIsNone(bt._ask_llm("faz algo estranho"))

    def test_valid_action(self):
        with patch("core.llm.query_ollama", return_value='{"action": "GOTO_TAB", "target": "gmail"}'):
            self.assertEqual(bt._ask_llm("me leva pro gmail"), ("GOTO_TAB", "gmail", None))

    def test_garbage(self):
        with patch("core.llm.query_ollama", return_value="não sei"):
            self.assertIsNone(bt._ask_llm("x"))


class TestContract(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(bt.INTENT, "BROWSER_TABS")
        self.assertIn("APP_CONTROL", bt.PROMPT_TEXT)
        self.assertIn("aba", bt.KEYWORDS)


if __name__ == "__main__":
    unittest.main()
