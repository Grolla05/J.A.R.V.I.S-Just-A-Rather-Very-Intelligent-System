"""core.pending — ação crítica pendente: id, sem sobrescrita, prazo e leitura da resposta.

Cobre os Security Advisories GHSA-x47w (slot único sem lock) e GHSA-48jx
(qualquer frase com "pode/ok/vai" aprovava a ação).
"""
import threading
import unittest

from tests._stubs import install

install()

import core.state as state  # noqa: E402
from core import pending  # noqa: E402


def _noop():
    return "feito"


class PendingCase(unittest.TestCase):
    def setUp(self):
        self._saved = state.pending_critical_action
        state.pending_critical_action = None

    def tearDown(self):
        state.pending_critical_action = self._saved


class TestArmTake(PendingCase):
    def test_arm_creates_action_with_id(self):
        action_id = pending.arm("X", "Pergunta?", _noop, target="chrome.exe", clock=lambda: 100.0)
        self.assertTrue(action_id)
        current = state.pending_critical_action
        self.assertEqual((current["id"], current["type"], current["target"], current["timeout"]),
                         (action_id, "X", "chrome.exe", 130.0))

    def test_arm_never_overwrites_a_valid_action(self):
        first = pending.arm("A", "A?", _noop, clock=lambda: 100.0)
        self.assertIsNone(pending.arm("B", "B?", _noop, clock=lambda: 110.0))
        self.assertEqual(state.pending_critical_action["id"], first)
        # vencida: pode armar outra
        self.assertIsNotNone(pending.arm("B", "B?", _noop, clock=lambda: 200.0))
        self.assertEqual(state.pending_critical_action["type"], "B")

    def test_take_with_matching_id(self):
        action_id = pending.arm("A", "A?", _noop)
        action, status = pending.take(action_id)
        self.assertEqual((status, action["id"]), (pending.OK, action_id))
        self.assertIsNone(state.pending_critical_action)

    def test_take_with_other_id_keeps_the_new_action(self):
        pending.arm("A", "A?", _noop)
        action, status = pending.take("outro-id")
        self.assertEqual((action, status), (None, pending.REPLACED))
        self.assertIsNotNone(state.pending_critical_action)

    def test_take_empty_and_expired(self):
        self.assertEqual(pending.take(), (None, pending.EMPTY))
        pending.arm("A", "A?", _noop, clock=lambda: 100.0)
        self.assertEqual(pending.take(clock=lambda: 500.0), (None, pending.EXPIRED))
        self.assertIsNone(state.pending_critical_action)

    def test_active_drops_expired(self):
        pending.arm("A", "A?", _noop, clock=lambda: 100.0)
        self.assertIsNotNone(pending.active(clock=lambda: 120.0))
        self.assertIsNone(pending.active(clock=lambda: 500.0))
        self.assertIsNone(state.pending_critical_action)

    def test_concurrent_arm_only_one_wins(self):
        results = []
        barrier = threading.Barrier(8)

        def worker(i):
            barrier.wait()
            results.append(pending.arm(f"K{i}", "?", _noop))

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        winners = [r for r in results if r]
        self.assertEqual(len(winners), 1)
        self.assertEqual(state.pending_critical_action["id"], winners[0])


class TestParseReply(unittest.TestCase):
    def test_yes(self):
        for text in ("sim", "Sim.", "sim, pode encerrar", "pode fechar o chrome", "ok", "confirmo",
                     "pode sim, senhor", "encerra"):
            with self.subTest(text=text):
                self.assertEqual(pending.parse_reply(text, "chrome.exe"), pending.YES)

    def test_no(self):
        for text in ("não", "nao, pode manter", "Não, pode manter", "cancela", "deixa quieto", "negativo"):
            with self.subTest(text=text):
                self.assertEqual(pending.parse_reply(text, "chrome.exe"), pending.NO)

    def test_unrelated_phrases_never_approve(self):
        for text in ("pode me dizer o clima?", "vai chover amanhã", "pode tocar música",
                     "ok, abre o spotify e pode fechar tudo", "que horas são", "", "sim?"):
            with self.subTest(text=text):
                self.assertIsNone(pending.parse_reply(text, "chrome.exe"))


if __name__ == "__main__":
    unittest.main()
