"""services.live_context — agenda real no prompt do chat (fim da agenda inventada)."""
import datetime
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

import core.google_calendar as gc  # noqa: E402
import services.chat as chat  # noqa: E402
import services.live_context as lc  # noqa: E402

D = datetime.datetime
MONDAY = datetime.date(2026, 11, 9)


class FakeCalendar:
    """Mesma interface usada do core.google_calendar."""
    WEEKDAYS = gc.WEEKDAYS
    resolve_day = staticmethod(gc.resolve_day)

    def __init__(self, items=None, connected=True, configured=True, error=None):
        self.items, self.connected, self.configured, self.error = items or [], connected, configured, error
        self.asked = []

    def is_configured(self):
        return self.configured

    def is_connected(self):
        return self.connected

    def events(self, day):
        self.asked.append(day)
        if self.error:
            raise self.error
        return self.items


class TestDetection(unittest.TestCase):
    def test_calendar_questions(self):
        for q in ("JARVIS qual evento está marcado para amanhã na minha agenda",
                  "o que tenho hoje?", "tenho reunião na sexta?", "minha agenda de amanhã",
                  "estou livre à tarde?", "quais compromissos tenho", "Como está meu dia"):
            self.assertTrue(lc.is_calendar_question(q), q)

    def test_other_questions(self):
        for q in ("explique recursão em python", "qual a capital da França", "toca uma música"):
            self.assertFalse(lc.is_calendar_question(q), q)


class TestCalendarContext(unittest.TestCase):
    def test_injects_real_events_for_the_asked_day(self):
        cal = FakeCalendar([
            {"title": "Daily", "start": D(2026, 11, 10, 9), "end": D(2026, 11, 10, 9, 15), "all_day": False},
            {"title": "Feriado", "start": D(2026, 11, 10), "end": D(2026, 11, 11), "all_day": True},
        ])
        ctx = lc.calendar_context("qual evento está marcado para amanhã na minha agenda", MONDAY, cal)
        self.assertEqual(cal.asked, [datetime.date(2026, 11, 10)])
        self.assertIn("CONECTADA", ctx)
        self.assertIn("amanhã (10/11/2026, terça-feira)", ctx)
        self.assertIn("- 09:00–09:15 Daily", ctx)
        self.assertIn("- dia inteiro: Feriado", ctx)
        self.assertIn("PROIBIDO inventar", ctx)

    def test_empty_day_says_free(self):
        ctx = lc.calendar_context("o que tenho hoje", MONDAY, FakeCalendar([]))
        self.assertIn("(nenhum evento)", ctx)

    def test_not_connected_never_lists_events(self):
        cal = FakeCalendar(connected=False)
        ctx = lc.calendar_context("minha agenda de amanhã", MONDAY, cal)
        self.assertIn("NÃO CONECTADA", ctx)
        self.assertIn("/config → INTEGRAÇÕES", ctx)
        self.assertEqual(cal.asked, [])

    def test_api_error_is_reported_not_invented(self):
        ctx = lc.calendar_context("minha agenda", MONDAY, FakeCalendar(error=gc.CalendarError("Google respondeu 503.")))
        self.assertIn("INDISPONÍVEL AGORA", ctx)

    def test_unrelated_message_adds_nothing(self):
        cal = FakeCalendar()
        self.assertEqual(lc.calendar_context("explique recursão", MONDAY, cal), "")
        self.assertEqual(cal.asked, [])

    def test_build_never_raises(self):
        with patch.object(lc, "calendar_context", side_effect=RuntimeError("x")):
            self.assertEqual(lc.build("minha agenda"), "")


class TestChatUsesContext(unittest.TestCase):
    def test_context_reaches_the_model_with_low_temperature(self):
        seen = {}

        def fake_stream(messages, temperature):
            seen.update(messages=messages, temperature=temperature)
            yield "ok"

        with patch.object(chat, "query_ollama_stream", fake_stream), \
             patch.object(chat, "get_session_history_for_ai", return_value=[]), \
             patch.object(chat.state, "sys_monitor") as mon:
            mon.get_realtime_context.return_value = "cpu 5%"
            list(chat.ask_local_ai_stream("o que tenho amanhã", live_context="[AGENDA DO USUÁRIO] - 09:00 Daily"))
        systems = [m["content"] for m in seen["messages"] if m["role"] == "system"]
        self.assertTrue(any("09:00 Daily" in c for c in systems))
        self.assertEqual(seen["messages"][-1], {"role": "user", "content": "o que tenho amanhã"})
        self.assertEqual(seen["temperature"], 0.1)


if __name__ == "__main__":
    unittest.main()
