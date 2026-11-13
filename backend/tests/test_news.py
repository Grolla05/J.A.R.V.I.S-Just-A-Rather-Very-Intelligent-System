"""core/news.py — fontes de notícias escolhidas pelo usuário (/config → SISTEMA)."""
import datetime
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import briefing, news


class FakeDB:
    def __init__(self, value=None):
        self.data = {} if value is None else {news.CONFIG_KEY: value}

    def get_config(self, key):
        return self.data.get(key)

    def save_config(self, key, value):
        self.data[key] = value


class TestParse(unittest.TestCase):
    def test_split_trim_dedupe(self):
        self.assertEqual(news.parse_sources(" G1 ,BBC,, g1 ,  New   York Times "), ["G1", "BBC", "New York Times"])

    def test_empty_falls_back_to_default(self):
        self.assertEqual(news.normalize("  , ,"), news.DEFAULT_SOURCES)
        self.assertIn("SciELO", news.parse_sources(news.DEFAULT_SOURCES))

    def test_limit(self):
        self.assertEqual(len(news.parse_sources(",".join(f"f{i}" for i in range(30)))), news.MAX_SOURCES)

    def test_resolve(self):
        self.assertEqual(news.resolve("G1"), ("site", "g1.globo.com"))
        self.assertEqual(news.resolve("Google Acadêmico"), ("site", "scholar.google.com"))
        self.assertEqual(news.resolve("wsj"), ("site", "wsj.com"))
        self.assertEqual(news.resolve("https://Folha.uol.com.br/"), ("site", "folha.uol.com.br"))
        self.assertEqual(news.resolve("Artigos com DOI"), ("doi", None))
        self.assertEqual(news.resolve("Estadão"), ("query", "Estadão notícias hoje"))


class TestPersistence(unittest.TestCase):
    def test_get_default_and_save_normalized(self):
        db = FakeDB()
        self.assertEqual(news.get_sources(db), news.DEFAULT_SOURCES)
        self.assertEqual(news.save_sources("bbc ,  G1,bbc", db), "bbc, G1")
        self.assertEqual(news.get_sources(db), "bbc, G1")

    def test_db_error_uses_default(self):
        db = MagicMock()
        db.get_config.side_effect = RuntimeError("sem banco")
        self.assertEqual(news.get_sources(db), news.DEFAULT_SOURCES)


UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 13, 12, tzinfo=UTC)


def _rss(*items):
    body = "".join(f"<item><title>{t}</title><pubDate>{d}</pubDate></item>" for t, d in items)
    return MagicMock(status_code=200, content=f"<rss><channel>{body}</channel></rss>".encode())


class TestRelevance(unittest.TestCase):
    def test_weights(self):
        self.assertGreater(news.relevance("Morre o ator Fulano aos 80 anos"), 0)
        self.assertGreater(news.relevance("Ibovespa despenca e dólar dispara"),
                           news.relevance("Presidente visita feira"))
        self.assertEqual(news.relevance("Receita de bolo de cenoura"), 0)

    def test_pick_most_relevant_then_newest(self):
        titles = [("Festival de música agita a cidade", NOW), ("Presidente visita feira agrícola", NOW),
                  ("Morre cantor famoso aos 70", NOW)]
        self.assertEqual(news.pick_relevant(titles, now=NOW), "Morre cantor famoso aos 70")
        tie = [("Primeira notícia comum", NOW), ("Segunda notícia comum", NOW)]
        self.assertEqual(news.pick_relevant(tie, now=NOW), "Primeira notícia comum")

    def test_old_items_ignored(self):
        old = NOW - datetime.timedelta(days=5)
        self.assertIsNone(news.pick_relevant([("Morre alguém", old)], now=NOW))
        self.assertEqual(news.pick_relevant([("Sem data", None)], now=NOW), "Sem data")

    def test_portal_titles(self):
        self.assertTrue(news._is_portal_title("g1 - O portal de notícias da Globo", "G1", "g1.globo.com"))
        self.assertTrue(news._is_portal_title("U.S. News - WSJ.com", "WSJ", "wsj.com"))
        self.assertTrue(news._is_portal_title("Google Scholar", "Google Acadêmico", "scholar.google.com"))
        self.assertTrue(news._is_portal_title("The New York Times, US News, World News and Videos",
                                              "New York Times", "nytimes.com"))
        self.assertFalse(news._is_portal_title("Morre ex-presidente aos 90 anos - g1", "G1", "g1.globo.com"))
        self.assertTrue(news._is_portal_title("Scientific Electronic Library Online", "SciELO", "scielo.org"))

    def test_clean_title_strips_portal_suffix(self):
        self.assertEqual(news.clean_title("Mercado recua - WSJ", "Wall Street Journal", "wsj.com"), "Mercado recua")
        self.assertEqual(news.clean_title("Chuva forte | g1", "G1", "g1.globo.com"), "Chuva forte")
        self.assertEqual(news.clean_title("Placar: 2 - 1", "G1", "g1.globo.com"), "Placar: 2 - 1")


class TestFeed(unittest.TestCase):
    def test_parses_rss_and_dates(self):
        get = MagicMock(return_value=_rss(("Título  A", "Fri, 13 Nov 2026 10:00:00 GMT")))
        out = news.fetch_feed("http://x/rss", get=get)
        self.assertEqual(out[0][0], "Título A")
        self.assertEqual(out[0][1], datetime.datetime(2026, 11, 13, 10, tzinfo=UTC))

    def test_error_or_bad_xml_returns_empty(self):
        self.assertEqual(news.fetch_feed("u", get=MagicMock(side_effect=OSError("off"))), [])
        self.assertEqual(news.fetch_feed("u", get=MagicMock(return_value=MagicMock(status_code=200,
                                                                                   content=b"<html"))), [])


class TestHeadlines(unittest.TestCase):
    def _search(self, query, max_results=5):
        site = query.split("site:")[-1].split()[0]
        return [{"title": f"{site} - Portal de notícias"}, {"title": f"Ministro anuncia plano para {site}"}]

    def test_one_per_source_in_order_skipping_portal_titles(self):
        out = news.headlines(["SciELO", "Estadão"], search=self._search)
        self.assertEqual(out, [("SciELO", "Ministro anuncia plano para scielo.org"),
                               ("Estadão", "Ministro anuncia plano para Estadão")])

    def test_feed_first_then_search_fallback(self):
        fresh = datetime.datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
        get = MagicMock(return_value=_rss(("Chuva fecha estradas", fresh), ("Morre jornalista aos 88", fresh)))
        search = MagicMock(side_effect=self._search)
        out = news.headlines(["G1"], search=search, get=get)
        self.assertEqual(out, [("G1", "Morre jornalista aos 88")])
        search.assert_not_called()
        undated = MagicMock(return_value=MagicMock(
            status_code=200, content=b"<rss><channel><item><title>Sem data</title></item></channel></rss>"))
        self.assertEqual(news.headlines(["G1"], search=search, get=undated),
                         [("G1", "Ministro anuncia plano para g1.globo.com")])
        stale = MagicMock(return_value=_rss(("Velha", "Mon, 01 Jan 2024 10:00:00 GMT")))
        out = news.headlines(["G1"], search=search, get=stale)
        self.assertEqual(out, [("G1", "Ministro anuncia plano para g1.globo.com")])

    def test_failing_source_is_skipped(self):
        def search(query, max_results=5):
            if "scielo" in query:
                raise RuntimeError("caiu")
            return self._search(query)

        out = news.headlines(["SciELO", "Estadão"], search=search)
        self.assertEqual([s for s, _ in out], ["Estadão"])

    def test_doi_source_uses_crossref(self):
        with patch.object(news, "doi_articles", return_value=["Paper X (doi.org/10.1/x)"]) as doi:
            out = news.headlines(["DOI"], search=self._search)
        doi.assert_called_once_with(limit=1)
        self.assertEqual(out, [("DOI", "Paper X (doi.org/10.1/x)")])


class TestCrossref(unittest.TestCase):
    def test_only_items_with_doi_and_title(self):
        res = MagicMock(status_code=200)
        res.json.return_value = {"message": {"items": [
            {"DOI": "10.1/a", "title": ["Artigo  A"]},
            {"title": ["Sem DOI"]},
            {"DOI": "10.1/b", "title": []},
        ]}}
        get = MagicMock(return_value=res)
        out = news.doi_articles(limit=3, today=datetime.date(2026, 11, 10), get=get)
        self.assertEqual(out, ["Artigo A (doi.org/10.1/a)"])
        self.assertIn("from-pub-date:2026-11-09", get.call_args.kwargs["params"]["filter"])

    def test_error_returns_empty(self):
        self.assertEqual(news.doi_articles(get=MagicMock(side_effect=OSError("off"))), [])


class TestBriefingUsesSources(unittest.TestCase):
    def test_news_goes_through_sources(self):
        with patch.object(news, "headlines", return_value=[("G1", "Manchete")]) as h:
            self.assertEqual(briefing._news(), [("G1", "Manchete")])
        h.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
