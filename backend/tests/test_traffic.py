"""core.traffic + /rota + skill TRAFFIC — geocodificação, TomTom × OSRM e aviso de saída."""
import datetime
import json
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

import core.traffic as traffic  # noqa: E402
from core.config import settings  # noqa: E402
from frontend.commands import COMMANDS, parse, parse_rota_arg  # noqa: E402
from services import user_prefs  # noqa: E402
from skills.productivity import traffic_commute  # noqa: E402

HOME = {"address": "Rua A, 1", "lat": -23.5, "lon": -46.6, "label": "Rua A"}
WORK = {"address": "Av B, 2", "lat": -23.6, "lon": -46.7, "label": "Av B"}
D = datetime.datetime


class _FakeDb:
    def __init__(self):
        self.data = {}

    def get_config(self, key):
        return self.data.get(key)

    def save_config(self, key, value):
        self.data[key] = value


class _Base(unittest.TestCase):
    def setUp(self):
        self.db = _FakeDb()
        self._ps = [patch.object(traffic, "_db", lambda: self.db),
                    patch.object(settings, "TOMTOM_API_KEY", "")]
        for p in self._ps:
            p.start()

    def tearDown(self):
        for p in reversed(self._ps):
            p.stop()

    def _places(self):
        self.db.data[traffic.PLACES["casa"]] = json.dumps(HOME)
        self.db.data[traffic.PLACES["trabalho"]] = json.dumps(WORK)


class TestPlaces(_Base):
    def test_geocode_parses_nominatim(self):
        hit = [{"lat": "-23.5", "lon": "-46.6", "display_name": "Rua A, 1, Centro, São Paulo, Brasil"}]
        with patch.object(traffic, "_get_json", return_value=hit) as get:
            place = traffic.geocode("Rua A, 1")
        self.assertEqual(place["label"], "Rua A, 1, Centro")
        self.assertEqual(place["lat"], -23.5)
        self.assertIn("User-Agent", get.call_args.args[2])

    def test_geocode_failure(self):
        with patch.object(traffic, "_get_json", side_effect=RuntimeError("off")):
            self.assertIsNone(traffic.geocode("x"))
        with patch.object(traffic, "_get_json", return_value=[]):
            self.assertIsNone(traffic.geocode("x"))

    def test_set_and_get_place(self):
        msg = traffic.set_place("casa", "Rua A, 1", geocoder=lambda a: dict(HOME))
        self.assertIn("salvo", msg)
        self.assertEqual(traffic.get_place("casa")["lat"], -23.5)
        self.assertFalse(traffic.has_places())
        self.assertIn("Não encontrei", traffic.set_place("trabalho", "???", geocoder=lambda a: None))
        self.assertIn("Uso", traffic.set_place("???", "x"))       # tag sem letras
        self.assertIn("Qual o endereço de praia", traffic.set_place("praia", " "))

    def test_clear_places(self):
        self._places()
        self.assertTrue(traffic.has_places())
        traffic.clear_places()
        self.assertFalse(traffic.has_places())


class TestRoute(_Base):
    def test_osrm_without_key(self):
        with patch.object(traffic, "_get_json", return_value={"code": "Ok", "routes": [{"duration": 1680}]}) as get:
            result = traffic.route(HOME, WORK)
        self.assertEqual(result, {"minutes": 28, "typical": None, "source": "OSRM"})
        self.assertIn("router.project-osrm.org", get.call_args.args[0])
        self.assertIn("-46.6,-23.5", get.call_args.args[0])  # OSRM é lon,lat

    def test_tomtom_with_key(self):
        payload = {"routes": [{"summary": {"travelTimeInSeconds": 2040, "noTrafficTravelTimeInSeconds": 1500}}]}
        with patch.object(settings, "TOMTOM_API_KEY", "k"), \
             patch.object(traffic, "_get_json", return_value=payload) as get:
            result = traffic.route(HOME, WORK)
        self.assertEqual(result, {"minutes": 34, "typical": 25, "source": "TomTom"})
        self.assertEqual(get.call_args.args[1]["traffic"], "true")

    def test_tomtom_failure_falls_back_to_osrm(self):
        calls = []

        def get(url, params=None, headers=None):
            calls.append(url)
            if "tomtom" in url:
                raise RuntimeError("403")
            return {"code": "Ok", "routes": [{"duration": 600}]}

        with patch.object(settings, "TOMTOM_API_KEY", "k"), patch.object(traffic, "_get_json", get):
            self.assertEqual(traffic.route(HOME, WORK)["source"], "OSRM")
        self.assertEqual(len(calls), 2)

    def test_route_none_when_all_fail(self):
        with patch.object(traffic, "_get_json", side_effect=RuntimeError("off")):
            self.assertIsNone(traffic.route(HOME, WORK))

    def test_describe(self):
        self.assertEqual(traffic.describe("casa", "trabalho", {"minutes": 34, "typical": 25, "source": "TomTom"}),
                         "Casa → trabalho: 34 min (+9 pelo trânsito, TomTom).")
        self.assertIn("trânsito livre", traffic.describe("casa", "trabalho",
                                                         {"minutes": 26, "typical": 25, "source": "TomTom"}))
        self.assertIn("sem trânsito ao vivo", traffic.describe("trabalho", "casa",
                                                               {"minutes": 28, "typical": None, "source": "OSRM"}))

    def test_direction_flips_in_the_evening(self):
        self.assertEqual(traffic.direction(D(2026, 11, 9, 8)), ("casa", "trabalho"))
        self.assertEqual(traffic.direction(D(2026, 11, 9, 18)), ("trabalho", "casa"))

    def test_commute_line_and_text(self):
        self.assertIsNone(traffic.commute_line())
        self.assertEqual(traffic.commute_text(), traffic.NO_PLACES)
        self._places()
        with patch.object(traffic, "route", return_value={"minutes": 20, "typical": None, "source": "OSRM"}) as r:
            line = traffic.commute_line(D(2026, 11, 9, 18))
        self.assertTrue(line.startswith("Trabalho → casa: 20 min"))
        self.assertEqual(r.call_args.args, (WORK, HOME))
        with patch.object(traffic, "route", return_value=None):
            self.assertIn("Não consegui", traffic.commute_text())

    def test_skill(self):
        with patch.object(traffic, "commute_text", return_value="ok"):
            self.assertEqual(traffic_commute.execute("", "como está o trânsito"), "ok")


FACUL = {"address": "Av C, 3", "lat": -23.55, "lon": -46.65, "label": "Av C"}


class TestFreePlaces(_Base):
    def test_set_any_tag_and_list(self):
        geo = lambda a: {**FACUL, "address": a}  # noqa: E731
        self.assertIn("faculdade salvo", traffic.set_place("Faculdade", "Av C, 3", geocoder=geo))
        self.assertIn("escola salvo", traffic.set_place("colégio", "Rua D", geocoder=geo))  # alias
        self.assertIn("casa da mae", traffic.set_place("casa_da_mãe", "Rua E", geocoder=geo))
        self._places()
        self.assertEqual(list(traffic.list_places()), ["casa", "trabalho", "faculdade", "escola", "casa_da_mae"])
        self.assertEqual(traffic.get_place("FACULDADE")["label"], "Av C")
        text = traffic.places_text()
        self.assertIn("**Faculdade:** Av C", text)
        traffic.clear_places()
        self.assertEqual(traffic.list_places(), {})

    def test_set_place_keeps_legacy_keys(self):
        traffic.set_place("home", "Rua A", geocoder=lambda a: HOME)
        self.assertIn(traffic.PLACES["casa"], self.db.data)

    def test_places_text_empty(self):
        self.assertIn("Nenhum local", traffic.places_text())

    def test_trip_text(self):
        self._places()
        self.db.data["place_faculdade"] = json.dumps(FACUL)
        with patch.object(traffic, "route", return_value={"minutes": 15, "typical": None, "source": "OSRM"}) as r:
            text = traffic.trip_text("faculdade", "casa")
        self.assertTrue(text.startswith("Faculdade → casa: 15 min"))
        self.assertEqual(r.call_args.args, (FACUL, HOME))
        self.assertIn("Não tenho o endereço de academia", traffic.trip_text("casa", "academia"))
        self.assertIn("já está", traffic.trip_text("casa", "casa"))


class TestTrafficSkill(_Base):
    TAGS = ["casa", "trabalho", "faculdade", "escola"]
    MORNING = D(2026, 11, 9, 8)

    def test_decide(self):
        d = lambda text: traffic_commute.decide(text, self.TAGS, self.MORNING)  # noqa: E731
        self.assertEqual(d("quanto tempo até a faculdade?"), ("casa", "faculdade"))
        self.assertEqual(d("quanto demora da escola pra casa"), ("escola", "casa"))
        self.assertEqual(d("pra casa saindo da faculdade"), ("faculdade", "casa"))
        self.assertEqual(d("saindo da facul, quanto demora?"), ("faculdade", "casa"))
        self.assertEqual(d("quanto tempo até minha casa"), ("trabalho", "casa"))
        self.assertIsNone(d("como está o trânsito"))
        evening = traffic_commute.decide("quanto tempo pra faculdade", self.TAGS, D(2026, 11, 9, 18))
        self.assertEqual(evening, ("trabalho", "faculdade"))

    def test_execute_routes_between_places(self):
        self._places()
        self.db.data["place_faculdade"] = json.dumps(FACUL)
        self.db.data[traffic.INDEX_KEY] = json.dumps(["faculdade"])
        with patch.object(traffic, "trip_text", return_value="trip") as trip:
            self.assertEqual(traffic_commute.execute("faculdade", "da faculdade pra casa"), "trip")
        trip.assert_called_once_with("faculdade", "casa")

    def test_execute_unknown_place_explains(self):
        self._places()
        self.assertIn("Não tenho o endereço de academia", traffic_commute.execute("academia", "tempo até a academia"))
        with patch.object(traffic, "commute_text", return_value="commute"):
            self.assertEqual(traffic_commute.execute("null", "como está o trânsito"), "commute")
            self.assertEqual(traffic_commute.execute("agora", "e o trânsito agora?"), "commute")


class TestAlertDue(unittest.TestCase):
    def test_rules(self):
        monday = D(2026, 11, 9, 7, 40)
        self.assertTrue(traffic.alert_due(450, monday, None))             # 07:30, já passou 10 min
        self.assertFalse(traffic.alert_due(0, monday, None))              # desligado
        self.assertFalse(traffic.alert_due(480, monday, None))            # ainda não é 08:00
        self.assertFalse(traffic.alert_due(450, monday, "2026-11-09"))    # já avisou hoje
        self.assertFalse(traffic.alert_due(450, D(2026, 11, 9, 9, 0), None))   # passou da janela
        self.assertFalse(traffic.alert_due(450, D(2026, 11, 14, 7, 40), None))  # sábado

    def test_pref_options(self):
        self.assertIn("commute_alert", user_prefs.GROUPS["ROTINAS"])
        self.assertEqual(user_prefs.display("commute_alert", 450), "07:30")
        self.assertEqual(user_prefs.display("commute_alert", 0), "desligado")


class TestRotaCommand(unittest.TestCase):
    def test_parse(self):
        self.assertIn("rota", COMMANDS)
        self.assertEqual(parse("/rota casa Rua A, 1").arg, "casa Rua A, 1")
        self.assertEqual(parse_rota_arg(""), ("list", None, ""))
        self.assertEqual(parse_rota_arg("casa Rua A, 1"), ("set", "casa", "Rua A, 1"))
        self.assertEqual(parse_rota_arg("Trabalho Av B"), ("set", "trabalho", "Av B"))
        self.assertEqual(parse_rota_arg("Faculdade Av. Paulista, 1000"), ("set", "faculdade", "Av. Paulista, 1000"))
        self.assertIsNone(parse_rota_arg("faculdade"))  # sem endereço


if __name__ == "__main__":
    unittest.main()
