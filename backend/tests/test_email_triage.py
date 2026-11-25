"""services.email_triage — prioridade e categoria dos e-mails (lógica pura)."""
import unittest

from tests._stubs import install

install()

from services import email_triage as triage  # noqa: E402


def msg(subject="Oi", sender="x@y.com", labels=(), unread=True, name="X"):
    return {"id": subject, "thread_id": subject, "subject": subject, "from_addr": sender, "from_name": name,
            "labels": list(labels), "unread": unread, "snippet": "", "date": ""}


class TestScore(unittest.TestCase):
    def test_bands(self):
        urgent = msg("URGENTE: prazo da entrega hoje", labels=["IMPORTANT"])
        promo = msg("50% OFF só hoje", labels=["CATEGORY_PROMOTIONS"], unread=False)
        self.assertEqual(triage.band(triage.score(urgent)), triage.HIGH)
        self.assertEqual(triage.band(triage.score(promo)), triage.LOW)

    def test_vip_sender_raises_priority(self):
        plain = msg("Reunião", sender="chefe@empresa.com")
        self.assertGreater(triage.score(plain, vip={"chefe@empresa.com"}), triage.score(plain))
        self.assertEqual(triage.band(triage.score(plain, vip={"chefe@empresa.com"})), triage.HIGH)

    def test_prioritize_sorts_high_first_and_annotates(self):
        items = triage.prioritize([msg("Newsletter semanal", labels=["CATEGORY_PROMOTIONS"]),
                                   msg("Fatura vence amanhã", labels=["IMPORTANT"])], vip=set())
        self.assertEqual(items[0]["subject"], "Fatura vence amanhã")
        self.assertIn("band", items[0])

    def test_categories(self):
        self.assertEqual(triage.category(msg("Sua fatura de novembro")), triage.FINANCE)
        self.assertEqual(triage.category(msg("Oferta", labels=["CATEGORY_PROMOTIONS"])), triage.PROMO)
        self.assertEqual(triage.category(msg("Fulano curtiu", labels=["CATEGORY_SOCIAL"])), triage.SOCIAL)
        self.assertEqual(triage.category(msg("URGENTE: servidor caiu")), triage.URGENT)
        self.assertEqual(triage.category(msg("Almoço?")), triage.OTHER)

    def test_markdown_and_summary(self):
        items = triage.prioritize([msg("Prova amanhã", labels=["IMPORTANT"], name="Prof. Ana"),
                                   msg("Promo", labels=["CATEGORY_PROMOTIONS"])], vip=set())
        md = triage.markdown(items)
        self.assertIn("1.", md)
        self.assertIn("Prof. Ana", md)
        self.assertIn("ALTA", md)
        short = triage.summary(items)
        self.assertNotIn("**", short)
        self.assertIn("Prova amanhã", short)
        self.assertIn("caixa vazia", triage.summary([]).lower())


if __name__ == "__main__":
    unittest.main()
