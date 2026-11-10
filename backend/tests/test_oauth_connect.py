"""Login de contas pelo navegador: client embutido, loopback de verdade, Google e Spotify."""
import json
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.google_calendar as gc  # noqa: E402
import core.oauth as oauth  # noqa: E402
import core.spotify as sp  # noqa: E402
from core import config  # noqa: E402
from core.config import settings  # noqa: E402


class TestPersonalKeysDocumented(unittest.TestCase):
    def test_docs_say_keys_are_personal(self):
        root = config.ROOT_DIR
        guide = (root / "docs" / "integracoes-oauth.md").read_text(encoding="utf-8")
        self.assertIn("chaves PESSOAIS", guide)
        for var in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SPOTIFY_CLIENT_ID"):
            self.assertIn(var, guide)
            self.assertIn(var, (root / "env.example").read_text(encoding="utf-8"))
        self.assertIn("docs/integracoes-oauth.md", (root / "README.md").read_text(encoding="utf-8"))


class TestRealLoopback(unittest.TestCase):
    """Sobe o servidor de callback de verdade e simula o navegador voltando do provedor."""

    def _browser(self, query_for_state):
        def open_browser(url):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            redirect, state = q["redirect_uri"][0], q["state"][0]

            def hit():
                params = urllib.parse.urlencode(query_for_state(state))
                with urllib.request.urlopen(f"{redirect}?{params}", timeout=5) as resp:
                    self.page = resp.read().decode("utf-8")
            self.browser = threading.Thread(target=hit, daemon=True)
            self.browser.start()
        return open_browser

    def _page(self):
        self.browser.join(5)
        return self.page

    def _build(self, redirect_uri, challenge, state):
        return "https://provedor/auth?" + urllib.parse.urlencode(
            {"redirect_uri": redirect_uri, "state": state, "code_challenge": challenge})

    def test_code_arrives_and_page_is_shown(self):
        result = oauth.authorize(self._build, 10, open_browser=self._browser(lambda s: {"code": "C1", "state": s}))
        self.assertIsNotNone(result)
        code, verifier, redirect = result
        self.assertEqual(code, "C1")
        self.assertTrue(redirect.startswith("http://127.0.0.1:"))
        self.assertIn("CONECTADO", self._page())

    def test_fixed_port_and_path(self):
        port = oauth.free_port()
        result = oauth.authorize(self._build, 10, port=port, path="/callback",
                                 open_browser=self._browser(lambda s: {"code": "C2", "state": s}))
        self.assertEqual(result[2], f"http://127.0.0.1:{port}/callback")

    def test_denied_shows_denied_page(self):
        result = oauth.authorize(self._build, 10,
                                 open_browser=self._browser(lambda s: {"error": "access_denied", "state": s}))
        self.assertIsNone(result)
        self.assertIn("NEGADO", self._page())


class TestGoogleAccountPicker(unittest.TestCase):
    def test_url_asks_to_choose_account(self):
        with patch.object(settings, "GOOGLE_CLIENT_ID", "cid"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(
                gc.build_authorize_url("http://127.0.0.1:1", "c", "s")).query)
        self.assertEqual(q["prompt"], ["select_account consent"])


class _MemVault:
    """secrets_store em memória: os testes nunca tocam o Cofre real do Windows."""

    def __init__(self):
        self.data = {}

    def get(self, name):
        return self.data.get(name)

    def set(self, name, value):
        self.data[name] = dict(value)
        return True

    def delete(self, name):
        self.data.pop(name, None)


class TestSpotifyConnect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = _MemVault()
        self._ps = [patch.object(sp, "secrets_store", self.vault),patch.object(settings, "SPOTIFY_TOKEN_PATH", Path(self.tmp.name) / "spotify_token.json"),
                    patch.object(settings, "DIR_DATABASE", Path(self.tmp.name)),
                    patch.object(settings, "SPOTIFY_CLIENT_ID", "sid"),
                    patch.object(settings, "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")]
        for p in self._ps:
            p.start()

    def tearDown(self):
        for p in reversed(self._ps):
            p.stop()
        self.tmp.cleanup()

    def test_authorize_url_forces_login_dialog(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(
            sp._build_authorize_url("http://127.0.0.1:8888/callback", "ch", "st")).query)
        self.assertEqual(q["show_dialog"], ["true"])
        self.assertEqual(q["redirect_uri"], ["http://127.0.0.1:8888/callback"])
        self.assertEqual(q["client_id"], ["sid"])

    def test_flow_uses_registered_redirect_and_saves_account(self):
        seen = {}

        def authorize(build, timeout, port=None, path=""):
            seen.update(port=port, path=path)
            return "CODE", "VER", f"http://127.0.0.1:{port}{path}"

        sp._save_token({"access_token": "velho", "refresh_token": "velho", "account": "Outra"})
        token = {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600}
        with patch.object(sp, "_exchange_code", return_value=token) as exchange, \
             patch.object(sp, "_fetch_account", return_value="Felipe"):
            self.assertTrue(sp._run_auth_flow(authorize=authorize))
        self.assertEqual((seen["port"], seen["path"]), (8888, "/callback"))
        self.assertEqual(exchange.call_args.args, ("CODE", "VER", "http://127.0.0.1:8888/callback"))
        saved = self.vault.get(sp.SECRET_NAME)
        self.assertEqual(saved["refresh_token"], "r1")
        self.assertNotIn("velho", saved.values())
        self.assertEqual(saved["account"], "Felipe")
        self.assertEqual(sp.spotify.account(), "Felipe")

    def test_cancelled_flow(self):
        self.assertFalse(sp._run_auth_flow(authorize=lambda *a, **k: None))
        self.assertFalse(sp.spotify.is_authorized())

    def test_disconnect_removes_token(self):
        sp._save_token({"access_token": "a", "refresh_token": "r"})
        self.assertTrue(sp.spotify.is_authorized())
        self.assertTrue(sp.disconnect())
        self.assertFalse(sp.spotify.is_authorized())

    def test_token_survives_restart(self):
        sp._save_token({"access_token": "a", "refresh_token": "r", "expires_in": 3600, "account": "Felipe"})
        self.assertFalse(settings.SPOTIFY_TOKEN_PATH.exists())        # nada em arquivo
        self.assertEqual(sp._load_token()["refresh_token"], "r")      # "reinício": lê do cofre
        self.assertEqual(sp.spotify.account(), "Felipe")

    def test_old_token_file_is_migrated(self):
        settings.SPOTIFY_TOKEN_PATH.write_text(json.dumps({"refresh_token": "antigo"}), encoding="utf-8")
        self.assertEqual(sp._load_token()["refresh_token"], "antigo")
        self.assertEqual(self.vault.get(sp.SECRET_NAME)["refresh_token"], "antigo")
        self.assertFalse(settings.SPOTIFY_TOKEN_PATH.exists())

    def test_expired_access_token_renews_without_login(self):
        sp._save_token({"access_token": "velho", "refresh_token": "r1", "expires_at": 0})
        resp = MagicMock(status_code=200, text="")
        resp.json.return_value = {"access_token": "novo", "expires_in": 3600}
        with patch.object(sp.requests, "post", return_value=resp):
            self.assertEqual(sp.spotify._access_token(), "novo")
        self.assertEqual(self.vault.get(sp.SECRET_NAME)["refresh_token"], "r1")  # mantém o refresh

    def test_revoked_access_clears_token(self):
        sp._save_token({"access_token": "velho", "refresh_token": "r1", "expires_at": 0})
        resp = MagicMock(status_code=400, text='{"error":"invalid_grant"}')
        with patch.object(sp.requests, "post", return_value=resp):
            self.assertIsNone(sp.spotify._access_token())
        self.assertFalse(sp.spotify.is_authorized())

    def test_network_error_keeps_token(self):
        sp._save_token({"access_token": "velho", "refresh_token": "r1", "expires_at": 0})
        class Offline(Exception):
            pass

        with patch.object(sp.requests, "RequestException", Offline),              patch.object(sp.requests, "post", side_effect=Offline("offline")):
            self.assertIsNone(sp.spotify._access_token())
        self.assertTrue(sp.spotify.is_authorized())

    def test_fetch_account(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"display_name": "Felipe", "id": "fg"}
        with patch.object(sp.requests, "get", return_value=resp):
            self.assertEqual(sp._fetch_account("tok"), "Felipe")


class TestGoogleKeepsSession(unittest.TestCase):
    def setUp(self):
        self.vault = _MemVault()
        self._ps = [patch.object(gc, "secrets_store", self.vault),
                    patch.object(settings, "GOOGLE_CLIENT_ID", "cid"),
                    patch.object(settings, "GOOGLE_CLIENT_SECRET", "cs")]
        for p in self._ps:
            p.start()

    def tearDown(self):
        for p in reversed(self._ps):
            p.stop()

    def test_revoked_refresh_clears_session(self):
        self.vault.set(gc.SECRET_NAME, {"refresh_token": "r", "expires_at": 0})
        with patch.object(gc, "_post", side_effect=gc.CalendarError('Google recusou (400): {"error": "invalid_grant"}')):
            with self.assertRaises(gc.CalendarError) as ctx:
                gc._access_token()
        self.assertIn("Reconecte", str(ctx.exception))
        self.assertFalse(gc.is_connected())

    def test_network_error_keeps_session(self):
        self.vault.set(gc.SECRET_NAME, {"refresh_token": "r", "expires_at": 0})
        with patch.object(gc, "_post", side_effect=gc.CalendarError("Google recusou (503): x")):
            with self.assertRaises(gc.CalendarError):
                gc._access_token()
        self.assertTrue(gc.is_connected())


class TestCards(unittest.TestCase):
    def test_spotify_card_shows_account(self):
        import services.integrations as integrations
        with patch.object(sp.spotify, "is_configured", return_value=True), \
             patch.object(sp.spotify, "is_authorized", return_value=True), \
             patch.object(sp.spotify, "account", return_value="Felipe"):
            self.assertEqual(integrations.state_of(integrations.get("spotify")), (integrations.ON, "conta: Felipe"))

    def test_connected_card_does_not_open_login_again(self):
        import services.integrations as integrations
        with patch.object(sp.spotify, "is_configured", return_value=True),              patch.object(sp.spotify, "is_authorized", return_value=True),              patch.object(sp.spotify, "account", return_value="Felipe"),              patch.object(sp, "start_authorization") as start:
            message = integrations.connect("spotify")
        start.assert_not_called()
        self.assertIn("já está conectado (Felipe)", message)
        with patch.object(gc, "is_configured", return_value=True),              patch.object(gc, "is_connected", return_value=True),              patch.object(gc, "account", return_value="eu@gmail.com"),              patch.object(gc, "connect") as connect:
            self.assertIn("já está conectado", integrations.connect("google_calendar"))
        connect.assert_not_called()

    def test_cards_without_key_point_to_env(self):
        import services.integrations as integrations
        with patch.object(settings, "SPOTIFY_CLIENT_ID", ""), patch.object(settings, "GOOGLE_CLIENT_ID", ""):
            self.assertEqual(integrations.state_of(integrations.get("spotify"))[1], "falta SPOTIFY_CLIENT_ID no .env")
            self.assertEqual(integrations.state_of(integrations.get("google_calendar"))[1],
                             "falta GOOGLE_CLIENT_ID no .env")
            with patch.object(integrations, "_open") as opened:
                self.assertIn("docs/integracoes-oauth.md", integrations.connect("spotify"))
                self.assertIn("docs/integracoes-oauth.md", integrations.connect("google_calendar"))
            self.assertEqual(opened.call_count, 2)  # abre o painel de cada serviço


if __name__ == "__main__":
    unittest.main()
