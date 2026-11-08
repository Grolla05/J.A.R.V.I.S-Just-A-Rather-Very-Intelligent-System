"""TUI — comandos de ferramentas (/web, /gh, /briefing, /clip) via Pilot."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._stubs import install

install()

import core.database as database  # noqa: E402
import core.state as state  # noqa: E402
import frontend.app as tui_app  # noqa: E402
import services.sessions as sessions  # noqa: E402
from core.config import settings  # noqa: E402
from tests.test_tui_app import FakeVoice, _fake_stream  # noqa: E402


class ToolsAppCase(unittest.IsolatedAsyncioTestCase):
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
        state.voice_enabled = False
        for p in reversed(self._patches):
            p.stop()
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass

    def _app(self):
        return tui_app.JarvisApp(stream_fn=_fake_stream, start_services=False, voice=FakeVoice())

    async def _send(self, pilot, text):
        pilot.app.query_one("#prompt").value = text
        await pilot.press("enter")
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()

    def _last_reply(self, app):
        return [m for m in app.query(tui_app.MessageView) if m.role == "assistant"][-1]


class TestWebCommand(ToolsAppCase):
    async def test_web_fills_bubble_from_worker(self):
        from core import web
        app = self._app()
        with patch.object(web, "research", return_value="**Resumo** [1]") as research:
            async with app.run_test() as pilot:
                await self._send(pilot, "/web python 3.14")
                self.assertEqual(self._last_reply(app).text, "**Resumo** [1]")
        research.assert_called_once_with("python 3.14")

    async def test_web_without_query_does_nothing(self):
        from core import web
        app = self._app()
        with patch.object(web, "research") as research:
            async with app.run_test() as pilot:
                await self._send(pilot, "/web")
        research.assert_not_called()

    async def test_tool_error_is_shown(self):
        from core import web
        app = self._app()
        with patch.object(web, "research", side_effect=RuntimeError("boom")):
            async with app.run_test() as pilot:
                await self._send(pilot, "/web algo")
                self.assertIn("boom", self._last_reply(app).text)
