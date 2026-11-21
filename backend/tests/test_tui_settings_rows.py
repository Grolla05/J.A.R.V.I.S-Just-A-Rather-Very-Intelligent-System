"""/config em seções — lógica pura (frontend/screens/settings_rows.py)."""
import unittest

import tests  # noqa: F401  (põe a raiz no sys.path)
from frontend.screens import settings_rows as sr
from services import user_prefs


def _plain(segs):
    return "".join(t for t, _ in segs)


def _styles(segs):
    return {s for _, s in segs}


class TestSections(unittest.TestCase):
    def test_every_pref_lives_in_exactly_one_section(self):
        keys = [k for group in ("VOZ", "MICROFONE", "ROTINAS") for s in sr.SECTIONS[group] for k in s.keys]
        self.assertEqual(sorted(keys), sorted(k for g in user_prefs.GROUPS.values() for k in g))
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_key_has_help_without_emoji(self):
        keys = [k for sections in sr.SECTIONS.values() for s in sections for k in s.keys]
        for key in keys:
            self.assertTrue(sr.HELP.get(key), key)
            self.assertTrue(all(ord(ch) < 0x1F000 for ch in sr.HELP[key]), key)  # emoji ocupa 2 colunas

    def test_rotinas_splits_in_two_columns(self):
        cols = {s.column for s in sr.SECTIONS["ROTINAS"]}
        self.assertEqual(cols, {0, 1})
        self.assertEqual([s.title for s in sr.SECTIONS["ROTINAS"]],
                         ["BRIEFING", "ASSISTENTE", "SEGURANÇA", "AGENDA", "SILÊNCIO & PALCO"])


class TestRowSegments(unittest.TestCase):
    def test_toggle_is_a_badge_not_a_bar(self):
        on = sr.RowState("x", "Vigia de rede", "ligado", toggle=True, on=True)
        segs = sr.row_segments(on, 50)
        self.assertIn("● ON", _plain(segs))
        self.assertIn("on", _styles(segs))
        self.assertNotIn("▰", _plain(segs))
        off = sr.row_segments(sr.RowState("x", "Vigia", "desligado", toggle=True, on=False), 50)
        self.assertIn("○ OFF", _plain(off))

    def test_width_is_exact_and_name_truncates(self):
        row = sr.RowState("x", "Um nome muito comprido demais para caber", "ligado", toggle=True, on=True)
        for width in (40, 50, 80):
            self.assertEqual(len(_plain(sr.row_segments(row, width))), width)
        self.assertIn("…", _plain(sr.row_segments(row, 40)))

    def test_arrows_only_on_focus(self):
        row = sr.RowState("x", "Aviso final", "15 min antes", pos=3, total=5)
        self.assertNotIn("◀", _plain(sr.row_segments(row, 50)))
        focused = sr.row_segments(row, 50, focused=True)
        self.assertIn("◀", _plain(focused))
        self.assertTrue(_plain(focused).startswith("▌"))

    def test_choice_shows_compact_value_and_position_dots(self):
        segs = sr.row_segments(sr.RowState("x", "Antecedência", "120 min antes", pos=2, total=4), 50)
        self.assertIn("120 min", _plain(segs))
        self.assertNotIn("antes", _plain(segs))
        dots = [s for t, s in segs if t == "▮"]
        self.assertEqual(dots, ["dot-past", "dot-past", "dot-now", "dot-next"])

    def test_off_choice_is_muted(self):
        segs = sr.row_segments(sr.RowState("x", "Aviso de saída", "desligado", pos=0, total=9), 50)
        self.assertIn("muted", _styles(segs))

    def test_flash_frames(self):
        row = sr.RowState("x", "Vigia", "ligado", toggle=True, on=True)
        self.assertIn("○──●", _plain(sr.row_segments(row, 50, flash=sr.FLASH_FRAMES)))  # desliza
        last = sr.row_segments(row, 50, flash=1)
        self.assertIn("● ON", _plain(last))
        self.assertIn("flash", _styles(last))                                          # pisca

    def test_custom_badge_text(self):
        segs = sr.row_segments(sr.RowState("agent", "Agente", "parado", toggle=True), 50,
                               on_text="RODANDO", off_text="PARADO")
        self.assertIn("○ PARADO", _plain(segs))


class TestHelpers(unittest.TestCase):
    def test_summary_counts_on_toggles_and_set_choices(self):
        rows = [sr.RowState("a", "a", "ligado", toggle=True, on=True),
                sr.RowState("b", "b", "desligado", toggle=True, on=False),
                sr.RowState("c", "c", "desligado", pos=0, total=9),
                sr.RowState("d", "d", "15 min antes", pos=3, total=5)]
        self.assertEqual(sr.summary(rows), (2, 4))

    def test_typed_reveals_chars_per_frame(self):
        text = "x" * 70
        self.assertEqual(sr.typed(text, 0), "")
        self.assertEqual(len(sr.typed(text, 1)), sr.QUIP_CHARS)
        self.assertEqual(sr.typed(text, 3), text)

    def test_short_labels(self):
        self.assertEqual(sr.short_label("dnd_auto_meeting", "Silenciar em reunião"), "Em reunião")
        self.assertEqual(sr.short_label("net_monitor", "Vigia de rede"), "Vigia de rede")


if __name__ == "__main__":
    unittest.main()
