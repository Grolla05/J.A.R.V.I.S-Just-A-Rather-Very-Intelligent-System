"""Web Watch — core/webwatch.py (preço, hash, linhas novas, URL segura) e
services/web_watch.py (pedido, banco, checagem, falas). Sem rede, sem GitHub,
sem Ollama: checadores de mentira e SQLite temporário."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests._stubs import install

install()

import core.database as database  # noqa: E402
from core import webwatch  # noqa: E402
from core.config import settings  # noqa: E402
from services import web_watch  # noqa: E402

NOW = datetime(2026, 11, 25, 12, 0)
URL = "https://www.loja.com.br/produto/rtx-5060"

LD_HTML = """<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Product", "name": "RTX",
 "offers": {"@type": "Offer", "price": "2499.90", "priceCurrency": "BRL"}}
</script></head><body><p>Placa de vídeo RTX 5060 com 8 GB.</p></body></html>"""
META_HTML = '<html><head><meta property="product:price:amount" content="1.299,00"></head><body></body></html>'
TEXT_HTML = "<html><body><p>Preço especial de lançamento: R$ 1.849,90 à vista no Pix.</p></body></html>"


class TestPriceParsing(unittest.TestCase):
    def test_parse_number_formats(self):
        self.assertEqual(webwatch.parse_number("1.234,56"), 1234.56)
        self.assertEqual(webwatch.parse_number("R$ 99,9"), 99.9)
        self.assertEqual(webwatch.parse_number("1234.56"), 1234.56)
        self.assertEqual(webwatch.parse_number("1.234"), 1234.0)
        self.assertEqual(webwatch.parse_number(300), 300.0)
        for bad in ("", "abc", None, 0, -5, True):
            self.assertIsNone(webwatch.parse_number(bad), bad)

    def test_price_from_json_ld_meta_and_text(self):
        self.assertEqual(webwatch.parse_price(LD_HTML), 2499.90)
        self.assertEqual(webwatch.parse_price(META_HTML), 1299.0)
        self.assertEqual(webwatch.parse_price(TEXT_HTML), 1849.90)
        self.assertIsNone(webwatch.parse_price("<html><body><p>Sem preço por aqui, só texto longo.</p></body></html>"))

    def test_json_ld_inside_graph(self):
        html = ('<script type="application/ld+json">{"@graph": [{"@type": "WebPage"}, '
                '{"@type": "Product", "offers": [{"lowPrice": 150}]}]}</script>')
        self.assertEqual(webwatch.parse_price(html), 150.0)

    def test_format_brl(self):
        self.assertEqual(webwatch.format_brl(1234.5), "R$ 1.234,50")
        self.assertEqual(webwatch.format_brl(9.9), "R$ 9,90")

    def test_check_price_uses_llm_only_without_markup(self):
        calls = []
        no_price = "<html><body><p>Produto incrível, compre já, oferta imperdível de hoje.</p></body></html>"
        res = webwatch.check_price(URL, fetch=lambda u: (no_price, None),
                                   ask_llm=lambda text: calls.append(text) or 777.0)
        self.assertEqual(res, {"price": 777.0})
        self.assertEqual(len(calls), 1)
        calls.clear()
        webwatch.check_price(URL, fetch=lambda u: (LD_HTML, None), ask_llm=lambda t: calls.append(t))
        self.assertEqual(calls, [])

    def test_check_price_error(self):
        res = webwatch.check_price(URL, fetch=lambda u: ("", "o site respondeu HTTP 503"))
        self.assertEqual(res, {"error": "o site respondeu HTTP 503"})


class TestPageFingerprint(unittest.TestCase):
    def test_fingerprint_ignores_clock_and_spacing(self):
        a = webwatch.fingerprint("Notícias\nAtualizado às 10:32 de 24/11/2026\nTexto")
        b = webwatch.fingerprint("Notícias   \nAtualizado às 11:05 de 25/11/2026\n Texto")
        self.assertEqual(a, b)
        self.assertNotEqual(a, webwatch.fingerprint("Notícias\nTexto novo"))

    def test_new_lines(self):
        old = "Vaga A\nVaga B"
        new = "Vaga A\nVaga C\nVaga B\nVaga D\nVaga E\nVaga F"
        self.assertEqual(webwatch.new_lines(old, new), ["Vaga C", "Vaga D", "Vaga E"])


class TestTargets(unittest.TestCase):
    def test_github_repo(self):
        self.assertEqual(webwatch.github_repo("https://github.com/ollama/ollama"), "ollama/ollama")
        self.assertEqual(webwatch.github_repo("https://github.com/ollama/ollama/releases"), "ollama/ollama")
        self.assertEqual(webwatch.github_repo("ollama/ollama"), "ollama/ollama")
        self.assertIsNone(webwatch.github_repo("www.site.com/pagina"))
        self.assertIsNone(webwatch.github_repo(URL))

    def test_fetch_refuses_unsafe_urls(self):
        for url in ("http://localhost:8000/a", "http://192.168.0.1/admin", "file:///C:/x",
                    "https://site.com/?token=abc"):
            html, error = webwatch.fetch_html(url)
            self.assertEqual(html, "")
            self.assertIn("não permitido", error, url)

    def test_fetch_refuses_redirect_to_private(self):
        res = SimpleNamespace(url="http://10.0.0.5/", status_code=200, headers={"Content-Type": "text/html"},
                              text="<p>x</p>")
        with patch("requests.get", return_value=res):
            html, error = webwatch.fetch_html("https://encurtador.com/abc")
        self.assertEqual(html, "")
        self.assertIn("redirecionou", error)


class TestParseRequest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(web_watch.parse_request(f"vigia {URL}"),
                         {"kind": "page", "target": URL, "target_price": None})
        self.assertEqual(web_watch.parse_request(f"{URL} preço abaixo de 2.000"),
                         {"kind": "price", "target": URL, "target_price": 2000.0})
        self.assertEqual(web_watch.parse_request(f"me avisa quando o preço de {URL}. baixar")["kind"], "price")
        self.assertEqual(web_watch.parse_request("acompanha as releases do ollama/ollama")["target"], "ollama/ollama")
        self.assertEqual(web_watch.parse_request("vigia https://github.com/a/b")["kind"], "repo")
        self.assertEqual(web_watch.parse_request("vigia o repositório jarvis")["target"], "jarvis")

    def test_active_tab_fallback(self):
        req = web_watch.parse_request("me avisa quando o preço dessa página baixar de 300",
                                      url_fallback=lambda: URL)
        self.assertEqual(req, {"kind": "price", "target": URL, "target_price": 300.0})
        self.assertIsNone(web_watch.parse_request("vigia isso", url_fallback=lambda: ""))
        self.assertIsNone(web_watch.parse_request("vigia isso"))

    def test_short_label(self):
        self.assertEqual(web_watch.short_label(URL), "loja.com.br/produto/rtx-5060")


class DbCase(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path = path
        self._orig = settings.DB_PATH
        settings.DB_PATH = Path(path)
        self.db = database.DatabaseManager()
        self._patch = patch.object(web_watch, "db", self.db)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass


class FakeCheckers(dict):
    """Checadores de mentira com respostas trocáveis."""

    def __init__(self, page=None, price=None, repo=None):
        self.answers = {"page": page, "price": price, "repo": repo}
        self.calls = []
        super().__init__({k: self._make(k) for k in ("page", "price", "repo")})

    def _make(self, kind):
        def check(target):
            self.calls.append((kind, target))
            return self.answers[kind]
        return check


def _snapshot(tag="v1.0", sha="a" * 40, title="primeiro"):
    return {"repo": "ollama/ollama", "branch": "main",
            "release": {"tag": tag, "name": tag, "url": f"https://github.com/ollama/ollama/releases/{tag}"},
            "commit": {"sha": sha, "title": title, "url": "https://github.com/ollama/ollama/commit/x"}}


class TestService(DbCase):
    def test_price_watch_lifecycle(self):
        fake = FakeCheckers(price={"price": 2500.0})
        reply = web_watch.create_from_text(f"{URL} preço abaixo de 2.000", now=NOW, checkers=fake)
        self.assertIn("R$ 2.500,00", reply)
        self.assertIn("R$ 2.000,00", reply)
        later = NOW + timedelta(minutes=61)

        fake.answers["price"] = {"price": 2300.0}         # caiu, mas acima do alvo
        out = web_watch.collect(later, checkers=fake, interval_min=60)
        self.assertEqual(len(out), 1)
        self.assertFalse(out[0]["urgent"])
        self.assertIn("caiu de R$ 2.500,00 para R$ 2.300,00", out[0]["text"])

        fake.answers["price"] = {"price": 2400.0}         # subiu: só atualiza
        self.assertEqual(web_watch.collect(later + timedelta(minutes=61), checkers=fake, interval_min=60), [])

        fake.answers["price"] = {"price": 1999.0}         # chegou no alvo
        out = web_watch.collect(later + timedelta(minutes=122), checkers=fake, interval_min=60)
        self.assertTrue(out[0]["urgent"])
        self.assertIn("alvo", out[0]["text"])

    def test_not_due_is_not_checked(self):
        fake = FakeCheckers(page={"hash": "h1", "text": "linha"})
        web_watch.create_from_text(f"vigia {URL}", now=NOW, checkers=fake)
        fake.calls.clear()
        web_watch.collect(NOW + timedelta(minutes=10), checkers=fake, interval_min=60)
        self.assertEqual(fake.calls, [])

    def test_page_change_shows_new_lines(self):
        fake = FakeCheckers(page={"hash": "h1", "text": "Vaga A"})
        web_watch.create_from_text(f"vigia {URL}", now=NOW, checkers=fake)
        fake.answers["page"] = {"hash": "h1", "text": "Vaga A"}
        self.assertEqual(web_watch.collect(NOW + timedelta(hours=2), checkers=fake, interval_min=60), [])
        fake.answers["page"] = {"hash": "h2", "text": "Vaga A\nVaga B"}
        out = web_watch.collect(NOW + timedelta(hours=4), checkers=fake, interval_min=60)
        self.assertIn("mudou", out[0]["text"])
        self.assertIn("- Vaga B", out[0]["text"])

    def test_repo_release_then_commit(self):
        fake = FakeCheckers(repo=_snapshot())
        reply = web_watch.create_from_text("ollama/ollama", now=NOW, checkers=fake)
        self.assertIn("release atual v1.0", reply)
        fake.answers["repo"] = _snapshot(tag="v1.1", sha="b" * 40)
        out = web_watch.collect(NOW + timedelta(hours=2), checkers=fake, interval_min=60)
        self.assertIn("Release nova", out[0]["text"])
        self.assertIn("v1.1", out[0]["text"])
        fake.answers["repo"] = _snapshot(tag="v1.1", sha="c" * 40, title="corrige bug")
        out = web_watch.collect(NOW + timedelta(hours=4), checkers=fake, interval_min=60)
        self.assertIn("Commit novo", out[0]["text"])
        self.assertIn("corrige bug", out[0]["text"])
        self.assertEqual(json.loads(web_watch.items()[0]["last_value"])["commit"], "c" * 40)

    def test_error_keeps_state_and_never_raises(self):
        fake = FakeCheckers(price={"price": 100.0})
        web_watch.create_from_text(f"{URL} preço", now=NOW, checkers=fake)
        fake.answers["price"] = {"error": "site fora do ar"}
        self.assertEqual(web_watch.collect(NOW + timedelta(hours=2), checkers=fake, interval_min=60), [])
        item = web_watch.items()[0]
        self.assertEqual(webwatch.parse_number(item["last_value"]), 100.0)
        self.assertEqual(item["last_checked"], (NOW + timedelta(hours=2)).isoformat())

        def boom(target):
            raise RuntimeError("quebrou")
        self.assertEqual(web_watch.collect(NOW + timedelta(hours=9), checkers={"price": boom},
                                           interval_min=60), [])

    def test_duplicate_limit_list_and_remove(self):
        fake = FakeCheckers(page={"hash": "h", "text": "t"})
        web_watch.create_from_text(f"vigia {URL}", now=NOW, checkers=fake)
        self.assertIn("Já estou vigiando", web_watch.create_from_text(f"vigia {URL}", now=NOW, checkers=fake))
        with patch.object(settings, "WEBWATCH_MAX", 1):
            self.assertIn("limite", web_watch.create_from_text(f"vigia {URL}/outra", now=NOW, checkers=fake))
        self.assertIn("1. 📄 **loja.com.br/produto/rtx-5060**", web_watch.list_text())
        self.assertIn("Não há item 5", web_watch.remove_text(5))
        self.assertIn("Parei de vigiar", web_watch.remove_text(1))
        self.assertIn("Nada sob vigia", web_watch.list_text())

    def test_create_errors(self):
        self.assertIn("O que vigiar", web_watch.create_from_text("vigia isso", now=NOW, checkers=FakeCheckers()))
        fake = FakeCheckers(page={"error": "o site respondeu HTTP 404"})
        reply = web_watch.create_from_text(f"vigia {URL}", now=NOW, checkers=fake)
        self.assertIn("HTTP 404", reply)
        self.assertEqual(web_watch.items(), [])


class TestSkill(unittest.TestCase):
    def setUp(self):
        from skills.productivity import web_watch as skill
        self.skill = skill

    def test_routes(self):
        with patch.object(web_watch, "list_text", return_value="lista") as listing, \
             patch.object(web_watch, "remove_text", return_value="removido") as remove, \
             patch.object(web_watch, "create_from_text", return_value="criado") as create:
            self.assertEqual(self.skill.execute(None, "o que você está vigiando?"), "lista")
            self.assertEqual(self.skill.execute(None, "para de vigiar o 2"), "removido")
            self.assertIn("Qual item", self.skill.execute(None, "para de vigiar"))
            self.assertEqual(self.skill.execute(None, "vigia o preço dessa página abaixo de 300"), "criado")
        listing.assert_called_once()
        remove.assert_called_once_with(2)
        self.assertIs(create.call_args.kwargs["url_fallback"], self.skill._active_url)


if __name__ == "__main__":
    unittest.main()
