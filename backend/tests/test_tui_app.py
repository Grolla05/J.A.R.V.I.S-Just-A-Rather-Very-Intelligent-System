"""TUI — JarvisApp via Textual Pilot (sem Ollama, sem hardware)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._stubs import install

install()

import core.database as database
import frontend.app as tui_app
import services.sessions as sessions
from core.config import settings


def _fake_stream(text, session_id, images, mode, on_route=None):
    # Simula o brain: no Copilot, "abre ..." vira a skill APP_CONTROL.
    if mode == "copilot" and text.startswith("abre") and on_route:
        on_route("APP_CONTROL")
    yield f"**{mode}**: "
    yield f"eco de {text}"


class TestJarvisApp(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path = path
        self._orig = settings.DB_PATH
        settings.DB_PATH = Path(path)
        self.db = database.DatabaseManager()
        self._patches = [patch.object(sessions, "db", self.db), patch.object(tui_app, "db", self.db)]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass

    def _app(self):
        return tui_app.JarvisApp(stream_fn=_fake_stream, start_services=False)

    async def _send(self, pilot, text):
        prompt = pilot.app.query_one("#prompt")
        prompt.value = text
        await pilot.press("enter")
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()

    async def test_shift_tab_toggles_mode(self):
        app = self._app()
        async with app.run_test() as pilot:
            self.assertEqual(app.mode, "chat")
            await pilot.press("shift+tab")
            self.assertEqual(app.mode, "copilot")
            self.assertTrue(app.screen.has_class("-copilot"))
            await pilot.press("shift+tab")
            self.assertEqual(app.mode, "chat")
            self.assertFalse(app.screen.has_class("-copilot"))

    async def test_message_streams_and_is_logged(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._send(pilot, "olá")
            replies = [m for m in app.query(tui_app.MessageView) if m.role == "assistant"]
            self.assertEqual(replies[-1].text, "**chat**: eco de olá")
            self.assertFalse(app.busy)
            history = sessions.get_chat_history(app.session_id)
            self.assertEqual([m["content"] for m in history], ["olá", "**chat**: eco de olá"])

    async def test_copilot_mode_reaches_stream(self):
        app = self._app()
        async with app.run_test() as pilot:
            await pilot.press("shift+tab")
            await self._send(pilot, "abre o spotify")
            replies = [m for m in app.query(tui_app.MessageView) if m.role == "assistant"]
            self.assertTrue(replies[-1].text.startswith("**copilot**"))
            # Badge da skill acionada no cabeçalho da resposta
            self.assertIn("[APP_CONTROL] ✓", replies[-1].meta)

    async def test_chat_reply_has_no_skill_badge(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._send(pilot, "abre o spotify")
            replies = [m for m in app.query(tui_app.MessageView) if m.role == "assistant"]
            self.assertNotIn("APP_CONTROL", replies[-1].meta)

    async def test_topbar_shows_mode_badge_and_session_position(self):
        app = self._app()
        async with app.run_test() as pilot:
            badge = app.query_one("#mode-badge")
            info = app.query_one("#topbar-info")
            self.assertEqual(str(badge.render()), "CHAT")
            self.assertEqual(str(info.render()), "nova sessão")
            await self._send(pilot, "olá")
            self.assertEqual(str(info.render()), "sessão 1 de 1")
            await pilot.press("shift+tab")
            self.assertEqual(str(badge.render()), "COPILOT")
            self.assertTrue(str(info.render()).startswith("skills ativas"))
            app.critical = True
            await pilot.pause()
            self.assertIn("PROTOCOLO CRÍTICO", str(info.render()))
            self.assertTrue(app.screen.has_class("-critical"))

    async def test_session_picker_filters_and_opens(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._send(pilot, "receita de pão")
            first = app.session_id
            await pilot.press("ctrl+n")
            await self._send(pilot, "plano de estudos")
            await pilot.press("ctrl+o")
            await pilot.pause()
            picker = app.screen
            self.assertIsInstance(picker, tui_app.SessionPicker)
            await pilot.press(*"pão")
            await pilot.pause()
            option_list = picker.query_one("#picker-list")
            self.assertEqual(option_list.option_count, 1)
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(app.session_id, first)

    async def test_confirm_screen_expires_as_no(self):
        app = self._app()
        results = []
        async with app.run_test() as pilot:
            screen = tui_app.ConfirmScreen("Encerrar chrome.exe?", deadline=0)
            app.push_screen(screen, results.append)
            await pilot.pause(1.3)
            self.assertEqual(results, [False])

    async def test_confirm_screen_accepts_s(self):
        app = self._app()
        results = []
        async with app.run_test() as pilot:
            app.push_screen(tui_app.ConfirmScreen("Encerrar?"), results.append)
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            self.assertEqual(results, [True])

    async def test_new_session_command_and_binding(self):
        app = self._app()
        async with app.run_test() as pilot:
            first = app.session_id
            await self._send(pilot, "/new")
            second = app.session_id
            self.assertNotEqual(first, second)
            await pilot.press("ctrl+n")
            self.assertNotEqual(app.session_id, second)

    async def test_regen_replaces_last_answer(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._send(pilot, "pergunta")
            await pilot.press("ctrl+r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            history = sessions.get_chat_history(app.session_id)
            self.assertEqual([m["content"] for m in history], ["pergunta", "**chat**: eco de pergunta"])

    async def test_unknown_command_does_not_send(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._send(pilot, "/naoexiste")
            self.assertEqual(sessions.get_chat_history(app.session_id), [])


if __name__ == "__main__":
    unittest.main()
