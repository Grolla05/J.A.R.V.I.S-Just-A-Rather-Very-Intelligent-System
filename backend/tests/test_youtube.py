"""YouTube: core/youtube.py (busca de vídeo, títulos) e a skill YOUTUBE_CONTROL
(regex sem Ollama, teclas do player, aba de fundo, foco devolvido)."""
import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import youtube

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "skills", "automation", "youtube_control.py")
_spec = importlib.util.spec_from_file_location("youtube_control", _PATH)
yt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(yt)

# Trecho do ytInitialData de youtube.com/results (título com emoji e aspas escapados)
RESULTS_HTML = (r'var ytInitialData = {"contents":[{"videoRenderer":{"videoId":"rFZHOHl-L8A","thumbnail":{},'
                r'"title":{"runs":[{"text":"lofi hip hop radio 📚 beats \"to\" study"}]}}}]}')


class TestCoreYoutube(unittest.TestCase):
    def setUp(self):
        youtube._cache.clear()

    def test_pick_video_skips_non_youtube(self):
        results = [{"content": "https://vimeo.com/1", "title": "A"},
                   {"content": "https://www.youtube.com/watch?v=abc", "title": "Lo-fi"},
                   {"content": "https://youtu.be/xyz", "title": "B"}]
        self.assertEqual(youtube.pick_video(results), ("https://www.youtube.com/watch?v=abc", "Lo-fi"))
        self.assertIsNone(youtube.pick_video([{"content": "https://x.com"}]))

    def test_parse_results_html(self):
        url, title = youtube.parse_results_html(RESULTS_HTML)
        self.assertEqual(url, "https://www.youtube.com/watch?v=rFZHOHl-L8A")
        self.assertEqual(title, 'lofi hip hop radio \U0001f4da beats "to" study')
        self.assertIsNone(youtube.parse_results_html("<html>sem vídeo</html>"))

    def test_results_page_comes_first(self):
        with patch.object(youtube, "_from_results_page", return_value=("https://www.youtube.com/watch?v=a", "A")), \
                patch.object(youtube, "_from_ddgs") as ddgs:
            self.assertEqual(youtube.find_video("x"), ("https://www.youtube.com/watch?v=a", "A"))
        ddgs.assert_not_called()

    def test_find_video_uses_ddgs(self):
        fake = MagicMock()
        fake.DDGS.return_value.videos.return_value = [{"content": "https://youtu.be/q1", "title": "Achado"}]
        with patch.dict(sys.modules, {"ddgs": fake}), patch.object(youtube, "_from_results_page", return_value=None):
            self.assertEqual(youtube.find_video("interstellar trailer"), ("https://youtu.be/q1", "Achado"))

    def test_find_video_retries_after_dns_error(self):
        fake = MagicMock()
        fake.DDGS.return_value.videos.side_effect = [RuntimeError("DNSError"),
                                                     [{"content": "https://youtu.be/ok", "title": "Lo-fi"}]]
        with patch.dict(sys.modules, {"ddgs": fake}), patch.object(youtube.time, "sleep"), \
                patch.object(youtube, "_from_results_page", return_value=None):
            self.assertEqual(youtube.find_video("lo-fi"), ("https://youtu.be/ok", "Lo-fi"))
        self.assertEqual(fake.DDGS.return_value.videos.call_count, 2)

    def test_find_video_falls_back_to_results(self):
        fake = MagicMock()
        fake.DDGS.return_value.videos.side_effect = RuntimeError("sem rede")
        with patch.dict(sys.modules, {"ddgs": fake}), patch.object(youtube.time, "sleep"), \
                patch.object(youtube, "_from_results_page", return_value=None):
            url, title = youtube.find_video("receita de pão caseiro")
        self.assertEqual(url, youtube.RESULTS_URL + "receita+de+p%C3%A3o+caseiro")
        self.assertIsNone(title)

    def test_titles(self):
        self.assertEqual(youtube.clean_title("(2) Lo-fi beats - YouTube - Opera"), "Lo-fi beats")
        self.assertEqual(youtube.clean_title("Aula 3 – YouTube"), "Aula 3")
        self.assertTrue(youtube.is_youtube_title("Lo-fi - YouTube - Google Chrome"))
        self.assertTrue(youtube.is_youtube_title("YouTube"))
        self.assertFalse(youtube.is_youtube_title("GitHub - Opera"))


class TestParse(unittest.TestCase):
    def test_phrases(self):
        cases = {
            "toca lo-fi no YouTube": ("PLAY", "lo-fi"),
            "Jarvis, coloca Interstellar trailer no YouTube.": ("PLAY", "interstellar trailer"),
            "coloca o vídeo de receita de pão": ("PLAY", "receita de pao"),
            "pesquisa receita de pão no youtube": ("SEARCH", "receita de pao"),
            "abre o youtube": ("OPEN_HOME", None),
            "toca o vídeo": ("RESUME", None),
            "pausa o vídeo": ("PAUSE", None),
            "dá play": ("RESUME", None),
            "avança 30 segundos": ("FORWARD", 30),
            "avança 1 minuto": ("FORWARD", 60),
            "volta 10 segundos": ("BACK", 10),
            "volta um pouco": ("BACK", 10),
            "tela cheia": ("FULLSCREEN", None),
            "modo cinema": ("THEATER", None),
            "liga a legenda": ("CAPTIONS", None),
            "muta o vídeo": ("MUTE", None),
            "velocidade 1.5": ("SPEED_SET", 1.5),
            "velocidade 1,25": ("SPEED_SET", 1.25),
            "velocidade normal": ("SPEED_SET", 1.0),
            "próximo vídeo": ("NEXT", None),
            "vídeo anterior": ("PREVIOUS", None),
            "do começo": ("RESTART", None),
            "vai para a metade do vídeo": ("SEEK_PERCENT", 5),
            "pula para 30%": ("SEEK_PERCENT", 3),
            "que vídeo é esse?": ("NOW_PLAYING", None),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(yt.parse(text), expected)

    def test_seek_and_speed_math(self):
        self.assertEqual(yt.seek_keys(30), ("l", 3))
        self.assertEqual(yt.seek_keys(15), ("right", 3))
        self.assertEqual(yt.seek_keys(5), ("right", 1))
        self.assertEqual(yt.speed_presses(1), 3)
        self.assertEqual(yt.speed_presses(1.5), 5)
        self.assertEqual(yt.speed_presses(9), 7)   # teto 2×


WIN_ACTIVE = {"hwnd": 5, "title": "Lo-fi beats - YouTube - Opera", "process": "opera.exe"}
WIN_OTHER = {"hwnd": 6, "title": "GitHub - Opera", "process": "opera.exe"}


class Base(unittest.TestCase):
    def setUp(self):
        self.b = MagicMock()
        self.b.find_browser_windows.return_value = [WIN_ACTIVE]
        self.b.send_hotkey.return_value = True
        self.b.select_tab.return_value = True
        self.b.open_url.return_value = True
        self.b.foreground.return_value = 77   # terminal do usuário
        self._p = patch.object(yt, "browser", self.b)
        self._p.start()
        self.llm = patch.object(yt, "_ask_llm", side_effect=AssertionError("não deveria chamar o LLM"))
        self.llm.start()

    def tearDown(self):
        self._p.stop()
        self.llm.stop()


class TestPlayer(Base):
    def test_keys(self):
        cases = {"pausa o vídeo": ("k",), "tela cheia": ("f",), "liga a legenda": ("c",), "muta o vídeo": ("m",),
                 "próximo vídeo": ("shift", "n"), "vídeo anterior": ("shift", "p"), "modo cinema": ("t",),
                 "mais rápido": (">",), "do começo": ("0",)}
        for text, keys in cases.items():
            with self.subTest(text=text):
                self.b.send_hotkey.reset_mock()
                yt.execute(None, text)
                self.assertEqual(self.b.send_hotkey.call_args.args[1:], keys)
                self.assertEqual(self.b.send_hotkey.call_args.args[0], WIN_ACTIVE)

    def test_seek_presses(self):
        yt.execute(None, "volta 30 segundos")
        self.b.send_hotkey.assert_called_once_with(WIN_ACTIVE, "j", presses=3)

    def test_speed_set_goes_down_then_up(self):
        yt.execute(None, "velocidade 1.5")
        calls = self.b.send_hotkey.call_args_list
        self.assertEqual(calls[0].args[1:], ("<",))
        self.assertEqual(calls[0].kwargs["presses"], 7)
        self.assertEqual(calls[1].args[1:], (">",))
        self.assertEqual(calls[1].kwargs["presses"], 5)

    def test_quick_action_restores_focus(self):
        yt.execute(None, "pausa o vídeo")
        self.b.restore_focus.assert_called_once_with(77)

    def test_fullscreen_keeps_focus(self):
        yt.execute(None, "tela cheia")
        self.b.restore_focus.assert_not_called()

    def test_background_tab_is_selected_first(self):
        self.b.find_browser_windows.return_value = [WIN_OTHER]
        self.b.list_tabs.return_value = [{"index": 1, "title": "GitHub", "selected": True},
                                         {"index": 4, "title": "Aula - YouTube", "selected": False}]
        yt.execute(None, "pausa o vídeo")
        self.b.select_tab.assert_called_once_with(WIN_OTHER, 4)
        self.b.send_hotkey.assert_called_once()

    def test_no_youtube(self):
        self.b.find_browser_windows.return_value = [WIN_OTHER]
        self.b.list_tabs.return_value = [{"index": 1, "title": "GitHub", "selected": True}]
        self.assertEqual(yt.execute(None, "pausa o vídeo"), yt.NO_YOUTUBE)
        self.b.send_hotkey.assert_not_called()

    def test_now_playing(self):
        self.assertIn("Lo-fi beats", yt.execute(None, "que vídeo é esse?"))

    def test_no_focus(self):
        self.b.send_hotkey.return_value = False
        self.assertEqual(yt.execute(None, "pausa o vídeo"), yt.NO_FOCUS)
        self.b.restore_focus.assert_not_called()


class TestPlay(Base):
    def test_play_opens_found_video(self):
        with patch.object(yt.youtube, "find_video", return_value=("https://youtu.be/q1", "Lo-fi")):
            out = yt.execute(None, "toca lo-fi no youtube")
        self.b.open_url.assert_called_once_with("https://youtu.be/q1")
        self.assertIn("Lo-fi", out)

    def test_play_without_video_opens_results(self):
        with patch.object(yt.youtube, "find_video", return_value=(youtube.results_url("x"), None)):
            out = yt.execute(None, "toca x no youtube")
        self.assertIn("resultados", out)

    def test_search_opens_results(self):
        yt.execute(None, "pesquisa receita de pão no youtube")
        self.b.open_url.assert_called_once_with(youtube.results_url("receita de pao"))


class TestLlmFallback(unittest.TestCase):
    def test_invalid_action(self):
        with patch("core.llm.query_ollama", return_value='{"action": "DELETE", "value": null}'):
            self.assertIsNone(yt._ask_llm("x"))

    def test_back_seconds(self):
        with patch("core.llm.query_ollama", return_value='{"action": "BACK", "value": 30}'):
            self.assertEqual(yt._ask_llm("recua meio minuto"), ("BACK", 30))

    def test_play_query(self):
        with patch("core.llm.query_ollama", return_value='{"action": "PLAY", "value": "gato no piano"}'):
            self.assertEqual(yt._ask_llm("bota o gato"), ("PLAY", "gato no piano"))


class TestContract(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(yt.INTENT, "YOUTUBE_CONTROL")
        self.assertIn("SPOTIFY_CONTROL", yt.PROMPT_TEXT)
        self.assertIn("youtube", yt.KEYWORDS)
        self.assertIn("avanc*", yt.KEYWORDS)   # "avança 30 segundos" não cita o vídeo


if __name__ == "__main__":
    unittest.main()
