"""core.pending — dono da pendência (TUI × ponte Telegram/Discord) e `on_other` (ajuste sem cancelar)."""
import unittest
from unittest.mock import MagicMock

from tests._stubs import install

install()

import core.state as state  # noqa: E402
import services.brain as brain  # noqa: E402
from core import pending  # noqa: E402


class OwnerCase(unittest.TestCase):
    def setUp(self):
        self._saved = state.pending_critical_action
        state.pending_critical_action = None

    def tearDown(self):
        state.pending_critical_action = self._saved

    def test_default_owner_is_local(self):
        pending.arm("X", "Confirma?", lambda: "feito")
        self.assertEqual(state.pending_critical_action["owner"], pending.LOCAL)

    def test_other_owner_never_consumes(self):
        on_confirm = MagicMock(return_value="enviado")
        pending.arm("EMAIL_SEND", "Envio?", on_confirm, owner="telegram:42")
        self.assertIsNone(brain._check_pending_action("sim"))                      # TUI: não é dela
        self.assertIsNone(brain._check_pending_action("sim", owner="discord:7"))   # outro usuário
        on_confirm.assert_not_called()
        self.assertIsNotNone(state.pending_critical_action)
        self.assertEqual(brain._check_pending_action("sim", owner="telegram:42"), "enviado")
        on_confirm.assert_called_once()

    def test_on_other_gets_the_phrase_and_keeps_the_flow(self):
        def adjust(command):
            pending.arm("EMAIL_SEND", "Novo rascunho. Envio?", lambda: "enviado", on_other=adjust)
            return f"ajustado: {command}"

        pending.arm("EMAIL_SEND", "Envio?", lambda: "enviado", on_other=adjust)
        self.assertEqual(brain._check_pending_action("deixa mais formal"), "ajustado: deixa mais formal")
        self.assertEqual(state.pending_critical_action["question"], "Novo rascunho. Envio?")
        self.assertEqual(brain._check_pending_action("sim"), "enviado")

    def test_negation_still_beats_on_other(self):
        other, decline = MagicMock(return_value="x"), MagicMock(return_value="rascunho salvo")
        pending.arm("EMAIL_SEND", "Envio?", lambda: "enviado", on_decline=decline, on_other=other)
        self.assertEqual(brain._check_pending_action("não"), "rascunho salvo")
        other.assert_not_called()

    def test_on_other_returning_none_discards(self):
        pending.arm("EMAIL_SEND", "Envio?", lambda: "enviado", on_other=lambda c: None)
        self.assertIsNone(brain._check_pending_action("que horas são"))
        self.assertIsNone(state.pending_critical_action)


if __name__ == "__main__":
    unittest.main()
