"""services.remote_chat — núcleo da ponte Telegram/Discord (sem rede)."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import pending  # noqa: E402
from services import remote_chat as rc  # noqa: E402


class FakeDb:
    def __init__(self):
        self.data, self.history = {}, []

    def get_config(self, key):
        return self.data.get(key)

    def save_config(self, key, value):
        self.data[key] = value

    def log_interaction(self, role, content, session_id="default", *a, mode=None, **k):
        self.history.append((role, content, session_id, mode))


class RemoteCase(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.stream = MagicMock(side_effect=lambda *a, **k: iter(["Olá, ", "Senhor."]))
        self._patches = [patch.object(rc, "db", self.db),
                         patch.object(rc, "_set_title", MagicMock()),
                         patch.object(rc.settings, "TELEGRAM_ALLOWED_IDS", ("42",)),
                         patch.object(rc.settings, "DISCORD_ALLOWED_IDS", ("7",))]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()

    def _send(self, text, channel=rc.TELEGRAM, user="42"):
        return rc.handle_message(channel, user, text, stream_fn=self.stream)


class TestAccess(RemoteCase):
    def test_stranger_is_ignored_except_id(self):
        self.assertEqual(self._send("oi", user="99"), [])
        self.stream.assert_not_called()
        reply = self._send("/id", user="99")
        self.assertIn("99", reply[0])
        self.assertIn("TELEGRAM_ALLOWED_IDS", reply[0])

    def test_empty_allowlist_refuses_everyone(self):
        with patch.object(rc.settings, "TELEGRAM_ALLOWED_IDS", ()):
            self.assertEqual(self._send("oi"), [])
        self.stream.assert_not_called()

    def test_channels_have_separate_allowlists(self):
        self.assertEqual(self._send("oi", channel=rc.DISCORD, user="42"), [])
        self.assertEqual(self._send("oi", channel=rc.DISCORD, user="7"), ["Olá, Senhor."])


class TestChat(RemoteCase):
    def test_goes_to_brain_in_chat_mode_with_owner_and_logs(self):
        self.assertEqual(self._send("qual a capital da frança?"), ["Olá, Senhor."])
        args, kwargs = self.stream.call_args
        self.assertEqual(args[0], "qual a capital da frança?")
        self.assertEqual(kwargs["mode"], "chat")
        self.assertEqual(kwargs["owner"], "telegram:42")
        session = kwargs["session_id"]
        self.assertTrue(session.startswith("telegram-42"))
        self.assertEqual([h[:2] for h in self.db.history],
                         [("user", "qual a capital da frança?"), ("assistant", "Olá, Senhor.")])
        self.assertEqual({h[3] for h in self.db.history}, {"remote"})

    def test_same_session_until_nova(self):
        self._send("a")
        first = self.stream.call_args.kwargs["session_id"]
        self._send("b")
        self.assertEqual(self.stream.call_args.kwargs["session_id"], first)
        self.assertIn("Nova conversa", self._send("/nova")[0])
        self._send("c")
        self.assertNotEqual(self.stream.call_args.kwargs["session_id"], first)

    def test_brain_error_is_a_reply(self):
        self.stream.side_effect = RuntimeError("ollama fora")
        reply = self._send("oi")
        self.assertIn("Não consegui", reply[0])

    def test_commands(self):
        with patch.object(rc, "_email_text", return_value="**E-mails**"), \
             patch.object(rc, "_briefing_text", return_value="Bom dia"):
            self.assertEqual(self._send("/email"), ["**E-mails**"])
            self.assertEqual(self._send("/briefing"), ["Bom dia"])
        self.assertIn("J.A.R.V.I.S", self._send("/start")[0])
        self.stream.assert_not_called()


class TestSplit(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(rc.split_message("oi", 100), ["oi"])
        self.assertEqual(rc.split_message("", 100), [])

    def test_splits_on_paragraphs_under_limit(self):
        text = "\n\n".join(f"parágrafo {i} " + "x" * 40 for i in range(10))
        parts = rc.split_message(text, 120)
        self.assertTrue(all(len(p) <= 120 for p in parts))
        self.assertEqual("".join(parts).replace("\n", ""), text.replace("\n", ""))

    def test_hard_split_long_line(self):
        parts = rc.split_message("y" * 250, 100)
        self.assertEqual([len(p) for p in parts], [100, 100, 50])


class TestPendingOwner(RemoteCase):
    def test_owner_is_passed_through_so_yes_only_answers_own_pending(self):
        self._send("manda e-mail")
        self.assertEqual(self.stream.call_args.kwargs["owner"], "telegram:42")
        self.assertEqual(pending.LOCAL, "local")


if __name__ == "__main__":
    unittest.main()
