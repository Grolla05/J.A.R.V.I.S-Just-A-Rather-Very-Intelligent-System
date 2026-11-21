"""core/screen_capture.py — escolha da janela-alvo e do monitor (lógica pura)."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import screen_capture as sc


def win(hwnd, **kw):
    base = {"hwnd": hwnd, "title": f"Janela {hwnd}", "cls": "Chrome_WidgetWin_1", "visible": True,
            "iconic": False, "cloaked": False, "tool": False, "width": 800, "height": 600}
    base.update(kw)
    return base


class TestPickTarget(unittest.TestCase):
    def test_skips_own_terminal_and_takes_next_in_z_order(self):
        z = [win(1, title="JARVIS"), win(2, title="main.py - VS Code")]
        self.assertEqual(sc.pick_target(z, self_hwnds={1})["hwnd"], 2)

    def test_foreground_other_app_is_target(self):
        z = [win(5, title="Prova.pdf"), win(1, title="JARVIS")]
        self.assertEqual(sc.pick_target(z, self_hwnds={1})["hwnd"], 5)

    def test_skips_hidden_minimized_cloaked_untitled_tool_shell_tiny(self):
        z = [win(2, visible=False), win(3, iconic=True), win(4, cloaked=True), win(5, title="  "),
             win(6, tool=True), win(7, cls="Shell_TrayWnd"), win(8, cls="Progman"),
             win(9, width=20, height=600), win(10, title="Documento")]
        self.assertEqual(sc.pick_target(z)["hwnd"], 10)

    def test_no_candidate_returns_none(self):
        self.assertIsNone(sc.pick_target([win(1)], self_hwnds={1}))
        self.assertIsNone(sc.pick_target([]))


MONITORS = [{"x": -1920, "y": 0, "width": 1920, "height": 1080},
            {"x": 0, "y": 0, "width": 1920, "height": 1080},
            {"x": 1920, "y": 0, "width": 1920, "height": 1080}]


class TestMonitors(unittest.TestCase):
    def test_monitor_for_window_center(self):
        self.assertIs(sc.monitor_for((2000, 100, 3000, 900), MONITORS), MONITORS[2])
        self.assertIs(sc.monitor_for((-1800, 0, -100, 500), MONITORS), MONITORS[0])
        self.assertIs(sc.monitor_for((99999, 0, 99999, 10), MONITORS), MONITORS[0])  # fora de tudo
        self.assertIsNone(sc.monitor_for((0, 0, 10, 10), []))

    def test_monitor_bbox(self):
        self.assertEqual(sc.monitor_bbox(MONITORS[0]), (-1920, 0, 0, 1080))


class TestCapture(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(sc, "_ensure_dpi_aware")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_window_scope_grabs_window_rect(self):
        grab = MagicMock(return_value="IMG")
        with patch.object(sc, "target_window", return_value=win(7, title="VS Code")), \
                patch.object(sc, "window_rect", return_value=(10, 20, 810, 620)):
            image, label = sc.capture(grab=grab)
        self.assertEqual((image, label), ("IMG", "VS Code"))
        grab.assert_called_once_with(bbox=(10, 20, 810, 620), all_screens=True)

    def test_monitor_scope_by_index_or_window(self):
        grab = MagicMock(return_value="IMG")
        with patch.object(sc, "target_window", return_value=win(7)), \
                patch.object(sc, "window_rect", return_value=(2000, 0, 2500, 500)), \
                patch.object(sc, "get_monitors", return_value=MONITORS):
            self.assertEqual(sc.capture("monitor", 1, grab=grab), ("IMG", "monitor 1"))
            grab.assert_called_with(bbox=(-1920, 0, 0, 1080), all_screens=True)
            self.assertEqual(sc.capture("monitor", None, grab=grab), ("IMG", "monitor 3"))
            self.assertEqual(sc.capture("monitor", 9, grab=grab), ("IMG", "monitor 3"))  # índice inválido

    def test_no_window_or_error_returns_none(self):
        with patch.object(sc, "target_window", return_value=None):
            self.assertEqual(sc.capture(grab=MagicMock()), (None, ""))
        with patch.object(sc, "target_window", side_effect=OSError("win32")):
            self.assertEqual(sc.capture(grab=MagicMock()), (None, ""))


if __name__ == "__main__":
    unittest.main()
