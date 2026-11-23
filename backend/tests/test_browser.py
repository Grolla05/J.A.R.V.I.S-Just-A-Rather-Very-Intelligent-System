"""core/browser.py — lógica pura (escolha de janela, URL, aba, URL segura) e
falhas da UI Automation sem levantar. Nenhum navegador real é tocado."""
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

from core import browser


def win(hwnd=1, title="Página - Opera", process="opera.exe", **extra):
    base = {"hwnd": hwnd, "title": title, "process": process, "visible": True, "cloaked": False, "tool": False}
    base.update(extra)
    return base


class TestPickBrowsers(unittest.TestCase):
    def test_only_chromium_in_z_order(self):
        wins = [win(1, process="code.exe"), win(2, process="chrome.exe"), win(3, process="firefox.exe"),
                win(4, process="msedge.exe")]
        self.assertEqual([w["hwnd"] for w in browser.pick_browsers(wins)], [2, 4])

    def test_skips_self_hidden_tool_and_untitled(self):
        wins = [win(1), win(2, visible=False), win(3, cloaked=True), win(4, tool=True), win(5, title="  "), win(6)]
        self.assertEqual([w["hwnd"] for w in browser.pick_browsers(wins, self_hwnds={1})], [6])

    def test_minimized_still_counts(self):
        self.assertEqual(len(browser.pick_browsers([win(1, iconic=True)])), 1)


class TestNormalizeUrl(unittest.TestCase):
    def test_cases(self):
        cases = {
            "https://github.com/x": "https://github.com/x",
            "github.com/Grolla05": "https://github.com/Grolla05",
            "pt.wikipedia.org": "https://pt.wikipedia.org",
            "receita de bolo": "",
            "chrome://settings": "",
            "about:blank": "",
            "opera://startpage": "",
            "": "",
            None: "",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(browser.normalize_url(raw), expected)


class TestFetchSafe(unittest.TestCase):
    def test_public_pages_are_safe(self):
        for url in ("https://pt.wikipedia.org/wiki/Python", "http://example.com/a?page=2&lang=pt",
                    "https://www.youtube.com/watch?v=abc"):
            with self.subTest(url=url):
                self.assertTrue(browser.is_fetch_safe(url))

    def test_unsafe(self):
        for url in ("file:///C:/x.html", "http://localhost:8000", "http://127.0.0.1/", "http://192.168.0.1/admin",
                    "http://10.0.0.5/x", "http://[::1]/", "http://router.lan/", "http://intranet/x",
                    "https://site.com/reset?token=abc", "https://accounts.x.com/cb?code=123&state=9",
                    "https://api.x.com/?api_key=1", "https://x.com/#access_token=abc", "https://user:pw@x.com/",
                    "ftp://x.com/a", "", "nada"):
            with self.subTest(url=url):
                self.assertFalse(browser.is_fetch_safe(url))


class TestMatchTab(unittest.TestCase):
    TABS = [{"index": 1, "title": "Caixa de entrada - Gmail"},
            {"index": 2, "title": "Lo-fi beats to study - YouTube"},
            {"index": 3, "title": "Pull requests · Grolla05/J.A.R.V.I.S · GitHub"},
            {"index": 4, "title": "YouTube"}]

    def test_exact_beats_contains(self):
        self.assertEqual(browser.match_tab(self.TABS, "youtube")["index"], 4)

    def test_contains(self):
        self.assertEqual(browser.match_tab(self.TABS, "gmail")["index"], 1)

    def test_accent_and_case(self):
        tabs = [{"index": 1, "title": "Previsão do Tempo"}]
        self.assertEqual(browser.match_tab(tabs, "previsao")["index"], 1)

    def test_fuzzy_word(self):
        self.assertEqual(browser.match_tab(self.TABS, "githb")["index"], 3)

    def test_nothing(self):
        self.assertIsNone(browser.match_tab(self.TABS, "netflix"))
        self.assertIsNone(browser.match_tab([], "gmail"))
        self.assertIsNone(browser.match_tab(self.TABS, ""))


class TestCleanTabTitle(unittest.TestCase):
    def test_strips_chromium_status(self):
        cases = {
            "Fotossíntese – Wikipédia, a enciclopédia livre - Memory usage - 86.0 MB":
                "Fotossíntese – Wikipédia, a enciclopédia livre",   # visto no Edge real
            "Lo-fi beats - YouTube - Audio playing": "Lo-fi beats - YouTube",
            "Lo-fi beats - YouTube - Reproduzindo áudio": "Lo-fi beats - YouTube",
            "Meet - Uso de memória - 120 MB": "Meet",
            "GitHub​": "GitHub",
            "Pull requests - GitHub": "Pull requests - GitHub",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(browser.clean_tab_title(raw), expected)


class TestUiaFailures(unittest.TestCase):
    def test_no_uia_returns_empty(self):
        with patch.object(browser, "_uia", return_value=(None, None)):
            self.assertEqual(browser.active_url(win()), "")
            self.assertEqual(browser.list_tabs(win()), [])

    def test_non_browser_never_touches_uia(self):
        with patch.object(browser, "_uia") as uia:
            self.assertEqual(browser.active_url(win(process="code.exe")), "")
            self.assertEqual(browser.list_tabs(None), [])
        uia.assert_not_called()

    def test_uia_exception_is_swallowed(self):
        class Boom:
            def ElementFromHandle(self, hwnd):
                raise OSError("COM")
        with patch.object(browser, "_uia", return_value=(Boom(), object())):
            self.assertEqual(browser.active_url(win()), "")
            self.assertEqual(browser.list_tabs(win()), [])

    def test_select_tab_falls_back_to_shortcut(self):
        with patch.object(browser, "_tab_element", return_value=(None, None)), \
                patch.object(browser, "send_hotkey", return_value=True) as hk:
            self.assertTrue(browser.select_tab(win(), 3))
            hk.assert_called_with(win(), "ctrl", "3")
            browser.select_tab(win(), -1)
            hk.assert_called_with(win(), "ctrl", "9")
            self.assertFalse(browser.select_tab(win(), 12))


class TestKeysNeedFocus(unittest.TestCase):
    def test_no_focus_no_keys(self):
        with patch.object(browser, "focus", return_value=False), patch.dict("sys.modules", {"pyautogui": None}):
            # pyautogui=None faria o import falhar: prova que nem chegou a importar
            self.assertFalse(browser.send_hotkey(win(), "ctrl", "w"))

    def test_open_url_only_http(self):
        with patch("webbrowser.open", return_value=True) as op:
            self.assertFalse(browser.open_url("file:///C:/Windows"))
            self.assertFalse(browser.open_url("javascript:alert(1)"))
            self.assertTrue(browser.open_url("https://github.com"))
        op.assert_called_once_with("https://github.com", new=2)


if __name__ == "__main__":
    unittest.main()
