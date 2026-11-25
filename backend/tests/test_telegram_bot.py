"""core.telegram_bot — long polling da Bot API com HTTP fake; core.messenger_ctl — quando a ponte sobe."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import messenger_ctl, telegram_bot  # noqa: E402


class Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data


def update(uid, text, chat_type="private", upd_id=1):
    return {"update_id": upd_id, "message": {"message_id": 5, "text": text,
                                             "from": {"id": uid, "is_bot": False},
                                             "chat": {"id": uid, "type": chat_type}}}


class TestParse(unittest.TestCase):
    def test_private_text_only(self):
        self.assertEqual(telegram_bot.parse_update(update(42, "oi")), (42, "42", "oi"))
        self.assertIsNone(telegram_bot.parse_update(update(42, "oi", chat_type="group")))
        self.assertIsNone(telegram_bot.parse_update({"update_id": 2, "message": {"chat": {"type": "private"}}}))
        self.assertIsNone(telegram_bot.parse_update({"update_id": 3}))


class TestPolling(unittest.TestCase):
    def test_poll_once_answers_and_advances_offset(self):
        http = MagicMock()
        http.get.return_value = Resp({"ok": True, "result": [update(42, "oi", upd_id=10),
                                                             update(42, "tudo bem?", upd_id=11)]})
        http.post.return_value = Resp({"ok": True})
        handler = MagicMock(side_effect=lambda ch, uid, text: [f"eco: {text}"])
        bridge = telegram_bot.TelegramBridge("TOKEN", handler, http=http)
        self.assertEqual(bridge.poll_once(), 2)
        self.assertEqual(bridge.offset, 12)
        self.assertEqual(handler.call_args_list[0].args, ("telegram", "42", "oi"))
        sent = [c for c in http.post.call_args_list if c.args[0].endswith("/sendMessage")]
        self.assertEqual([c.kwargs["json"]["text"] for c in sent], ["eco: oi", "eco: tudo bem?"])
        self.assertEqual(http.get.call_args.kwargs["params"]["timeout"], telegram_bot.POLL_TIMEOUT)

    def test_empty_reply_sends_nothing(self):
        http = MagicMock()
        http.get.return_value = Resp({"ok": True, "result": [update(99, "oi")]})
        bridge = telegram_bot.TelegramBridge("TOKEN", MagicMock(return_value=[]), http=http)
        bridge.poll_once()
        self.assertFalse([c for c in http.post.call_args_list if c.args[0].endswith("/sendMessage")])

    def test_token_never_logged_on_error(self):
        http = MagicMock()
        http.get.side_effect = ConnectionError("https://api.telegram.org/botSECRET123/getUpdates falhou")
        bridge = telegram_bot.TelegramBridge("SECRET123", MagicMock(), http=http)
        with patch.object(telegram_bot.log, "warning") as warn:
            self.assertEqual(bridge.poll_once(), 0)
        self.assertNotIn("SECRET123", " ".join(str(c) for c in warn.call_args_list))


class TestMessengerCtl(unittest.TestCase):
    def test_enabled_needs_pref_and_a_token_per_channel(self):
        prefs = {"telegram": True, "discord": False}
        with patch.object(messenger_ctl, "_pref", side_effect=lambda ch: prefs[ch]),              patch.object(messenger_ctl.settings, "TELEGRAM_BOT_TOKEN", ""),              patch.object(messenger_ctl.settings, "DISCORD_BOT_TOKEN", "d"):
            self.assertFalse(messenger_ctl.should_run())          # Telegram ligado mas sem token
        with patch.object(messenger_ctl, "_pref", side_effect=lambda ch: prefs[ch]),              patch.object(messenger_ctl.settings, "TELEGRAM_BOT_TOKEN", "t"),              patch.object(messenger_ctl.settings, "DISCORD_BOT_TOKEN", "d"):
            self.assertEqual(messenger_ctl.active_channels(), {"telegram"})
            self.assertTrue(messenger_ctl.should_run())

    def test_start_spawns_only_when_not_running(self):
        popen = MagicMock()
        with patch.object(messenger_ctl, "is_running", return_value=True):
            self.assertTrue(messenger_ctl.start(popen=popen))
        popen.assert_not_called()
        with patch.object(messenger_ctl, "is_running", return_value=False):
            self.assertTrue(messenger_ctl.start(popen=popen))
        args = popen.call_args.args[0]
        self.assertTrue(args[1].endswith("messenger.py"))


if __name__ == "__main__":
    unittest.main()
