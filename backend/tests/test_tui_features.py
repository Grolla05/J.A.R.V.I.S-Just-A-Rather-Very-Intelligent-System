"""TUI — saúde na linha de status, foco/DND, palette (Ctrl+K) e invocação global."""
from unittest.mock import patch

from tests._stubs import install

install()

from tests import test_tui_app as base  # módulo, não a classe: o pytest coletaria de novo


class _Base(base.TestJarvisApp):
    """Reaproveita setUp/tearDown (banco temporário) e o _app() sem rodar os testes herdados."""


# Os testes herdados de TestJarvisApp já rodam no módulo dele.
for _name in [n for n in dir(base.TestJarvisApp) if n.startswith("test_")]:
    setattr(_Base, _name, None)


class TestHealthStatus(_Base):
    async def test_health_glyphs_not_in_status_line(self):
        app = self._app()
        async with app.run_test() as pilot:
            app._set_health({"OLL": ("ok", ""), "OBS": ("warn", ""), "MIC": ("fail", ""), "DB": ("ok", "")})
            await pilot.pause()
            text = app.status_text()
            for label in ("OLL", "OBS", "MIC", "DB"):
                self.assertNotIn(label, text)

    async def test_transition_to_fail_notifies(self):
        app = self._app()
        async with app.run_test() as pilot:
            app._set_health({"OLL": ("ok", "")})
            with patch.object(app, "notify") as notify:
                app._set_health({"OLL": ("fail", "servidor offline")})
                await pilot.pause()
            notify.assert_called_once()
            self.assertIn("Ollama", notify.call_args[0][0])


class TestFocusCommands(_Base):
    def test_parse_focus_and_dnd_args(self):
        from frontend.commands import parse_dnd_arg, parse_focus_arg
        self.assertEqual(parse_focus_arg(""), ("start", None))
        self.assertEqual(parse_focus_arg("50"), ("start", 50))
        self.assertEqual(parse_focus_arg("stop"), ("stop", None))
        self.assertEqual(parse_focus_arg("pular"), ("skip", None))
        self.assertIsNone(parse_focus_arg("banana"))
        self.assertEqual(parse_dnd_arg(""), ("dnd_toggle", None))
        self.assertEqual(parse_dnd_arg("30"), ("dnd_on", 30))
        self.assertEqual(parse_dnd_arg("off"), ("dnd_off", None))
        self.assertIsNone(parse_dnd_arg("0"))

    async def test_focus_command_calls_manager(self):
        from services.focus import focus
        app = self._app()
        async with app.run_test() as pilot:
            with patch.object(focus, "apply", return_value="Pomodoro iniciado.") as apply:
                await self._send(pilot, "/focus 40")
            apply.assert_called_once_with("start", 40)
            replies = [m for m in app.query(base.tui_app.MessageView) if m.role == "assistant"]
            self.assertIn("Pomodoro iniciado.", replies[-1].text)

    async def test_bad_dnd_arg_warns(self):
        app = self._app()
        async with app.run_test() as pilot:
            with patch.object(app, "notify") as notify:
                await self._send(pilot, "/dnd talvez")
            self.assertIn("Uso: /dnd", notify.call_args[0][0])

    async def test_focus_badge_in_status_line(self):
        from services.focus import focus
        app = self._app()
        async with app.run_test():
            with patch.object(focus, "badge", return_value="◷ FOCO 12m 1/4"):
                self.assertIn("◷ FOCO 12m 1/4", app.status_text())


class TestPaletteLogic(_Base):
    SKILLS = [{"id": "automation", "enabled": True,
               "skills": [{"id": "APP_CONTROL", "enabled": True}, {"id": "SPOTIFY_CONTROL", "enabled": False}]}]

    def test_entries_by_mode(self):
        from frontend.commands import palette_entries
        chat = palette_entries(self.SKILLS, "chat")
        kinds = {e.label: e.kind for e in chat}
        self.assertEqual(kinds["/status"], "command")
        self.assertEqual(kinds["/rename <título>"], "prefill")
        self.assertNotIn("/menu", kinds)
        skill = next(e for e in chat if e.label == "SPOTIFY_CONTROL")
        self.assertEqual(skill.value, ("SPOTIFY_CONTROL", True))  # OFF -> ligar
        self.assertTrue(any(e.kind == "mode" and e.value == "copilot" for e in chat))
        copilot = palette_entries(self.SKILLS, "copilot")
        self.assertFalse(any(e.kind == "prefill" for e in copilot))
        self.assertTrue(any(e.kind == "mode" and e.value == "chat" for e in copilot))

    def test_fuzzy_ranking(self):
        from frontend.commands import filter_entries, fuzzy_score, palette_entries
        self.assertIsNone(fuzzy_score("xyz", "/status"))
        self.assertGreater(fuzzy_score("sta", "/status"), fuzzy_score("sta", "SPOTIFY_CONTROL") or -1e9)
        entries = palette_entries(self.SKILLS, "chat")
        self.assertEqual(filter_entries(entries, "sta")[0].label, "/status")
        self.assertEqual(filter_entries(entries, "spo")[0].label, "SPOTIFY_CONTROL")
        self.assertEqual(filter_entries(entries, ""), entries)
        self.assertEqual(filter_entries(entries, "qwzx"), [])


class TestPaletteScreen(_Base):
    async def _open(self, pilot):
        await pilot.press("ctrl+k")
        await pilot.pause()
        self.assertIsInstance(pilot.app.screen, base.tui_app.CommandPalette)

    async def test_ctrl_k_opens_even_with_prompt_focused(self):
        app = self._app()
        async with app.run_test() as pilot:
            app.query_one("#prompt").value = "texto"
            await self._open(pilot)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, base.tui_app.CommandPalette)
            self.assertEqual(app.query_one("#prompt").value, "texto")  # Ctrl+K não apagou

    async def test_filter_and_enter_runs_command(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._open(pilot)
            await pilot.press("s", "t", "a")
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, base.tui_app.StatusScreen)

    async def test_prefill_command(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._open(pilot)
            await pilot.press(*"rename")
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt").value, "/rename ")

    async def test_skill_entry_toggles(self):
        app = self._app()
        skills = [{"id": "automation", "enabled": True, "skills": [{"id": "APP_CONTROL", "enabled": True}]}]
        async with app.run_test() as pilot:
            with patch("services.skill_settings.list_skills", return_value=skills), \
                 patch("services.skill_settings.set_enabled", return_value="Skill") as set_enabled:
                await self._open(pilot)
                await pilot.press(*"app_con")
                await pilot.press("enter")
                await pilot.pause()
            set_enabled.assert_called_once_with("APP_CONTROL", False)

    async def test_menu_command_opens_palette(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._send(pilot, "/menu")
            self.assertIsInstance(app.screen, base.tui_app.CommandPalette)


class TestSummon(_Base):
    async def test_summon_closes_screens_and_goes_copilot(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._send(pilot, "/status")
            self.assertIsInstance(app.screen, base.tui_app.StatusScreen)
            app._on_summon("SUMMON")
            await pilot.pause()
            self.assertEqual(app.mode, "copilot")
            self.assertEqual(len(app.screen_stack), 1)
            app._on_summon("TO_CHAT")
            await pilot.pause()
            self.assertEqual(app.mode, "chat")

    async def test_start_mode_copilot(self):
        app = base.tui_app.JarvisApp(stream_fn=base._fake_stream, start_services=False,
                                     voice=base.FakeVoice(), start_mode="copilot")
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(app.mode, "copilot")
