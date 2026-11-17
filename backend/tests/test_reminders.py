"""services.reminders — avisos da agenda, deslocamento, frase e lembretes por pedido.
Sem Google, sem Ollama, sem rede: relógio fixo, agenda/rota/LLM de mentira e SQLite temporário."""
import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from tests._stubs import install

install()

import core.database as database  # noqa: E402
import core.google_calendar as gc  # noqa: E402
from core.config import settings  # noqa: E402
from services import reminders  # noqa: E402

NOW = datetime(2026, 11, 16, 12, 0)
HOME = {"lat": -23.5, "lon": -46.6, "label": "Casa"}
FGV = {"lat": -23.56, "lon": -46.65, "label": "FGV"}


def ev(title="Prova de Cálculo", start=None, minutes=120, location="", all_day=False, id_="e1"):
    start = start or NOW + timedelta(minutes=minutes)
    return {"title": title, "start": start, "end": start + timedelta(hours=1), "all_day": all_day,
            "id": id_, "location": location}


class FakeTraffic:
    def __init__(self, home=HOME, places=None, geocoded=FGV, route_minutes=35):
        self.home, self.places, self.geocoded, self.route_minutes = home, places or {}, geocoded, route_minutes
        self.geocode_calls, self.route_calls = [], []

    def get_place(self, kind):
        return self.home if kind == "casa" else self.places.get(kind)

    def list_places(self):
        return {**({"casa": self.home} if self.home else {}), **self.places}

    @staticmethod
    def tag_label(tag):
        return tag.replace("_", " ")

    def geocode(self, address):
        self.geocode_calls.append(address)
        return self.geocoded

    def route(self, a, b):
        self.route_calls.append((a, b))
        return {"minutes": self.route_minutes, "typical": None, "source": "OSRM"} if self.route_minutes else None


class FakeCalendar:
    def __init__(self, items):
        self.items, self.asked = items, []

    def upcoming(self, hours, now):
        self.asked.append((hours, now))
        return self.items


class DbCase(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path = path
        self._orig = settings.DB_PATH
        settings.DB_PATH = Path(path)
        self.db = database.DatabaseManager()
        self._patch = patch.object(reminders, "db", self.db)
        self._patch.start()
        reminders._travel_cache.clear()

    def tearDown(self):
        self._patch.stop()
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass


class TestHumanize(unittest.TestCase):
    def test_cases(self):
        for minutes, text in ((120, "2 horas"), (60, "1 hora"), (90, "1 hora e 30 minutos"),
                              (45, "45 minutos"), (1, "1 minuto"), (0, "0 minutos"), (125, "2 horas e 5 minutos")):
            self.assertEqual(reminders.humanize(minutes), text)


class TestPlanAndDue(unittest.TestCase):
    def _due(self, events, now=NOW, fired=None, lead=120, final=15, travel=None):
        return reminders.due(now, events, fired or {}, lead, final, (lambda e: travel) if travel else None)

    def test_plan_without_route_has_lead_and_final(self):
        plan = dict(reminders.plan_event(ev(), 120, 15))
        self.assertEqual(plan, {"lead": NOW, "final": NOW + timedelta(minutes=105)})

    def test_plan_with_route_replaces_final_with_leave(self):
        plan = dict(reminders.plan_event(ev(), 120, 15, travel_min=35))
        # sair às 13:15 (14:00 − 35 − 10 de folga); avisa 15 min antes
        self.assertEqual(plan["leave"], NOW + timedelta(minutes=60))
        self.assertNotIn("final", plan)

    def test_all_day_and_missing_start_have_no_plan(self):
        self.assertEqual(reminders.plan_event(ev(all_day=True), 120, 15), [])
        self.assertEqual(reminders.plan_event({"title": "x", "start": None, "all_day": False}, 120, 15), [])

    def test_lead_fires_two_hours_before_once(self):
        found, keys = self._due([ev(minutes=120)])
        self.assertEqual([(f["kind"], f["minutes"]) for f in found], [("lead", 120)])
        again, _ = self._due([ev(minutes=120)], fired=dict.fromkeys(keys, "2026-11-16"))
        self.assertEqual(again, [])

    def test_nothing_before_the_lead_time(self):
        self.assertEqual(self._due([ev(minutes=121)])[0], [])

    def test_late_lead_within_grace_uses_real_minutes(self):
        found, _ = self._due([ev(minutes=100)])  # evento criado há pouco: o LEAD "venceu" há 20 min
        self.assertEqual([(f["kind"], f["minutes"]) for f in found], [("lead", 100)])

    def test_lead_too_late_is_dropped_and_final_takes_over(self):
        self.assertEqual(self._due([ev(minutes=80)])[0], [])       # LEAD 40 min atrasado
        found, _ = self._due([ev(minutes=15)])
        self.assertEqual([f["kind"] for f in found], ["final"])

    def test_two_due_at_once_emit_only_the_closest_and_mark_both(self):
        found, keys = self._due([ev(minutes=12)], lead=30, final=15)
        self.assertEqual([f["kind"] for f in found], ["final"])
        self.assertEqual(len(keys), 2)

    def test_leave_warning_carries_travel(self):
        travel = {"minutes": 35, "dest": "FGV"}
        found, _ = self._due([ev(minutes=60)], fired={"e1|" + ev(minutes=60)["start"].isoformat() + "|lead": "x"},
                             travel=travel)
        self.assertEqual([(f["kind"], f["travel"]) for f in found], [("leave", travel)])

    def test_rescheduled_event_rearms(self):
        found, keys = self._due([ev(minutes=120)])
        moved = ev(start=NOW + timedelta(minutes=180))
        later = NOW + timedelta(minutes=60)
        again, _ = self._due([moved], now=later, fired=dict.fromkeys(keys, "2026-11-16"))
        self.assertEqual([f["kind"] for f in again], ["lead"])

    def test_started_all_day_and_disabled_are_ignored(self):
        self.assertEqual(self._due([ev(minutes=-5), ev(all_day=True, id_="e2")])[0], [])
        self.assertEqual(self._due([ev(minutes=120)], lead=0, final=0)[0], [])

    def test_route_only_asked_inside_horizon(self):
        calls = []
        reminders.due(NOW, [ev(minutes=600)], {}, 120, 15, lambda e: calls.append(e))
        self.assertEqual(calls, [])

    def test_travel_error_falls_back_to_final(self):
        def boom(_event):
            raise RuntimeError("sem rede")
        found, _ = reminders.due(NOW, [ev(minutes=15)], {}, 120, 15, boom)
        self.assertEqual([f["kind"] for f in found], ["final"])


class TestTravel(DbCase):
    def test_geocodes_event_location_and_caches_it(self):
        traffic = FakeTraffic()
        event = ev(location="Av. 9 de Julho, 2029, São Paulo")
        self.assertEqual(reminders.travel_minutes(event, traffic), {"minutes": 35, "dest": "Av. 9 de Julho"})
        reminders._travel_cache.clear()
        reminders.travel_minutes(event, traffic)
        self.assertEqual(len(traffic.geocode_calls), 1)  # 2ª vez veio do cache no banco
        self.assertEqual(traffic.route_calls[0], (HOME, FGV))

    def test_geocode_failure_is_not_cached(self):
        """Timeout do Nominatim (None) não pode virar "endereço inexistente" para sempre."""
        traffic = FakeTraffic(geocoded=None)
        event = ev(location="Av. Paulista, 1578, São Paulo", id_="t")
        self.assertIsNone(reminders.travel_minutes(event, traffic))
        reminders._travel_cache.clear()
        traffic.geocoded = FGV
        self.assertEqual(reminders.travel_minutes(event, traffic)["minutes"], 35)
        self.assertEqual(len(traffic.geocode_calls), 2)

    def test_saved_place_in_title_wins_over_geocoding(self):
        traffic = FakeTraffic(places={"faculdade": FGV})
        result = reminders.travel_minutes(ev(title="Prova na faculdade"), traffic)
        self.assertEqual(result, {"minutes": 35, "dest": "faculdade"})
        self.assertEqual(traffic.geocode_calls, [])

    def test_none_without_home_location_route_or_when_online(self):
        cases = (
            (FakeTraffic(home=None), ev(location="Rua A, 1")),
            (FakeTraffic(), ev(location="")),
            (FakeTraffic(), ev(location="https://meet.google.com/abc-defg-hij", id_="m")),
            (FakeTraffic(geocoded=None), ev(location="Lugar que não existe", id_="g")),
            (FakeTraffic(route_minutes=0), ev(location="Rua B, 2", id_="r")),
        )
        for traffic, event in cases:
            reminders._travel_cache.clear()
            with self.subTest(location=event["location"]):
                self.assertIsNone(reminders.travel_minutes(event, traffic))

    def test_result_is_cached_in_memory(self):
        traffic = FakeTraffic()
        clock = iter([0.0, 10.0, 5000.0, 5000.0]).__next__  # grava · acerta · vence · regrava
        event = ev(location="Rua C, 3")
        reminders.travel_minutes(event, traffic, clock=clock)
        reminders.travel_minutes(event, traffic, clock=clock)
        self.assertEqual(len(traffic.route_calls), 1)
        reminders.travel_minutes(event, traffic, clock=clock)  # TTL vencido
        self.assertEqual(len(traffic.route_calls), 2)


class TestPhrase(unittest.TestCase):
    EVENT = ev(location="FGV, São Paulo")

    def test_fallbacks(self):
        self.assertEqual(reminders.fallback_phrase("lead", self.EVENT, 120),
                         "Senhor, em 2 horas, às 14:00, o senhor tem Prova de Cálculo em FGV.")
        self.assertEqual(reminders.fallback_phrase("final", ev(), 15),
                         "Senhor, Prova de Cálculo começa em 15 minutos, às 14:00.")
        leave = reminders.fallback_phrase("leave", self.EVENT, 60, {"minutes": 35, "dest": "FGV"})
        self.assertIn("saia em 15 minutos", leave)
        self.assertIn("35 minutos de trajeto até FGV", leave)
        self.assertIn("saia agora", reminders.fallback_phrase("leave", self.EVENT, 40, {"minutes": 35, "dest": "FGV"}))

    def test_model_sentence_is_used_when_it_keeps_the_time(self):
        seen = []

        def query(messages, temperature, timeout):
            seen.append((messages[0]["content"], timeout))
            return ' "Às 14:00 há a **Prova de Cálculo**, Senhor; duas horas bastam para revisar." '

        text = reminders.phrase("lead", self.EVENT, 120, query=query)
        self.assertEqual(text, "Às 14:00 há a Prova de Cálculo, Senhor; duas horas bastam para revisar.")
        self.assertIn("às 14:00", seen[0][0])                 # os fatos foram ao prompt
        self.assertEqual(seen[0][1], reminders.PHRASE_TIMEOUT_S)

    def test_model_must_keep_relative_time_and_the_order_to_leave(self):
        """Visto no teste real: o modelo trocava 'em 2 horas' por 'está agendada' e sumia com o 'saia'."""
        lead_fallback = reminders.fallback_phrase("lead", self.EVENT, 120)
        dropped = "Senhor, a Prova de Cálculo II está agendada para as 14:00 em FGV."
        self.assertEqual(reminders.phrase("lead", self.EVENT, 120, query=lambda *a, **k: dropped), lead_fallback)
        for kept in ("Em duas horas, às 14:00, Prova de Cálculo II, Senhor.", "Daqui a 2h, às 14:00: prova, Senhor."):
            self.assertEqual(reminders.phrase("lead", self.EVENT, 120, query=lambda *a, k2=kept, **k: k2), kept)
        travel = {"minutes": 35, "dest": "FGV"}
        no_leave = "Senhor, a Prova às 14:00 fica a 35 minutos de trajeto."
        self.assertEqual(reminders.phrase("leave", self.EVENT, 60, travel, query=lambda *a, **k: no_leave),
                         reminders.fallback_phrase("leave", self.EVENT, 60, travel))
        ok = "Hora de sair, Senhor: Prova às 14:00 e 35 minutos de estrada."
        self.assertEqual(reminders.phrase("leave", self.EVENT, 60, travel, query=lambda *a, **k: ok), ok)
        invented = "Senhor, em 2 horas, às 14:00, o senhor tem Prova de Cálculo II. Sai em 15 minutos."
        self.assertEqual(reminders.phrase("lead", self.EVENT, 120, query=lambda *a, **k: invented), lead_fallback)
        final = "Prova de Cálculo começa em 15 minutos, às 14:00. Ânimo, Senhor."
        self.assertEqual(reminders.phrase("final", self.EVENT, 15, query=lambda *a, **k: final), final)

    def test_model_output_without_the_time_or_broken_falls_back(self):
        fallback = reminders.fallback_phrase("lead", self.EVENT, 120)
        for answer in ("O senhor tem uma prova às 15:00.", "", None, "x" * 400):
            with self.subTest(answer=answer):
                self.assertEqual(reminders.phrase("lead", self.EVENT, 120, query=lambda *a, **k: answer), fallback)

        def boom(*a, **k):
            raise TimeoutError("ollama lento")
        self.assertEqual(reminders.phrase("lead", self.EVENT, 120, query=boom), fallback)


class TestParseWhen(unittest.TestCase):
    def test_cases(self):
        d = NOW.replace
        cases = {
            "me lembra em 30 min de tirar a roupa": (NOW + timedelta(minutes=30), "tirar a roupa"),
            "daqui a 2 horas ligar para o João": (NOW + timedelta(hours=2), "ligar para o João"),
            "em meia hora beber água": (NOW + timedelta(minutes=30), "beber água"),
            "em 1 hora e meia sair para o treino": (NOW + timedelta(minutes=90), "sair para o treino"),
            "em 1h30 buscar o carro": (NOW + timedelta(minutes=90), "buscar o carro"),
            "em uma hora revisar o PR": (NOW + timedelta(hours=1), "revisar o PR"),
            "às 18h ligar pro João": (d(hour=18, minute=0), "ligar pro João"),
            "18:30 jantar com a Ana": (d(hour=18, minute=30), "jantar com a Ana"),
            "me avisa às 9h de tomar o remédio": (d(hour=9, minute=0) + timedelta(days=1), "tomar o remédio"),
            "amanhã às 9h reunião com o time": (d(hour=9, minute=0) + timedelta(days=1), "reunião com o time"),
            "às 15 pagar o boleto": (d(hour=15, minute=0), "pagar o boleto"),
            "Jarvis, me lembre daqui 10 minutos que o forno está ligado":
                (NOW + timedelta(minutes=10), "o forno está ligado"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(reminders.parse_when(text, NOW), expected)

    def test_no_time(self):
        for text in ("comprar pão", "me lembra de ligar para o João", "", "em 3 meses renovar o domínio",
                     "às 25h dormir"):
            with self.subTest(text=text):
                self.assertIsNone(reminders.parse_when(text, NOW))


class TestManual(DbCase):
    def test_create_list_remove(self):
        reply = reminders.create_from_text("em 30 min tirar a roupa", NOW, ask_llm=None)
        self.assertEqual(reply, "Lembrete marcado para hoje às 12:30 (em 30 minutos): tirar a roupa.")
        reminders.create_from_text("amanhã às 9h reunião com o time", NOW, ask_llm=None)
        listing = reminders.list_text(NOW)
        self.assertIn("1. **hoje às 12:30** — tirar a roupa", listing)
        self.assertIn("2. **amanhã às 09:00** — reunião com o time", listing)
        self.assertEqual(reminders.remove_text(1), "Lembrete removido: tirar a roupa.")
        self.assertIn("Não há lembrete 5", reminders.remove_text(5))
        self.assertEqual([i["text"] for i in reminders.pending()], ["reunião com o time"])

    def test_survives_new_session(self):
        reminders.create_from_text("em 30 min tirar a roupa", NOW, ask_llm=None)
        with patch.object(reminders, "db", database.DatabaseManager()):
            self.assertEqual(len(reminders.pending()), 1)

    def test_missing_time_or_subject_saves_nothing(self):
        self.assertIn("Para quando", reminders.create_from_text("ligar para o João", NOW, ask_llm=None))
        self.assertIn("Lembrar do quê", reminders.create_from_text("em 10 min", NOW, ask_llm=None))
        self.assertEqual(reminders.pending(), [])
        self.assertIn("Nenhum lembrete", reminders.list_text(NOW))

    def test_llm_fallback_when_regex_fails(self):
        reply = reminders.create_from_text("daqui a pouco ver o forno", NOW, ask_llm=lambda t: (15.0, "ver o forno"))
        self.assertIn("hoje às 12:15", reply)
        self.assertIn("Para quando", reminders.create_from_text("ver o forno", NOW, ask_llm=lambda t: None))

    def test_ask_llm_validates_minutes(self):
        for raw, expected in ((json.dumps({"minutes": 15, "text": "ver o forno"}), (15.0, "ver o forno")),
                              (json.dumps({"minutes": None, "text": "x"}), None),
                              (json.dumps({"minutes": -5, "text": "x"}), None),
                              (json.dumps({"minutes": True, "text": "x"}), None),
                              ("lixo", None)):
            with self.subTest(raw=raw), patch("core.llm.query_ollama", return_value=raw):
                self.assertEqual(reminders._ask_llm("daqui a pouco ver o forno"), expected)

    def test_pop_due_fires_once(self):
        reminders.add("tirar a roupa", NOW + timedelta(minutes=30))
        self.assertEqual(reminders.pop_due(NOW + timedelta(minutes=29)), [])
        self.assertEqual([i["text"] for i in reminders.pop_due(NOW + timedelta(minutes=30))], ["tirar a roupa"])
        self.assertEqual(reminders.pop_due(NOW + timedelta(minutes=31)), [])
        self.assertEqual(reminders.pending(), [])


class TestCollect(DbCase):
    PREFS = {"event_reminders": True, "reminder_lead": 120, "reminder_final": 15}

    def _collect(self, events, now=NOW, prefs=None, travel=None):
        return reminders.collect(now, calendar=FakeCalendar(events), prefs=prefs or self.PREFS,
                                 travel_fn=lambda e: travel,
                                 phrase_fn=lambda kind, event, minutes, tr: f"{kind}:{event['title']}:{minutes}")

    def test_lead_is_not_urgent_and_does_not_repeat(self):
        self.assertEqual(self._collect([ev()]), [{"text": "lead:Prova de Cálculo:120", "kind": "lead", "urgent": False}])
        self.assertEqual(self._collect([ev()], now=NOW + timedelta(seconds=30)), [])  # persistido no banco

    def test_final_and_leave_are_urgent(self):
        out = self._collect([ev(minutes=15)])
        self.assertEqual((out[0]["kind"], out[0]["urgent"]), ("final", True))
        out = self._collect([ev(minutes=60, id_="e9")], travel={"minutes": 35, "dest": "FGV"},
                            prefs={**self.PREFS, "reminder_lead": 30})
        self.assertEqual((out[0]["kind"], out[0]["urgent"]), ("leave", True))

    def test_pref_off_skips_the_calendar(self):
        calendar = FakeCalendar([ev()])
        out = reminders.collect(NOW, calendar=calendar, prefs={**self.PREFS, "event_reminders": False})
        self.assertEqual(out, [])
        self.assertEqual(calendar.asked, [])

    def test_manual_due_and_missed_while_closed(self):
        reminders.add("beber água", NOW - timedelta(minutes=1))
        reminders.add("ligar para o João", NOW - timedelta(hours=3))
        reminders.add("pagar o boleto", NOW - timedelta(hours=2))
        out = self._collect([])
        self.assertEqual(out[0], {"text": "Lembrete, Senhor: beber água.", "kind": "manual", "urgent": True})
        self.assertIn("Enquanto estive fora, 2 lembretes venceram", out[1]["text"])
        self.assertIn("ligar para o João (16/11 09:00)", out[1]["text"])
        self.assertEqual(self._collect([]), [])

    def test_calendar_failure_does_not_break_manual(self):
        class Broken:
            def upcoming(self, hours, now):
                raise RuntimeError("google fora")
        reminders.add("beber água", NOW)
        out = reminders.collect(NOW, calendar=Broken(), prefs=self.PREFS)
        self.assertEqual([o["kind"] for o in out], ["manual"])


class TestCalendarUpcoming(unittest.TestCase):
    ITEM = {"id": "abc", "summary": "Prova", "location": " FGV, São Paulo ", "status": "confirmed",
            "start": {"dateTime": "2026-11-16T14:00:00-03:00"}, "end": {"dateTime": "2026-11-16T16:00:00-03:00"}}

    def setUp(self):
        gc._upcoming_cache.update(at=-1e9, items=[], hours=0)
        self._patches = [patch.object(gc, "is_configured", return_value=True),
                         patch.object(gc, "is_connected", return_value=True),
                         patch.object(gc, "_access_token", return_value="tok")]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        gc._upcoming_cache.update(at=-1e9, items=[], hours=0)

    def test_parse_event_keeps_id_and_location(self):
        event = gc.parse_event(self.ITEM)
        self.assertEqual((event["id"], event["location"], event["title"]), ("abc", "FGV, São Paulo", "Prova"))
        self.assertEqual(gc.parse_event({"summary": "x"})["location"], "")

    def test_window_crosses_midnight_and_is_cached(self):
        clock = iter([100.0, 100.0, 200.0, 1000.0, 1000.0]).__next__
        cancelled = {**self.ITEM, "id": "z", "status": "cancelled"}
        with patch.object(gc, "_get", return_value={"items": [self.ITEM, cancelled]}) as get:
            now = datetime(2026, 11, 16, 20, 0)
            items = gc.upcoming(24, now, clock=clock)
            self.assertEqual([i["id"] for i in items], ["abc"])
            params = get.call_args[0][2]
            self.assertTrue(params["timeMin"].startswith("2026-11-16T20:00"))
            self.assertTrue(params["timeMax"].startswith("2026-11-17T20:00"))
            gc.upcoming(24, now, clock=clock)          # dentro do TTL: sem HTTP
            self.assertEqual(get.call_count, 1)
            gc.upcoming(24, now, clock=clock)          # TTL vencido
            self.assertEqual(get.call_count, 2)

    def test_failure_returns_last_known_and_disconnected_returns_empty(self):
        clock = iter([100.0, 100.0, 5000.0]).__next__
        with patch.object(gc, "_get", return_value={"items": [self.ITEM]}):
            gc.upcoming(24, datetime(2026, 11, 16, 8, 0), clock=clock)
        with patch.object(gc, "_get", side_effect=gc.CalendarError("fora")):
            self.assertEqual(len(gc.upcoming(24, datetime(2026, 11, 16, 9, 0), clock=clock)), 1)
        with patch.object(gc, "is_connected", return_value=False):
            self.assertEqual(gc.upcoming(), [])


class TestSkill(unittest.TestCase):
    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "skills", "productivity", "reminder.py")
        spec = importlib.util.spec_from_file_location("reminder_skill", path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_routes_create_list_remove(self):
        with patch.object(reminders, "create_from_text", return_value="criado") as create, \
             patch.object(reminders, "list_text", return_value="lista") as listing, \
             patch.object(reminders, "remove_text", return_value="removido") as remove:
            self.assertEqual(self.mod.execute("roupa", "me lembra em 30 min de tirar a roupa"), "criado")
            self.assertEqual(self.mod.execute(None, "quais lembretes eu tenho?"), "lista")
            self.assertEqual(self.mod.execute(None, "cancela o lembrete 2"), "removido")
            self.assertIn("Qual lembrete", self.mod.execute(None, "cancela o lembrete"))
        create.assert_called_once_with("me lembra em 30 min de tirar a roupa")
        listing.assert_called_once()
        remove.assert_called_once_with(2)
        self.assertEqual(self.mod.INTENT, "REMINDER")


if __name__ == "__main__":
    unittest.main()
