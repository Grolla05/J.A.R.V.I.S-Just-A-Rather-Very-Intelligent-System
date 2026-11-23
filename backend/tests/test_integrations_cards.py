"""Cards novos de /config → INTEGRAÇÕES: Gmail, Telegram, Discord e Downloads (winget)."""
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

from core import discord_bot, gmail, messenger_ctl, winget  # noqa: E402
from core.config import settings  # noqa: E402
from services import integrations, user_prefs  # noqa: E402


class TestCards(unittest.TestCase):
    def setUp(self):
        integrations._registry.clear()
        integrations._winget_cache.clear()

    def test_registry_has_new_cards(self):
        ids = [i.id for i in integrations.all_integrations()]
        for card in ("gmail", "telegram", "discord", "winget"):
            self.assertIn(card, ids)

    def test_gmail_states(self):
        card = integrations.get("gmail")
        with patch.object(gmail, "is_configured", return_value=False):
            self.assertEqual(integrations.state_of(card)[0], integrations.SETUP)
        with patch.object(gmail, "is_configured", return_value=True), \
             patch.object(gmail, "is_connected", return_value=True), \
             patch.object(gmail.account, "account", return_value="eu@gmail.com"):
            self.assertEqual(integrations.state_of(card), (integrations.ON, "conta: eu@gmail.com"))

    def test_bridge_needs_token_and_allowlist(self):
        card = integrations.get("telegram")
        with patch.object(settings, "TELEGRAM_BOT_TOKEN", ""):
            state, detail = integrations.state_of(card)
        self.assertEqual(state, integrations.SETUP)
        self.assertIn("TELEGRAM_BOT_TOKEN", detail)
        with patch.object(settings, "TELEGRAM_BOT_TOKEN", "t"), patch.object(settings, "TELEGRAM_ALLOWED_IDS", ()):
            self.assertIn("TELEGRAM_ALLOWED_IDS", integrations.state_of(card)[1])

    def test_bridge_connect_turns_pref_on_and_starts(self):
        saved = {}
        with patch.object(settings, "TELEGRAM_BOT_TOKEN", "t"), \
             patch.object(settings, "TELEGRAM_ALLOWED_IDS", ("42",)), \
             patch.object(user_prefs, "get", side_effect=lambda k: saved.get(k, False)), \
             patch.object(user_prefs, "set", side_effect=lambda k, v: saved.__setitem__(k, v)), \
             patch.object(messenger_ctl, "start", return_value=True) as start, \
             patch.object(messenger_ctl, "is_running", return_value=True):
            text = integrations.connect("telegram")
            self.assertIn("ligada", text)
            self.assertTrue(saved["remote_telegram"])
            start.assert_called_once()
            self.assertEqual(integrations.state_of(integrations.get("telegram"))[0], integrations.ON)
            self.assertIn("desligada", integrations.disconnect("telegram"))
            self.assertFalse(saved["remote_telegram"])

    def test_discord_without_lib_is_setup(self):
        with patch.object(settings, "DISCORD_BOT_TOKEN", "d"), \
             patch.object(settings, "DISCORD_ALLOWED_IDS", ("7",)), \
             patch.object(discord_bot, "available", return_value=False):
            state, detail = integrations.state_of(integrations.get("discord"))
        self.assertEqual(state, integrations.SETUP)
        self.assertIn("discord.py", detail)

    def test_winget_card(self):
        with patch.object(winget, "available", return_value=True):
            self.assertEqual(integrations.state_of(integrations.get("winget"))[0], integrations.ON)
        integrations._winget_cache.clear()
        with patch.object(winget, "available", return_value=False):
            self.assertEqual(integrations.state_of(integrations.get("winget"))[0], integrations.SETUP)


if __name__ == "__main__":
    unittest.main()
