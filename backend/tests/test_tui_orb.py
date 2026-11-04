"""Orb pixel-art do Copilot — lógica pura (frontend/orb.py)."""
import unittest

import tests  # noqa: F401  (põe a raiz no sys.path)
from frontend import orb


def _codes(grid):
    return {c for row in grid for c in row if c is not None}


class TestOrbGrid(unittest.TestCase):
    def test_grid_is_16x16(self):
        for state in orb.STATES:
            for n in range(orb.frame_count(state)):
                grid = orb.frame(state, n)
                self.assertEqual(len(grid), orb.SIZE)
                self.assertTrue(all(len(row) == orb.SIZE for row in grid))

    def test_sprite_shape_is_symmetric(self):
        filled = [[c is not None for c in row] for row in orb.frame("ouvindo")]
        for row in filled:
            self.assertEqual(row, row[::-1])
        self.assertEqual(filled, filled[::-1])

    def test_ouvindo_is_blue_ball_with_full_white_ring(self):
        codes = _codes(orb.frame("ouvindo"))
        self.assertEqual(codes, {orb.RING, orb.CORE, orb.SHADE, orb.HL})
        self.assertEqual(orb.frame_count("ouvindo"), 1)

    def test_pensando_is_all_white(self):
        for n in range(orb.frame_count("pensando")):
            self.assertTrue(_codes(orb.frame("pensando", n)) <= {orb.WHITE, orb.WHITE_DIM})

    def test_pensando_pulses(self):
        frames = [orb.frame("pensando", n) for n in range(orb.frame_count("pensando"))]
        self.assertNotEqual(frames[0], frames[2])
        self.assertEqual(frames[1], frames[3])  # vai e volta

    def test_respondendo_gap_walks_around_ring(self):
        seen = set()
        for n in range(orb.frame_count("respondendo")):
            grid = orb.frame("respondendo", n)
            dim = {orb.BASE[y][x][1] for y, row in enumerate(grid)
                   for x, c in enumerate(row) if c == orb.RING_DIM}
            self.assertEqual(dim, orb.dimmed_octants(n))
            self.assertEqual(len(dim), orb.GAP)
            # a bola continua azul enquanto responde
            self.assertIn(orb.CORE, _codes(grid))
            seen |= dim
        self.assertEqual(seen, set(range(orb.OCTANTS)))

    def test_frames_wrap_around(self):
        self.assertEqual(orb.frame("respondendo", 0), orb.frame("respondendo", orb.OCTANTS))

    def test_halfblocks_are_16_cols_by_8_rows(self):
        rows = orb.to_halfblocks(orb.frame("ouvindo"))
        self.assertEqual(len(rows), orb.SIZE // 2)
        self.assertTrue(all(len(r) == orb.SIZE for r in rows))

    def test_halfblock_chars(self):
        self.assertEqual(orb.to_halfblocks([[None, "a", None, "a"], [None, None, "b", "b"]]),
                         [[(" ", None, None), ("▀", "a", None), ("▄", "b", None), ("▀", "a", "b")]])
        self.assertEqual(orb.to_halfblocks([["a"], ["a"]]), [[("█", "a", None)]])


if __name__ == "__main__":
    unittest.main()
