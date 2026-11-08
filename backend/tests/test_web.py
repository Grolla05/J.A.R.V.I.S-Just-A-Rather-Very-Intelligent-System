"""core.web — extração de HTML, busca (ddgs mockado) e pesquisa completa."""
import sys
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import web  # noqa: E402

HTML = """
<html><head><title>Python 3.14 lançado</title><style>p{color:red}</style></head>
<body>
  <nav><p>Menu principal com vários links inúteis aqui</p></nav>
  <h1>Python 3.14 foi lançado oficialmente hoje</h1>
  <p>A nova versão traz o interpretador free-threaded como opção suportada.</p>
  <p>Ok</p>
  <script>var x = "código que não deve aparecer no texto";</script>
  <footer><p>Copyright de alguém, todos os direitos reservados</p></footer>
</body></html>
"""


class TestExtractText(unittest.TestCase):
    def test_keeps_content_and_drops_noise(self):
        text = web.extract_text(HTML)
        self.assertIn("Python 3.14 foi lançado", text)
        self.assertIn("free-threaded", text)
        self.assertNotIn("Menu principal", text)
        self.assertNotIn("código que não deve", text)
        self.assertNotIn("Copyright", text)
        self.assertNotIn("Ok", text.split("\n"))  # migalha curta descartada

    def test_max_chars_and_empty(self):
        self.assertEqual(web.extract_text(""), "")
        self.assertLessEqual(len(web.extract_text(HTML, max_chars=20)), 20)


class TestSearch(unittest.TestCase):
    def test_maps_ddgs_results(self):
        fake = MagicMock()
        fake.DDGS.return_value.text.return_value = [
            {"title": "A", "href": "https://a.example", "body": "trecho a"},
            {"title": "sem url", "body": "x"},
        ]
        with patch.dict(sys.modules, {"ddgs": fake}):
            results = web.search("python")
        self.assertEqual(results, [{"title": "A", "url": "https://a.example", "snippet": "trecho a"}])

    def test_failure_returns_empty(self):
        fake = MagicMock()
        fake.DDGS.return_value.text.side_effect = RuntimeError("rate limit")
        with patch.dict(sys.modules, {"ddgs": fake}):
            self.assertEqual(web.search("python"), [])

    def test_blank_query(self):
        self.assertEqual(web.search("   "), [])


class TestFetchText(unittest.TestCase):
    def test_http_error_returns_empty(self):
        fake = MagicMock()
        fake.get.return_value = MagicMock(status_code=404, headers={}, text=HTML)
        with patch.dict(sys.modules, {"requests": fake}):
            self.assertEqual(web.fetch_text("https://x.example"), "")

    def test_non_html_ignored(self):
        fake = MagicMock()
        fake.get.return_value = MagicMock(status_code=200, headers={"Content-Type": "application/pdf"}, text="%PDF")
        with patch.dict(sys.modules, {"requests": fake}):
            self.assertEqual(web.fetch_text("https://x.example/a.pdf"), "")

    def test_network_exception(self):
        fake = MagicMock()
        fake.get.side_effect = OSError("offline")
        with patch.dict(sys.modules, {"requests": fake}):
            self.assertEqual(web.fetch_text("https://x.example"), "")


class TestResearch(unittest.TestCase):
    def setUp(self):
        web._cache.clear()

    def test_blank(self):
        self.assertIn("Pesquisar o quê", web.research(""))

    def test_no_results(self):
        with patch.object(web, "search", return_value=[]):
            self.assertIn("não retornou nada", web.research("algo"))

    def test_full_flow_with_sources_and_cache(self):
        results = [{"title": f"T{i}", "url": f"https://s{i}.example", "snippet": f"s{i}"} for i in range(5)]
        with patch.object(web, "search", return_value=results) as search, \
             patch.object(web, "fetch_text", return_value="texto da página") as fetch, \
             patch("core.llm.query_ollama", return_value="Resposta [1].") as llm:
            out = web.research("Pergunta X")
            again = web.research("pergunta x")  # cache (case-insensitive)
        self.assertEqual(fetch.call_count, web.PAGES_TO_READ)
        self.assertEqual(search.call_count, 1)
        self.assertEqual(llm.call_count, 1)
        self.assertIn("Resposta [1].", out)
        self.assertIn("**Fontes**", out)
        self.assertIn("https://s0.example", out)
        self.assertNotIn("https://s3.example", out)
        self.assertEqual(out, again)
        prompt = llm.call_args[0][0][0]["content"]
        self.assertIn("Pergunta X", prompt)
        self.assertIn("texto da página", prompt)

    def test_llm_down_falls_back_to_snippets(self):
        results = [{"title": "T", "url": "https://s.example", "snippet": "trecho útil"}]
        with patch.object(web, "search", return_value=results), \
             patch.object(web, "fetch_text", return_value=""), \
             patch("core.llm.query_ollama", return_value=None):
            out = web.research("q")
        self.assertIn("trecho útil", out)
        self.assertIn("https://s.example", out)


class TestSkill(unittest.TestCase):
    def test_skill_delegates_to_research(self):
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "web", "web_search.py")
        spec = importlib.util.spec_from_file_location("web_search", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.INTENT, "WEB_SEARCH")
        self.assertIn("WEB_SEARCH", mod.PROMPT_TEXT)
        with patch.object(web, "research", return_value="ok") as research:
            self.assertEqual(mod.execute("", "pesquisa clima"), "ok")
        research.assert_called_once_with("pesquisa clima")


if __name__ == "__main__":
    unittest.main()
