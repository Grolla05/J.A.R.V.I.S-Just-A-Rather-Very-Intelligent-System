"""services.email_organize — plano de organização, aplicado só depois do "sim"; nunca apaga."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.state as state  # noqa: E402
import services.brain as brain  # noqa: E402
from core import gmail  # noqa: E402
from services import email_organize as organize  # noqa: E402


def msg(i, subject, labels=()):
    return {"id": i, "thread_id": i, "subject": subject, "from_addr": "x@y.com", "from_name": "X",
            "labels": ["INBOX", *labels], "unread": True, "snippet": "", "date": ""}


INBOX = [msg("p1", "Black Friday 70% OFF", ["CATEGORY_PROMOTIONS"]),
         msg("s1", "Fulano comentou", ["CATEGORY_SOCIAL"]),
         msg("f1", "Sua fatura chegou"),
         msg("u1", "URGENTE: prazo hoje", ["IMPORTANT"]),
         msg("o1", "Almoço sexta?")]


class OrganizeCase(unittest.TestCase):
    def setUp(self):
        self._saved = state.pending_critical_action
        state.pending_critical_action = None

    def tearDown(self):
        state.pending_critical_action = self._saved

    def test_plan(self):
        plan = organize.build_plan(INBOX, vip=set())
        self.assertEqual(sorted(plan["archive"]), ["p1", "s1"])
        self.assertEqual(plan["labels"][organize.LABEL_FINANCE], ["f1"])
        self.assertEqual(plan["labels"][organize.LABEL_URGENT], ["u1"])
        self.assertEqual(plan["star"], ["u1"])
        self.assertNotIn("o1", str(plan))
        text = organize.plan_text(plan)
        self.assertIn("2", text)
        self.assertIn("arquivar", text)

    def test_nothing_to_do(self):
        self.assertIn("em ordem", organize.organize(fetch=lambda **k: [msg("o1", "Oi")]))
        self.assertIsNone(state.pending_critical_action)

    def test_applies_only_after_yes_and_never_deletes(self):
        with patch.object(gmail, "batch_modify") as modify, patch.object(gmail, "ensure_label",
                                                                       side_effect=lambda n: f"id:{n}"):
            text = organize.organize(fetch=lambda **k: INBOX)
            self.assertIn("Confirma", text)
            modify.assert_not_called()
            reply = brain._check_pending_action("sim")
        self.assertIn("organizad", reply.lower())
        calls = [c.kwargs for c in modify.call_args_list]
        self.assertIn({"ids": ["p1", "s1"], "add": [], "remove": ["INBOX", "UNREAD"]},
                      [{**c, "ids": sorted(c["ids"])} for c in calls])
        self.assertTrue(any(c["add"] == ["STARRED"] for c in calls))
        self.assertFalse(hasattr(gmail, "delete"))

    def test_decline_does_nothing(self):
        with patch.object(gmail, "batch_modify") as modify:
            organize.organize(fetch=lambda **k: INBOX)
            brain._check_pending_action("não")
        modify.assert_not_called()

    def test_gmail_error_is_text(self):
        self.assertIn("off", organize.organize(fetch=MagicMock(side_effect=gmail.GmailError("off"))))


if __name__ == "__main__":
    unittest.main()
