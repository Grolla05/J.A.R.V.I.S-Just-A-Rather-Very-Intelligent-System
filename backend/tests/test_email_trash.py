"""services.email_trash + skill EMAIL_TRASH — "apaga o e-mail 3" move para a Lixeira, só depois do "sim"."""
import importlib.util
import os
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

import core.state as state  # noqa: E402
import services.brain as brain  # noqa: E402
from core import gmail, pending  # noqa: E402
from services import email_trash, mailbox  # noqa: E402

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "productivity",
                    "email_trash.py")


def msg(i, subject, labels=(), name="Loja"):
    return {"id": i, "thread_id": i, "subject": subject, "from_addr": "x@y.com", "from_name": name,
            "labels": ["INBOX", *labels], "unread": True, "snippet": "", "date": "", "band": "BAIXA", "score": 0}


LISTED = [msg("a", "Prova amanhã", ["IMPORTANT"], "Prof. Ana"),
          msg("b", "Black Friday 70% OFF", ["CATEGORY_PROMOTIONS"]),
          msg("c", "Cupom de desconto", ["CATEGORY_PROMOTIONS"]),
          msg("d", "Fulano comentou", ["CATEGORY_SOCIAL"], "Rede")]


class TrashCase(unittest.TestCase):
    def setUp(self):
        self._saved = state.pending_critical_action
        state.pending_critical_action = None
        mailbox._last[:] = LISTED
        self._patches = [patch.object(gmail, "is_configured", return_value=True),
                         patch.object(gmail, "is_connected", return_value=True)]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        mailbox._last.clear()
        state.pending_critical_action = self._saved


class TestSelect(TrashCase):
    def test_numbers(self):
        self.assertEqual([m["id"] for m in email_trash.select("apaga o e-mail 2")], ["b"])
        self.assertEqual([m["id"] for m in email_trash.select("apaga os e-mails 1, 3 e 4")], ["a", "c", "d"])
        self.assertEqual(email_trash.select("apaga o e-mail 9"), [])

    def test_categories(self):
        self.assertEqual([m["id"] for m in email_trash.select("apaga as promoções")], ["b", "c"])
        self.assertEqual([m["id"] for m in email_trash.select("joga fora as notificações de rede social")], ["d"])

    def test_nothing_clear_selects_nothing(self):
        self.assertEqual(email_trash.select("apaga meus e-mails"), [])   # "todos" sem número não apaga nada


class TestRequest(TrashCase):
    def test_asks_then_trashes_after_yes(self):
        with patch.object(gmail, "trash", return_value=2) as trash:
            text = email_trash.request("apaga os e-mails 2 e 3")
            trash.assert_not_called()
            self.assertIn("Black Friday", text)
            self.assertIn("Cupom", text)
            self.assertIn("Lixeira", text)
            self.assertEqual(state.pending_critical_action["type"], "EMAIL_TRASH")
            reply = brain._check_pending_action("sim")
        trash.assert_called_once_with(["b", "c"])
        self.assertIn("30 dias", reply)
        self.assertNotIn("b", [m["id"] for m in mailbox._last])      # some da lista vista

    def test_decline_keeps(self):
        with patch.object(gmail, "trash") as trash:
            email_trash.request("apaga o e-mail 2")
            reply = brain._check_pending_action("não")
        trash.assert_not_called()
        self.assertIn("Nada", reply)

    def test_unclear_asks_which(self):
        text = email_trash.request("apaga meus e-mails")
        self.assertIn("Quais", text)
        self.assertIsNone(state.pending_critical_action)

    def test_empty_list_fetches_first(self):
        mailbox._last.clear()
        with patch.object(mailbox, "priority", side_effect=lambda: mailbox._last.extend(LISTED) or LISTED):
            text = email_trash.request("apaga o e-mail 2")
        self.assertIn("Black Friday", text)

    def test_busy_and_errors(self):
        pending.arm("X", "outra?", lambda: "x")
        self.assertEqual(email_trash.request("apaga o e-mail 2"), pending.BUSY_REPLY)
        state.pending_critical_action = None
        email_trash.request("apaga o e-mail 2")
        with patch.object(gmail, "trash", side_effect=gmail.GmailError("Gmail fora")):
            self.assertIn("Gmail fora", brain._check_pending_action("sim"))

    def test_not_connected(self):
        with patch.object(gmail, "is_connected", return_value=False):
            self.assertIn("INTEGRAÇÕES", email_trash.request("apaga o e-mail 2"))


class TestSkill(TrashCase):
    def test_contract(self):
        spec = importlib.util.spec_from_file_location("email_trash_skill", PATH)
        skill = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(skill)
        self.assertEqual(skill.INTENT, "EMAIL_TRASH")
        with patch.object(email_trash, "request", return_value="pergunta") as req:
            self.assertEqual(skill.execute("3", "apaga o e-mail 3"), "pergunta")
        req.assert_called_once_with("3 apaga o e-mail 3")


if __name__ == "__main__":
    unittest.main()
