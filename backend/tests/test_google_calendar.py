"""core.google_calendar + skill CALENDAR — token, eventos, formatação e 'em reunião'."""
import datetime
import unittest
import urllib.parse
from unittest.mock import patch

from tests._stubs import install

install()

import core.google_calendar as gc  # noqa: E402
from core.config import settings  # noqa: E402
from skills.productivity import calendar_agenda  # noqa: E402

D = datetime.datetime


def _ev(title, start, end, all_day=False):
    return {"title": title, "start": start, "end": end, "all_day": all_day}


class _Vault:
    """secrets_store em memória."""

    def __init__(self, data=None):
        self.data = {} if data is None else {gc.SECRET_NAME: data}

    def get(self, name):
        return self.data.get(name)

    def set(self, name, value):
        self.data[name] = value
        return True

    def delete(self, name):
        self.data.pop(name, None)


class _Base(unittest.TestCase):
    def setUp(self):
        self.vault = _Vault()
        self._ps = [patch.object(gc, "secrets_store", self.vault),
                    patch.object(settings, "GOOGLE_CLIENT_ID", "cid"),
                    patch.object(settings, "GOOGLE_CLIENT_SECRET", "csecret")]
        for p in self._ps:
            p.start()
        gc._busy_cache.update(at=0.0, value=False)

    def tearDown(self):
        for p in reversed(self._ps):
            p.stop()


class TestConfigAndUrl(_Base):
    def test_not_configured(self):
        with patch.object(settings, "GOOGLE_CLIENT_ID", ""):
            self.assertFalse(gc.is_configured())
            self.assertEqual(gc.connect(authorize=lambda *a: self.fail("não deveria abrir")), gc.NOT_CONFIGURED)

    def test_authorize_url_is_readonly_offline_pkce(self):
        url = gc.build_authorize_url("http://127.0.0.1:5000", "chall", "st")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(q["scope"], [gc.SCOPE])
        self.assertEqual(q["access_type"], ["offline"])
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["redirect_uri"], ["http://127.0.0.1:5000"])
        self.assertEqual(q["client_id"], ["cid"])


class TestConnect(_Base):
    def test_connect_stores_tokens_and_account(self):
        posts = []

        def post(url, data):
            posts.append(data)
            return {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600}

        with patch.object(gc, "_post", post), patch.object(gc, "_get", return_value={"id": "eu@gmail.com"}):
            msg = gc.connect(authorize=lambda build, t: ("CODE", "VER", "http://127.0.0.1:1"))
        self.assertIn("eu@gmail.com", msg)
        self.assertEqual(posts[0]["code_verifier"], "VER")
        self.assertEqual(posts[0]["client_secret"], "csecret")
        stored = self.vault.get(gc.SECRET_NAME)
        self.assertEqual(stored["refresh_token"], "r1")
        self.assertEqual(stored["account"], "eu@gmail.com")
        self.assertNotIn("expires_in", stored)
        self.assertTrue(gc.is_connected())

    def test_connect_cancelled(self):
        self.assertIn("não foi autorizada", gc.connect(authorize=lambda *a: None))
        self.assertFalse(gc.is_connected())

    def test_connect_without_refresh_token(self):
        with patch.object(gc, "_post", return_value={"access_token": "a"}):
            msg = gc.connect(authorize=lambda *a: ("C", "V", "R"))
        self.assertIn("refresh token", msg)
        self.assertFalse(gc.is_connected())

    def test_refresh_keeps_refresh_token(self):
        self.vault.data[gc.SECRET_NAME] = {"refresh_token": "r1", "access_token": "old", "expires_at": 0}
        with patch.object(gc, "_post", return_value={"access_token": "new", "expires_in": 3600}) as post:
            self.assertEqual(gc._access_token(), "new")
            self.assertEqual(gc._access_token(), "new")  # 2ª vez do cache
        post.assert_called_once()
        self.assertEqual(self.vault.get(gc.SECRET_NAME)["refresh_token"], "r1")

    def test_disconnect_deletes_secret(self):
        self.vault.data[gc.SECRET_NAME] = {"refresh_token": "r1"}
        with patch.object(gc, "_requests"):
            self.assertIn("desconectado", gc.disconnect())
        self.assertFalse(gc.is_connected())


class TestEvents(_Base):
    def test_parse_timed_and_all_day(self):
        timed = gc.parse_event({"summary": "Daily", "start": {"dateTime": "2026-11-09T12:00:00Z"},
                                "end": {"dateTime": "2026-11-09T12:30:00Z"}})
        self.assertFalse(timed["all_day"])
        expected = D(2026, 11, 9, 12, 0, tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
        self.assertEqual(timed["start"], expected)
        whole = gc.parse_event({"start": {"date": "2026-11-09"}, "end": {"date": "2026-11-10"}})
        self.assertTrue(whole["all_day"])
        self.assertEqual(whole["title"], "(sem título)")

    def test_events_skips_cancelled_and_asks_for_the_day(self):
        self.vault.data[gc.SECRET_NAME] = {"refresh_token": "r", "access_token": "a", "expires_at": 9e12}
        items = [{"summary": "A", "start": {"date": "2026-11-09"}, "end": {"date": "2026-11-10"}},
                 {"summary": "B", "status": "cancelled", "start": {"date": "2026-11-09"}}]
        with patch.object(gc, "_get", return_value={"items": items}) as get:
            result = gc.events(datetime.date(2026, 11, 9))
        self.assertEqual([e["title"] for e in result], ["A"])
        params = get.call_args.args[2]
        self.assertTrue(params["timeMin"].startswith("2026-11-09T00:00:00"))
        self.assertEqual(params["singleEvents"], "true")

    def test_format(self):
        items = [_ev("Feriado", D(2026, 11, 9), D(2026, 11, 10), True),
                 _ev("Daily", D(2026, 11, 9, 9), D(2026, 11, 9, 9, 15))]
        self.assertEqual(gc.format_events(items), "2 eventos hoje: dia inteiro: Feriado · 09:00 Daily")
        self.assertEqual(gc.format_events([], "amanhã"), "Agenda livre amanhã.")

    def test_summary_none_when_not_connected(self):
        self.assertIsNone(gc.summary())

    def test_busy_and_next(self):
        items = [_ev("Feriado", D(2026, 11, 9), D(2026, 11, 10), True),
                 _ev("Reunião", D(2026, 11, 9, 10), D(2026, 11, 9, 11)),
                 _ev("Almoço", D(2026, 11, 9, 12), D(2026, 11, 9, 13))]
        self.assertTrue(gc.busy_now(items, D(2026, 11, 9, 10, 30)))
        self.assertFalse(gc.busy_now(items, D(2026, 11, 9, 11, 30)))
        self.assertEqual(gc.next_event(D(2026, 11, 9, 10, 30), items)["title"], "Almoço")

    def test_is_busy_cached_and_safe(self):
        self.vault.data[gc.SECRET_NAME] = {"refresh_token": "r"}
        now = D(2026, 11, 9, 10, 30)
        calls = []

        def events(day):
            calls.append(day)
            return [_ev("Reunião", D(2026, 11, 9, 10), D(2026, 11, 9, 11))]

        clock = iter([1000.0, 1000.0, 1010.0]).__next__
        with patch.object(gc, "events", events):
            self.assertTrue(gc.is_busy(now, clock=clock))
            self.assertTrue(gc.is_busy(now, clock=clock))
        self.assertEqual(len(calls), 1)
        gc._busy_cache.update(at=0.0)
        with patch.object(gc, "events", side_effect=gc.CalendarError("x")):
            self.assertFalse(gc.is_busy(now, clock=lambda: 5000.0))


class TestSkill(_Base):
    def test_resolve_day(self):
        today = datetime.date(2026, 11, 9)  # segunda
        self.assertEqual(gc.resolve_day("o que tenho amanhã", today),
                         (datetime.date(2026, 11, 10), "amanhã"))
        self.assertEqual(gc.resolve_day("e na sexta?", today),
                         (datetime.date(2026, 11, 13), "na sexta"))
        self.assertEqual(gc.resolve_day("sábado", today)[1], "no sábado")
        self.assertEqual(gc.resolve_day("minha agenda", today), (today, "hoje"))
        self.assertEqual(gc.resolve_day("qual a próxima reunião", today)[0], "next")

    def test_execute_not_connected(self):
        self.assertEqual(calendar_agenda.execute("", "minha agenda"), gc.NOT_CONNECTED)

    def test_execute_lists_day(self):
        self.vault.data[gc.SECRET_NAME] = {"refresh_token": "r"}
        with patch.object(gc, "events", return_value=[]):
            self.assertEqual(calendar_agenda.execute("amanhã", "o que tenho amanhã"), "Agenda livre amanhã.")

    def test_execute_next(self):
        self.vault.data[gc.SECRET_NAME] = {"refresh_token": "r"}
        with patch.object(gc, "next_event", return_value=_ev("Daily", D(2026, 11, 9, 9), None)):
            self.assertIn("**Daily** às 09:00", calendar_agenda.execute("", "próxima reunião"))


if __name__ == "__main__":
    unittest.main()
