"""TUI — parser de /comandos."""
import unittest
from datetime import date

from frontend.commands import COMMANDS, help_markdown, parse, unescape
from frontend.widgets import format_when


class TestFormatWhen(unittest.TestCase):
    def test_today_yesterday_and_older(self):
        today = date(2026, 11, 3)
        self.assertEqual(format_when("2026-11-03 14:02:10", today), "14:02")
        self.assertEqual(format_when("2026-11-02 23:59:59", today), "ontem")
        self.assertEqual(format_when("2026-10-28 08:00:00", today), "28/10")

    def test_invalid_is_blank(self):
        self.assertEqual(format_when(None), "")
        self.assertEqual(format_when("ontem"), "")


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
            self.assertIn(usage, md)


if __name__ == "__main__":
    unittest.main()
