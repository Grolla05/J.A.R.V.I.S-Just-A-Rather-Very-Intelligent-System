"""Sprites e efeitos 16-bit — lógica pura (frontend/sprites.py) + PixelSprite."""
import unittest

import tests  # noqa: F401  (põe a raiz no sys.path)
from frontend import orb, sprites


class TestSprites(unittest.TestCase):
    def test_every_sprite_has_even_rows_and_known_codes(self):
        for name in sprites.names():
            grid = sprites.sprite(name)
            self.assertEqual(len(grid) % 2, 0, name)
            width = len(grid[0])
            self.assertTrue(all(len(row) == width for row in grid), name)
            codes = {c for row in grid for c in row if c is not None}
            self.assertTrue(codes <= set(sprites.CODES), name)
            # renderiza em meio-bloco sem erro
            self.assertEqual(len(orb.to_halfblocks(grid)), len(grid) // 2)

    def test_recolor_swaps_codes(self):
        grid = sprites.sprite("mini_orb", recolor={sprites.NEON: sprites.WARN})
        codes = {c for row in grid for c in row if c}
        self.assertIn(sprites.WARN, codes)
        self.assertNotIn(sprites.NEON, codes)

    def test_radar_has_8_distinct_frames(self):
        frames = [sprites.radar(n) for n in range(sprites.RADAR_FRAMES)]
        self.assertEqual(len({str(f) for f in frames}), sprites.RADAR_FRAMES)
        self.assertEqual(sprites.radar(0), sprites.radar(sprites.RADAR_FRAMES))
        self.assertEqual(len(frames[0]) % 2, 0)


class TestEffects(unittest.TestCase):
    def test_block_bar(self):
        self.assertEqual(sprites.block_bar(0), "▱▱▱▱▱")
        self.assertEqual(sprites.block_bar(41), "▰▰▱▱▱")
        self.assertEqual(sprites.block_bar(100), "▰▰▰▰▰")
        self.assertEqual(sprites.block_bar(250), "▰▰▰▰▰")
        self.assertEqual(sprites.block_bar(None), "▱▱▱▱▱")
        self.assertEqual(sprites.block_bar(50, 10, "█", "░"), "█████░░░░░")

    def test_sparkline(self):
        self.assertEqual(sprites.sparkline([0, 50, 100]), "▁▅█")
        self.assertEqual(sprites.sparkline([100] * 30, width=4), "████")
        self.assertEqual(sprites.sparkline([0], width=3), "  ▁")

    def test_bar_chart(self):
        lines = sprites.bar_chart([0, 50, 100], width=4, height=2)
        self.assertEqual(lines, ["   █", "  ██"])
        self.assertTrue(all(len(line) == 4 for line in lines))
        self.assertEqual(sprites.bar_chart([12.5], width=1, height=1), ["▁"])
        self.assertEqual(sprites.bar_chart([], width=3, height=1), ["   "])

    def test_load_level(self):
        self.assertEqual(sprites.load_level(10), "baixa")
        self.assertEqual(sprites.load_level(70), "moderada")
        self.assertEqual(sprites.load_level(95), "alta")
        self.assertEqual(sprites.load_level(None), "baixa")

    def test_crt_frames_collapse_to_a_dot(self):
        frames = sprites.crt_frames(20, 9)
        self.assertEqual(len(frames), sprites.CRT_FRAMES)
        for f in frames:
            self.assertEqual(len(f), 9)
            self.assertTrue(all(len(line) == 20 for line in f))

        def lit(frame):
            return sum(ch != " " for line in frame for ch in line)

        counts = [lit(f) for f in frames]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertEqual(counts[-1], 1)

    def test_scanline_reveal(self):
        lines = ["abc", "def", "ghi"]
        self.assertEqual(sprites.scanline_reveal(lines, 0), ["   ", "   ", "   "])
        self.assertEqual(sprites.scanline_reveal(lines, 2), ["abc", "def", "   "])
        self.assertEqual(sprites.scanline_reveal(lines, 9), lines)


if __name__ == "__main__":
    unittest.main()
