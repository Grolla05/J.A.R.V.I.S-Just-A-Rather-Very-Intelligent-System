"""TUI — parser de /comandos."""
import unittest
from datetime import date

from frontend.commands import COMMANDS, help_markdown, parse, unescape
from frontend.widgets import format_slot_when


class TestFormatSlotWhen(unittest.TestCase):
    def test_today_yesterday_weekday_and_older(self):
        today = date(2026, 11, 6)  # sexta
        self.assertEqual(format_slot_when("2026-11-06 14:03:00", today), "hoje · 14:03")
        self.assertEqual(format_slot_when("2026-11-05 21:40:00", today), "ontem · 21:40")
        self.assertEqual(format_slot_when("2026-11-02 19:30:00", today), "seg · 19:30")
        self.assertEqual(format_slot_when("2026-10-25 10:05:00", today), "25/10 · 10:05")

    def test_invalid_is_blank(self):
        self.assertEqual(format_slot_when(None), "")


class TestCommandParser(unittest.TestCase):
    def test_plain_text_is_not_command(self):
        self.assertIsNone(parse("abre o spotify"))
        self.assertIsNone(parse(""))

    def test_double_slash_escapes_to_message(self):
        self.assertIsNone(parse("//etc/hosts é o quê?"))
        self.assertEqual(unescape("//etc/hosts"), "/etc/hosts")
        self.assertEqual(unescape("normal"), "normal")

    def test_command_with_argument(self):
        cmd = parse("/rename Ideias do projeto")
        self.assertEqual((cmd.name, cmd.arg, cmd.known), ("rename", "Ideias do projeto", True))

    def test_attach_keeps_path_with_spaces(self):
        cmd = parse('/attach C:\\Users\\eu\\Minhas Fotos\\a.png')
        self.assertEqual(cmd.name, "attach")
        self.assertEqual(cmd.arg, "C:\\Users\\eu\\Minhas Fotos\\a.png")

    def test_case_insensitive_and_aliases(self):
        self.assertEqual(parse("/NEW").name, "new")
        self.assertEqual(parse("/q").name, "quit")
        self.assertEqual(parse("/").name, "help")

    def test_unknown_command_flagged(self):
        cmd = parse("/foo bar")
        self.assertFalse(cmd.known)
        self.assertEqual(cmd.name, "foo")

    def test_help_lists_every_command(self):
        md = help_markdown()
        for usage, _ in COMMANDS.values():
            self.assertIn(usage.replace("|", chr(92) + "|"), md)

    def test_help_table_keeps_two_cells_with_pipes(self):
        from markdown_it import MarkdownIt
        tokens = MarkdownIt("gfm-like").parse(help_markdown())
        rows, cells = [], None
        for tok in tokens:
            if tok.type == "tr_open":
                cells = []
            elif tok.type == "inline" and cells is not None:
                cells.append(tok.children[0].content if tok.children else tok.content)
            elif tok.type == "tr_close":
                rows.append(cells)
                cells = None
        self.assertEqual(len(rows), len(COMMANDS) + 1)
        self.assertTrue(all(len(r) == 2 for r in rows))
        usages = [r[0] for r in rows[1:]]
        self.assertIn("/mode [chat|copilot]", usages)
        self.assertIn("/skills [on|off <skill|categoria>]", usages)


class TestSkillGlyphs(unittest.TestCase):
    def test_real_intents_have_their_own_icon(self):
        from frontend.screens.skills import FALLBACK_GLYPH, glyph_for
        expected = {"APP_CONTROL": "▣", "AUDIO_CONTROL": "♪", "SPOTIFY_CONTROL": "♫",
                    "KEYBOARD_CONTROL": "⌨", "SCREEN_CONTROL": "▦", "WORK_MACRO": "⚙",
                    "SYSTEM_REPORT": "≡", "SYSTEM_CLEANUP": "✕", "SYSTEM_SECURITY": "⛨"}
        for intent, glyph in expected.items():
            self.assertEqual(glyph_for(intent), glyph, intent)
        self.assertEqual(glyph_for("ALGO_NOVO"), FALLBACK_GLYPH)

    def test_glyphs_take_one_cell(self):
        from rich.cells import cell_len

        from frontend.screens.skills import _GLYPHS, FALLBACK_GLYPH, TAB
        for _, glyph in _GLYPHS:
            self.assertEqual(cell_len(glyph), 1, glyph)
        self.assertEqual(cell_len(FALLBACK_GLYPH), 1)
        self.assertEqual(cell_len(TAB), len(TAB))


class TestToolCommands(unittest.TestCase):
    def test_tool_commands_parse(self):
        self.assertEqual(parse("/web python 3.14"), parse("/web  python 3.14"))
        cmd = parse("/web python 3.14")
        self.assertEqual((cmd.name, cmd.arg, cmd.known), ("web", "python 3.14", True))
        for name in ("gh", "briefing", "clip"):
            self.assertIn(name, COMMANDS)

    def test_new_skills_have_icons(self):
        from frontend.screens.skills import FALLBACK_GLYPH, glyph_for
        for intent in ("WEB_SEARCH", "GITHUB", "DAILY_BRIEFING", "CLIPBOARD"):
            self.assertNotEqual(glyph_for(intent), FALLBACK_GLYPH, intent)


if __name__ == "__main__":
    unittest.main()
