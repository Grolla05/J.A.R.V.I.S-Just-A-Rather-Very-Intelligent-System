"""Fact-Checking — core/factcheck.py: limpeza do pedido, fontes independentes,
regras duras do veredito e Markdown final; skill e /clip checar. Sem rede e sem
Ollama: busca, leitura e modelo de mentira."""
import json
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

from core import clipboard, factcheck  # noqa: E402

CLAIM = "a Muralha da China é visível do espaço"


def results(*domains):
    return [{"title": f"Artigo {d}", "url": f"https://www.{d}/artigo", "snippet": f"trecho de {d}"} for d in domains]


class FakeSearch:
    def __init__(self, first, second=()):
        self.answers = [list(first), list(second)]
        self.queries = []

    def __call__(self, query):
        self.queries.append(query)
        return self.answers[len(self.queries) - 1] if len(self.queries) <= 2 else []


def read_stub(items):
    return [dict(i, text=f"texto completo de {factcheck.domain(i['url'])}") for i in items]


def verdict(**data):
    return lambda claim, sources: json.dumps(data)


class TestClaim(unittest.TestCase):
    def setUp(self):
        factcheck._cache.clear()

    def test_clean_claim(self):
        for text in (f"isso é verdade: {CLAIM}?", f"Jarvis, checa se {CLAIM}", f"é fake que {CLAIM}?",
                     f"verifica pra mim se {CLAIM}", f"essa notícia é verdade? {CLAIM}", CLAIM):
            self.assertEqual(factcheck.clean_claim(text), CLAIM, text)

    def test_long_text_goes_to_llm(self):
        long_text = "Segundo um post viral, " + "blá " * 100 + CLAIM
        calls = []
        claim = factcheck.extract_claim(long_text, ask_llm=lambda t: calls.append(t) or CLAIM)
        self.assertEqual(claim, CLAIM)
        self.assertEqual(len(calls), 1)
        self.assertEqual(factcheck.extract_claim(f"checa se {CLAIM}", ask_llm=lambda t: 1 / 0), CLAIM)

    def test_empty_request(self):
        def no_search(query):
            raise AssertionError("não devia buscar")
        for text in ("checa isso", "isso é verdade?", ""):
            self.assertIn("Checar o quê", factcheck.check(text, search=no_search, claim_llm=None), text)


class TestSources(unittest.TestCase):
    def test_one_per_domain_and_safe_only(self):
        first = results("g1.globo.com", "bbc.com") + [
            {"title": "dup", "url": "https://g1.globo.com/outra", "snippet": ""},
            {"title": "local", "url": "http://192.168.0.10/x", "snippet": ""}]
        search = FakeSearch(first, results("bbc.com", "nasa.gov", "aosfatos.org", "lupa.uol.com.br", "extra.com"))
        sources = factcheck.gather_sources(CLAIM, search)
        self.assertEqual([factcheck.domain(s["url"]) for s in sources],
                         ["g1.globo.com", "bbc.com", "nasa.gov", "aosfatos.org", "lupa.uol.com.br"])
        self.assertEqual(search.queries, [CLAIM, f"{CLAIM} é verdade ou fake"])


class TestVerdictRules(unittest.TestCase):
    def test_confirmed_needs_two_sources(self):
        res = factcheck.parse_verdict(json.dumps({"veredito": "CONFIRMADO", "resumo": "Ok [1].",
                                                  "fontes_a_favor": [1, 2], "fontes_contra": []}), 3)
        self.assertEqual(res["verdict"], "CONFIRMADO")
        res = factcheck.parse_verdict(json.dumps({"veredito": "CONFIRMADO", "resumo": "Ok [1].",
                                                  "fontes_a_favor": [1], "fontes_contra": []}), 3)
        self.assertEqual(res["verdict"], "IMPRECISO")
        res = factcheck.parse_verdict(json.dumps({"veredito": "FALSO", "resumo": "Não.",
                                                  "fontes_a_favor": [], "fontes_contra": []}), 3)
        self.assertEqual(res["verdict"], "INCONCLUSIVO")

    def test_muralha_case_confirmed_with_debunking_sources(self):
        # Caso real (gemma2:2b, 25/11): "CONFIRMADO" citando "Desmentido…" a favor e 2 fontes contra
        titles = ["A muralha da China é visível do espaço? - Mundo Educação",
                  "A muralha da China é visível do espaço? - Brasil Escola",
                  "Desmentido: A Grande Muralha da China Não É Visível do Espaço",
                  "Visível do espaço? Entenda essa e outras curiosidades sobre a ...",
                  "Mito: A muralha da China pode ser vista do espaço | Super"]
        raw = json.dumps({"veredito": "CONFIRMADO", "resumo": "Confirmada por duas fontes.",
                          "fontes_a_favor": [2, 3], "fontes_contra": [4, 5]})
        res = factcheck.parse_verdict(raw, 5, titles)
        self.assertEqual(res["pro"], [2])
        self.assertEqual(res["con"], [3, 4, 5])
        self.assertEqual(res["verdict"], "IMPRECISO")      # divergem: nunca CONFIRMADO
        raw = json.dumps({"veredito": "CONFIRMADO", "resumo": "x", "fontes_a_favor": [3], "fontes_contra": [5]})
        self.assertEqual(factcheck.parse_verdict(raw, 5, titles)["verdict"], "FALSO")
        answer = factcheck.render(CLAIM, factcheck.parse_verdict(raw, 5, titles), results("a.com", "b.com"))
        self.assertIn("O modelo disse CONFIRMADO", answer)

    def test_false_never_becomes_confirmed(self):
        raw = json.dumps({"veredito": "FALSO", "resumo": "x", "fontes_a_favor": [1, 2], "fontes_contra": []})
        self.assertEqual(factcheck.parse_verdict(raw, 3)["verdict"], "IMPRECISO")
        raw = json.dumps({"veredito": "FALSO", "resumo": "x", "fontes_a_favor": [1, 2], "fontes_contra": [3]})
        self.assertNotEqual(factcheck.parse_verdict(raw, 3)["verdict"], "CONFIRMADO")

    def test_debunk_titles(self):
        for title in ("Mito: X", "Desmentido: X", "Por que NÃO é possível ver X", "É fake que X", "X não é verdade"):
            self.assertTrue(factcheck._DEBUNK_RE.search(title), title)
        for title in ("Fato ou Fake: X é verdade", "A muralha é visível do espaço? - Brasil Escola", "Fakes News"):
            self.assertFalse(factcheck._DEBUNK_RE.search(title), title)

    def test_clean_title(self):
        from core import web
        glued = ("A muralha da China é visível do espaço? - Mundo EducaçãoA muralha da China é visível do espaço? "
                 "- Brasil EscolaDesmentido")
        self.assertEqual(web.clean_title(glued), "A muralha da China é visível do espaço? - Mundo Educação")
        long_title = " ".join(str(n) for n in range(200))
        self.assertLessEqual(len(web.clean_title(long_title)), web.TITLE_MAX)
        self.assertTrue(web.clean_title(long_title).endswith("…"))
        self.assertEqual(web.clean_title("  Curto  "), "Curto")

    def test_invalid_answers_are_inconclusive(self):
        for raw in (None, "", "não é json", "[1, 2]", json.dumps({"veredito": "TALVEZ", "resumo": "x"}),
                    json.dumps({"veredito": "FALSO", "fontes_contra": [1, 2]})):
            self.assertEqual(factcheck.parse_verdict(raw, 3)["verdict"], "INCONCLUSIVO", raw)

    def test_indices_are_validated(self):
        res = factcheck.parse_verdict(json.dumps({"veredito": "FALSO", "resumo": "Mito [1][2].",
                                                  "fontes_a_favor": [], "fontes_contra": [1, "2", 2, 9, "x"]}), 3)
        self.assertEqual(res["con"], [1, 2])
        self.assertEqual(res["verdict"], "FALSO")


class TestCheck(unittest.TestCase):
    def setUp(self):
        factcheck._cache.clear()

    def test_full_flow(self):
        search = FakeSearch(results("nasa.gov", "bbc.com"), results("aosfatos.org"))
        seen = {}

        def fake_verdict(claim, sources):
            seen["claim"], seen["sources"] = claim, sources
            return json.dumps({"veredito": "FALSO", "resumo": "É um mito [1][3].",
                               "fontes_a_favor": [], "fontes_contra": [1, 3]})

        answer = factcheck.check(f"isso é verdade: {CLAIM}?", search=search, read=read_stub,
                                 verdict_fn=fake_verdict, claim_llm=None)
        self.assertTrue(answer.startswith("**Veredito: ❌ FALSO**"))
        self.assertIn(f"> {CLAIM}", answer)
        self.assertIn("**Contra:** [1], [3]", answer)
        self.assertIn("**Fontes**", answer)
        self.assertEqual(seen["claim"], CLAIM)
        self.assertEqual(seen["sources"][0]["text"], "texto completo de nasa.gov")

        # 2ª vez: cache, sem nova busca
        again = factcheck.check(CLAIM, search=lambda q: 1 / 0, read=read_stub, verdict_fn=fake_verdict,
                                claim_llm=None)
        self.assertEqual(again, answer)

    def test_single_domain_is_inconclusive_without_llm(self):
        def no_llm(claim, sources):
            raise AssertionError("não devia chamar o modelo")
        answer = factcheck.check(CLAIM, search=FakeSearch(results("blog.com"), results("blog.com")),
                                 read=read_stub, verdict_fn=no_llm, claim_llm=None)
        self.assertIn("INCONCLUSIVO", answer)
        self.assertIn("fontes independentes", answer)

    def test_never_raises(self):
        def broken(query):
            raise RuntimeError("sem internet")
        self.assertIn("Não consegui checar", factcheck.check(CLAIM, search=broken, claim_llm=None))


class TestEntryPoints(unittest.TestCase):
    def test_skill_calls_check_with_phrase(self):
        from skills.web import fact_check
        with patch.object(factcheck, "check", return_value="veredito") as check:
            self.assertEqual(fact_check.execute(CLAIM, f"checa se {CLAIM}"), "veredito")
        check.assert_called_once_with(f"checa se {CLAIM}")

    def test_clip_checar(self):
        self.assertEqual(clipboard.resolve_action(None, "checar"), "factcheck")
        with patch.object(factcheck, "check", return_value="veredito") as check:
            self.assertEqual(clipboard.act("factcheck", CLAIM), "veredito")
        check.assert_called_once_with(CLAIM)


if __name__ == "__main__":
    unittest.main()
