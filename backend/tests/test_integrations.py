"""services.integrations + core.secrets_store — estados dos cards e cofre."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._stubs import install

install()

import core.secrets_store as secrets_store  # noqa: E402
import services.integrations as integrations  # noqa: E402
from core.config import settings  # noqa: E402


class TestSecretsStoreFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = settings.DIR_DATABASE
        settings.DIR_DATABASE = Path(self.tmp.name)

    def tearDown(self):
        settings.DIR_DATABASE = self._orig
        self.tmp.cleanup()

    def test_roundtrip_without_keyring(self):
        with patch.object(secrets_store, "_keyring", return_value=None):
            self.assertIsNone(secrets_store.get("google"))
            self.assertTrue(secrets_store.set("google", {"refresh_token": "r1"}))
            self.assertEqual(secrets_store.get("google"), {"refresh_token": "r1"})
            secrets_store.delete("google")
            self.assertIsNone(secrets_store.get("google"))

    def test_uses_keyring_when_available(self):
        store = {}

        class FakeKeyring:
            def get_password(self, svc, name):
                return store.get((svc, name))

            def set_password(self, svc, name, raw):
                store[(svc, name)] = raw

            def delete_password(self, svc, name):
                store.pop((svc, name), None)

        with patch.object(secrets_store, "_keyring", return_value=FakeKeyring()):
            secrets_store.set("google", {"a": 1})
            self.assertIn(("JARVIS", "google"), store)
            self.assertEqual(secrets_store.get("google"), {"a": 1})
            self.assertFalse((Path(self.tmp.name) / secrets_store._FALLBACK_FILE).exists())
            secrets_store.delete("google")
            self.assertEqual(store, {})


def _fake(id_="fake", status=("off", "pronto"), connect=lambda: "feito", disconnect=None):
    return integrations.Integration(id_, "Fake", "desc", lambda: status, connect, disconnect)


class TestRegistry(unittest.TestCase):
    def test_default_cards(self):
        ids = [i.id for i in integrations.all_integrations()]
        for expected in ("github", "spotify"):
            self.assertIn(expected, ids)

    def test_github_states(self):
        github = integrations.get("github")
        with patch.object(settings, "GITHUB_TOKEN", ""):
            self.assertEqual(integrations.state_of(github)[0], integrations.SETUP)
        with patch.object(settings, "GITHUB_TOKEN", "tok"):
            state, detail = integrations.state_of(github)
            self.assertEqual(state, integrations.ON)
            self.assertIn("GITHUB_TOKEN", detail)

    def test_github_connect_without_token_opens_tokens_page(self):
        with patch.object(settings, "GITHUB_TOKEN", ""), patch.object(integrations, "_open") as opened:
            message = integrations.connect("github")
        opened.assert_called_once_with(integrations.GITHUB_TOKENS_URL)
        self.assertIn("GITHUB_TOKEN", message)

    def test_status_error_becomes_setup(self):
        def boom():
            raise RuntimeError("x")
        broken = integrations.Integration("b", "B", "d", boom, lambda: "")
        self.assertEqual(integrations.state_of(broken)[0], integrations.SETUP)

    def test_connect_marks_wait_while_running(self):
        fake = _fake()
        seen = {}
        release = threading.Event()

        def slow():
            release.wait(2)
            return "conectado"

        fake.connect = slow
        with patch.object(integrations, "get", return_value=fake):
            def started():
                seen["state"] = integrations.state_of(fake)[0]
                seen["dup"] = integrations.connect("fake")
                release.set()
            message = integrations.connect("fake", on_started=started)
        self.assertEqual(message, "conectado")
        self.assertEqual(seen["state"], integrations.WAIT)
        self.assertIn("já estou esperando", seen["dup"])
        self.assertEqual(integrations.state_of(fake)[0], "off")  # wait some ao terminar

    def test_connect_exception_becomes_message(self):
        def boom():
            raise RuntimeError("rede caiu")
        with patch.object(integrations, "get", return_value=_fake(connect=boom)):
            self.assertIn("rede caiu", integrations.connect("fake"))
        self.assertFalse(integrations.is_waiting("fake"))

    def test_disconnect_without_handler(self):
        with patch.object(integrations, "get", return_value=_fake()):
            self.assertIn("não tem o que desconectar", integrations.disconnect("fake"))


if __name__ == "__main__":
    unittest.main()
