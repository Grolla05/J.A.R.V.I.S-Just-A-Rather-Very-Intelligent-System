"""Agenda por período: dia, semana, fim de semana, mês e ano (skill CALENDAR e contexto do Chat).

Bug corrigido: "qual compromisso eu tenho essa semana?" respondia "Agenda livre hoje."
porque `resolve_day` só conhecia dias.
"""
import datetime
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

import core.google_calendar as gc  # noqa: E402
import services.live_context as lc  # noqa: E402
from skills.productivity import calendar_agenda  # noqa: E402

D, Day = datetime.datetime, datetime.date
MONDAY = Day(2026, 11, 23)      # segunda
WEDNESDAY = Day(2026, 11, 25)   # quarta


def _ev(title, start, end=None, all_day=False):
    return {"title": title, "start": start, "end": end, "all_day": all_day, "id": title, "location": ""}


class TestResolvePeriod(unittest.TestCase):
    def check(self, text, today, kind, start, end, label=None):
        p = gc.resolve_period(text, today)
        self.assertEqual((p["kind"], p["start"], p["end"]), (kind, start, end), text)
        if label:
            self.assertEqual(p["label"], label)

    def test_this_week_from_today_to_sunday(self):
        self.check("qual compromisso eu tenho essa semana?", WEDNESDAY, "range", WEDNESDAY, Day(2026, 11, 30),
                   "nesta semana")
        self.check("minha agenda da semana", MONDAY, "range", MONDAY, Day(2026, 11, 30))
        self.check("o que tenho esta semana", Day(2026, 11, 29), "range", Day(2026, 11, 29), Day(2026, 11, 30))

    def test_next_week(self):
        for text in ("e na próxima semana?", "compromissos da semana que vem"):
            self.check(text, WEDNESDAY, "range", Day(2026, 11, 30), Day(2026, 12, 7), "na próxima semana")

    def test_weekend(self):
        self.check("tenho algo no fim de semana?", WEDNESDAY, "range", Day(2026, 11, 28), Day(2026, 11, 30),
                   "no fim de semana")
        self.check("e nesse final de semana", Day(2026, 11, 29), "range", Day(2026, 11, 29), Day(2026, 11, 30))

    def test_month(self):
        self.check("minha agenda do mês", WEDNESDAY, "range", WEDNESDAY, Day(2026, 12, 1), "neste mês")
        self.check("o que tenho no próximo mês", WEDNESDAY, "range", Day(2026, 12, 1), Day(2027, 1, 1),
                   "no próximo mês")
        self.check("compromissos do mês que vem", Day(2026, 12, 10), "range", Day(2027, 1, 1), Day(2027, 2, 1))

    def test_year(self):
        self.check("eventos deste ano", WEDNESDAY, "range", WEDNESDAY, Day(2027, 1, 1), "neste ano")
        self.check("o que tenho marcado no ano que vem", WEDNESDAY, "range", Day(2027, 1, 1), Day(2028, 1, 1),
                   "no próximo ano")

    def test_days_still_work(self):
        self.check("o que tenho amanhã", MONDAY, "day", Day(2026, 11, 24), Day(2026, 11, 25), "amanhã")
        self.check("minha agenda", MONDAY, "day", MONDAY, Day(2026, 11, 24), "hoje")
        self.check("e na sexta?", MONDAY, "day", Day(2026, 11, 27), Day(2026, 11, 28))
        self.assertEqual(gc.resolve_period("qual a próxima reunião", MONDAY)["kind"], "next")

    def test_words_inside_other_words_do_not_count(self):
        self.check("anota no meu plano de hoje", MONDAY, "day", MONDAY, Day(2026, 11, 24))   # "ano" em "anota"
        self.check("compromissos da semana", MONDAY, "range", MONDAY, Day(2026, 11, 30))     # "próxim" ausente


class TestRangeApi(unittest.TestCase):
    def setUp(self):
        self._p = patch.object(gc, "_access_token", return_value="tok")
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_events_range_paginates_and_bounds(self):
        page1 = {"items": [{"summary": "A", "start": {"date": "2026-11-25"}, "end": {"date": "2026-11-26"}}],
                 "nextPageToken": "p2"}
        page2 = {"items": [{"summary": "B", "start": {"dateTime": "2026-11-27T10:00:00-03:00"},
                            "end": {"dateTime": "2026-11-27T11:00:00-03:00"}},
                           {"summary": "X", "status": "cancelled", "start": {"date": "2026-11-27"}}]}
        with patch.object(gc, "_get", side_effect=[page1, page2]) as get:
            items = gc.events_range(WEDNESDAY, Day(2026, 11, 30))
        self.assertEqual([e["title"] for e in items], ["A", "B"])
        first, second = get.call_args_list
        self.assertTrue(first.args[2]["timeMin"].startswith("2026-11-25T00:00:00"))
        self.assertTrue(first.args[2]["timeMax"].startswith("2026-11-30T00:00:00"))
        self.assertEqual(second.args[2]["pageToken"], "p2")

    def test_events_range_stops_at_limit(self):
        page = {"items": [{"summary": f"E{i}", "start": {"date": "2026-11-25"}} for i in range(5)],
                "nextPageToken": "more"}
        with patch.object(gc, "_get", return_value=page) as get:
            items = gc.events_range(WEDNESDAY, Day(2027, 1, 1), limit=7)
        self.assertEqual(len(items), 7)
        self.assertEqual(get.call_count, 2)

    def test_events_day_uses_range(self):
        with patch.object(gc, "events_range", return_value=[]) as rng:
            gc.events(MONDAY)
        rng.assert_called_once_with(MONDAY, Day(2026, 11, 24), limit=gc.MAX_EVENTS)


class TestFormatRange(unittest.TestCase):
    def test_grouped_by_day_with_dates(self):
        items = [_ev("Daily", D(2026, 11, 25, 9), D(2026, 11, 25, 9, 15)),
                 _ev("Dentista", D(2026, 11, 25, 14)),
                 _ev("Feriado", D(2026, 11, 27), D(2026, 11, 28), True)]
        text = gc.format_range(items, "nesta semana", WEDNESDAY, Day(2026, 11, 30))
        self.assertIn("3 eventos nesta semana (25/11 a 29/11)", text)
        self.assertIn("**qua 25/11** · 09:00 Daily · 14:00 Dentista", text)
        self.assertIn("**sex 27/11** · dia inteiro: Feriado", text)

    def test_ongoing_all_day_counts_from_range_start(self):
        items = [_ev("Férias", D(2026, 11, 20), D(2026, 12, 2), True)]
        text = gc.format_range(items, "nesta semana", WEDNESDAY, Day(2026, 11, 30))
        self.assertIn("**qua 25/11** · dia inteiro: Férias", text)

    def test_empty_and_long(self):
        self.assertEqual(gc.format_range([], "neste mês", WEDNESDAY, Day(2026, 12, 1)),
                         "Agenda livre neste mês (25/11 a 30/11).")
        many = [_ev(f"E{i}", D(2026, 11, 25) + datetime.timedelta(days=i, hours=9)) for i in range(60)]
        text = gc.format_range(many, "neste ano", WEDNESDAY, Day(2027, 1, 1))
        self.assertIn("60 eventos", text)
        self.assertIn("e mais", text)


class TestSkillAndContext(unittest.TestCase):
    def setUp(self):
        self._ps = [patch.object(gc, "is_configured", return_value=True),
                    patch.object(gc, "is_connected", return_value=True)]
        for p in self._ps:
            p.start()

    def tearDown(self):
        for p in reversed(self._ps):
            p.stop()

    def test_skill_week_question_from_screenshot(self):
        week = [_ev("Reunião de equipe", D(2026, 11, 26, 10))]
        real = gc.resolve_period
        with patch.object(gc, "events_range", return_value=week) as rng, \
             patch.object(gc, "resolve_period", side_effect=lambda t, today=None: real(t, WEDNESDAY)):
            text = calendar_agenda.execute(None, "JARVIS qual compromisso eu tenho essa semana?")
        rng.assert_called_once_with(WEDNESDAY, Day(2026, 11, 30))
        self.assertIn("Reunião de equipe", text)
        self.assertNotIn("hoje", text)

    def test_skill_day_unchanged(self):
        with patch.object(gc, "events", return_value=[]):
            self.assertEqual(calendar_agenda.execute("amanhã", "o que tenho amanhã"), "Agenda livre amanhã.")

    def test_chat_context_uses_the_whole_week(self):
        week = [_ev("Reunião de equipe", D(2026, 11, 26, 10), D(2026, 11, 26, 11))]
        with patch.object(gc, "events_range", return_value=week) as rng:
            block = lc.calendar_context("qual compromisso eu tenho essa semana?", today=WEDNESDAY, calendar=gc)
        rng.assert_called_once_with(WEDNESDAY, Day(2026, 11, 30))
        self.assertIn("nesta semana", block)
        self.assertIn("qui 26/11 10:00–11:00 Reunião de equipe", block)


if __name__ == "__main__":
    unittest.main()
