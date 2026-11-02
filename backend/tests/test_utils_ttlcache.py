"""Feature 2 (base) — TTLCache: hit/miss, expiração por TTL e evicção LRU."""
import unittest

from tests._stubs import install

install()

from core.utils import TTLCache


class FakeClock:
    """Relógio injetável para testes determinísticos (sem time.sleep real)."""
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


class TestTTLCache(unittest.TestCase):
    def test_hit_and_miss(self):
        c = TTLCache(maxsize=4, ttl=30, time_fn=FakeClock(0))
        self.assertIsNone(c.get("a"))      # miss
        c.set("a", 123)
        self.assertEqual(c.get("a"), 123)  # hit

    def test_expiration(self):
        clock = FakeClock(0)
        c = TTLCache(maxsize=4, ttl=30, time_fn=clock)
        c.set("a", 1)
        clock.t = 29
        self.assertEqual(c.get("a"), 1)    # ainda válido
        clock.t = 31
        self.assertIsNone(c.get("a"))      # vencido → miss
        # Entrada vencida é purgada no acesso
        self.assertNotIn("a", c._store)

    def test_lru_eviction(self):
        c = TTLCache(maxsize=2, ttl=30, time_fn=FakeClock(0))
        c.set("a", 1)
        c.set("b", 2)
        c.get("a")            # 'a' vira a mais recente; 'b' a mais antiga
        c.set("c", 3)         # excede maxsize → evicta 'b'
        self.assertIsNone(c.get("b"))
        self.assertEqual(c.get("a"), 1)
        self.assertEqual(c.get("c"), 3)

    def test_set_refreshes_expiry(self):
        clock = FakeClock(0)
        c = TTLCache(maxsize=4, ttl=10, time_fn=clock)
        c.set("a", 1)
        clock.t = 8
        c.set("a", 2)         # reescreve → novo expiry em t+10 = 18
        clock.t = 15
        self.assertEqual(c.get("a"), 2)   # ainda válido graças ao refresh


if __name__ == "__main__":
    unittest.main()
