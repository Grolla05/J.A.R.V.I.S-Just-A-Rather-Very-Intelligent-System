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


class TestHeadlines(unittest.TestCase):
    DAY = datetime.date(2026, 11, 10)

    def _search(self, query, max_results=2):
        site = query.split("site:")[-1]
        return [{"title": f"{site} 1"}, {"title": f"{site} 2"}]

    def test_one_per_source_and_query_shape(self):
        calls = []

        def search(query, max_results=2):
            calls.append(query)
            return self._search(query)

        out = news.headlines(["G1", "BBC"], limit=4, search=search, today=self.DAY)
        self.assertEqual(sorted(out[:2]), ["bbc.com 1", "g1.globo.com 1"])  # 1ª rodada: uma de cada
        self.assertEqual(len(out), 4)
        self.assertIn("notícias hoje site:g1.globo.com", calls)

    def test_rotates_start_by_day(self):
        sources = ["G1", "BBC", "CNN"]
        first = [news.headlines(sources, limit=1, search=self._search, today=self.DAY + datetime.timedelta(d))[0]
                 for d in range(3)]
        self.assertEqual(len(set(first)), 3)

    def test_failing_source_is_skipped(self):
        def search(query, max_results=2):
            if "bbc" in query:
                raise RuntimeError("caiu")
            return self._search(query)

        out = news.headlines(["BBC", "G1"], limit=2, search=search, today=self.DAY)
        self.assertEqual(out, ["g1.globo.com 1", "g1.globo.com 2"])

    def test_doi_source_uses_crossref(self):
        with patch.object(news, "doi_articles", return_value=["Paper X (doi.org/10.1/x)"]) as doi:
            out = news.headlines(["DOI"], limit=2, search=self._search, today=self.DAY)
        doi.assert_called_once()
        self.assertEqual(out, ["Paper X (doi.org/10.1/x)"])


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
        with patch.object(news, "headlines", return_value=["Manchete G1"]) as h:
            self.assertEqual(briefing._news(limit=3), ["Manchete G1"])
        h.assert_called_once_with(limit=3)


if __name__ == "__main__":
    unittest.main()
