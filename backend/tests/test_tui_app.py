"""TUI — JarvisApp via Textual Pilot (sem Ollama, sem hardware)."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._stubs import install

install()

from textual.widgets import Footer

import core.database as database
import core.state as state
import frontend.app as tui_app
import services.sessions as sessions
from core.config import settings


def _fake_stream(text, session_id, images, mode, on_route=None):
    # Simula o brain: no Copilot, "abre ..." vira a skill APP_CONTROL.
    if mode == "copilot" and text.startswith("abre") and on_route:
        on_route("APP_CONTROL")
    yield f"**{mode}**: "
    yield f"eco de {text}"


class FakeVoice:
    """Microfone/TTS de mentira: entrega as falas da fila, registra o que falou."""

    def __init__(self, *phrases):
        self.queue = list(phrases)
        self.spoken = []
        self.orb_while_speaking = []
        self.app = None
        self.lock = threading.Lock()

    def listen(self):
        with self.lock:
            if self.queue:
                return self.queue.pop(0)
        time.sleep(0.05)
        return None

    def speak(self, text):
        if self.app is not None:
            self.orb_while_speaking.append(self.app.query_one("#copilot-hero").state)
        self.spoken.append(text)

    def pause(self):
        pass

    def resume(self):
        pass


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
        state.voice_enabled = False  # para o loop de voz da thread daemon
        state.pending_critical_action = None
        for p in reversed(self._patches):
            p.stop()
        settings.DB_PATH = self._orig
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._path + suffix)
            except OSError:
                pass

    def _app(self, voice=None):
        voice = voice or FakeVoice()
        app = tui_app.JarvisApp(stream_fn=_fake_stream, start_services=False, voice=voice)
        voice.app = app
        return app

    async def _wait_for(self, pilot, condition, timeout=10.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return
            await pilot.pause(0.05)
        self.fail("condição não atingida a tempo")

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

    async def test_copilot_is_voice_only(self):
        app = self._app()
        async with app.run_test() as pilot:
            prompt, voicebar, hero = (app.query_one(s) for s in ("#prompt", "#voicebar", "#copilot-hero"))
            self.assertTrue(prompt.display)
            self.assertFalse(voicebar.display or hero.display)
            await pilot.press("shift+tab")
            self.assertFalse(prompt.display)
            self.assertTrue(voicebar.display and hero.display)
            self.assertTrue(state.voice_enabled)
            await pilot.press("shift+tab")
            self.assertTrue(prompt.display)
            self.assertFalse(voicebar.display or hero.display)
            self.assertFalse(state.voice_enabled)

    async def test_ctrl_t_enters_copilot_and_hides_from_footer(self):
        app = self._app()
        async with app.run_test() as pilot:
            self.assertTrue(app.check_action("toggle_voice", ()))
            await pilot.press("ctrl+t")
            self.assertEqual(app.mode, "copilot")
            self.assertFalse(app.check_action("toggle_voice", ()))

    async def test_copilot_voice_turn_reaches_stream_and_speaks(self):
        voice = FakeVoice("abre o spotify")
        app = self._app(voice)
        async with app.run_test() as pilot:
            await pilot.press("shift+tab")
            await self._wait_for(pilot, lambda: voice.spoken)
            await self._wait_for(pilot, lambda: app.query_one("#copilot-hero").state == "ouvindo")
            users = [m for m in app.query(tui_app.MessageView) if m.role == "user"]
            replies = [m for m in app.query(tui_app.MessageView) if m.role == "assistant"]
            self.assertEqual(users[-1].text, "abre o spotify")
            self.assertTrue(users[-1].meta.startswith("voz · "))
            self.assertTrue(replies[-1].text.startswith("**copilot**"))
            # Badge da skill acionada no cabeçalho da resposta
            self.assertIn("[APP_CONTROL] ✓", replies[-1].meta)
            self.assertEqual(voice.spoken, ["**copilot**: eco de abre o spotify"])
            self.assertEqual(voice.orb_while_speaking, ["respondendo"])
            # Voz vai para a sessão atual (aparece no Ctrl+O)
            history = sessions.get_chat_history(app.session_id)
            self.assertEqual([m["content"] for m in history],
                             ["abre o spotify", "**copilot**: eco de abre o spotify"])

    async def test_orb_thinks_until_first_output(self):
        gate = threading.Event()

        def slow_stream(text, session_id, images, mode, on_route=None):
            gate.wait(5)
            yield "ok"

        voice = FakeVoice("que horas são")
        app = tui_app.JarvisApp(stream_fn=slow_stream, start_services=False, voice=voice)
        voice.app = app
        async with app.run_test() as pilot:
            hero = app.query_one("#copilot-hero")
            await pilot.press("shift+tab")
            await self._wait_for(pilot, lambda: hero.state == "pensando")
            self.assertIn("pensando", str(app.query_one("#hero-state").render()))
            gate.set()
            await self._wait_for(pilot, lambda: voice.spoken)
            self.assertEqual(voice.orb_while_speaking, ["respondendo"])

    async def test_status_and_keys_share_one_line(self):
        app = self._app()
        async with app.run_test() as pilot:
            await pilot.pause()
            footers = list(app.screen.query(Footer))
            self.assertEqual(len(footers), 1)
            self.assertEqual(footers[0].parent.id, "statusbar")
            self.assertEqual(app.query_one("#statusbar").region.height, 1)
            self.assertEqual(footers[0].region.y, app.query_one("#status-left").region.y)
            self.assertIn("voz off", str(app.query_one("#status-left").render()))
            await self._wait_for(pilot, lambda: list(footers[0].query("FooterKey")))
            keys = [k.key for k in footers[0].query("FooterKey")]
            self.assertEqual(keys[-1], "ctrl+q")  # Sair fica no fim

    async def test_critical_marks_main_screen_and_voicebar(self):
        app = self._app()
        async with app.run_test() as pilot:
            await pilot.press("shift+tab")
            app.critical = True
            state.pending_critical_action = {"timeout": None}
            app._show_announcement("Encerrar chrome.exe?")
            await pilot.pause(0.3)
            self.assertIsInstance(app.screen, tui_app.ConfirmScreen)
            self.assertTrue(app.main_screen.has_class("-critical"))
            self.assertIn("sim", str(app.query_one("#voice-text").render()))
            # O modal tem a própria linha de status, com os atalhos s/n
            def keys():
                return {k.key for k in app.screen.query("FooterKey")}
            await self._wait_for(pilot, lambda: {"s", "n"} <= keys())

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
            self.assertTrue(str(info.render()).startswith("somente voz"))
            class Mon:
                critical_reasons = ["disco D: com 8.2 GB livres"]
            with patch.object(state, "sys_monitor", Mon()):
                app.critical = True
                await pilot.pause()
            self.assertIn("PROTOCOLO CRÍTICO · disco D: com 8.2 GB livres", str(info.render()))
            self.assertTrue(app.main_screen.has_class("-critical"))

    async def test_session_picker_filters_and_opens(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._send(pilot, "receita de pão")
            first = app.session_id
            await pilot.press("ctrl+n")
            await self._send(pilot, "plano de estudos")
            await pilot.press("ctrl+o")
            await pilot.pause()
            await pilot.pause()
            picker = app.screen
            self.assertIsInstance(picker, tui_app.SessionPicker)
            self.assertEqual(str(picker.query_one("#mode-badge").render()), "CARREGAR")
            self.assertIn("2 sessões", str(picker.query_one("#session-title").render()))
            await pilot.press("slash", *"pão")
            await pilot.pause()
            self.assertEqual(len(picker._cards()), 1)
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

    async def test_confirm_screen_has_pixel_icon_and_countdown_bar(self):
        app = self._app()
        async with app.run_test() as pilot:
            app.push_screen(tui_app.ConfirmScreen("Encerrar?"))
            await pilot.pause()
            icon = app.screen.query_one("#confirm-icon")
            self.assertEqual((icon.region.width, icon.region.height), (16, 6))
            bar = str(app.screen.query_one("#confirm-bar").render())
            self.assertEqual(len(bar), 30)
            self.assertTrue(bar.startswith("█"))

    async def test_telemetry_shows_block_bars(self):
        app = self._app()
        async with app.run_test() as pilot:
            class Mon:
                def get_cpu_detailed(self): return {"usage": 41}
                def get_ram_usage(self): return {"percent": 100}
                def get_gpu_info(self): return {"load": 0}
            with patch.object(state, "sys_monitor", Mon()):
                app._poll_telemetry()
                await app.workers.wait_for_complete()
                await pilot.pause()
            text = str(app.query_one("#status-left").render())
            self.assertIn("CPU ▰▰▱▱▱ 41%", text)
            self.assertIn("RAM ▰▰▰▰▰ 100%", text)
            self.assertIn("GPU ▱▱▱▱▱ 0%", text)

    async def test_session_picker_focuses_current_slot_card(self):
        app = self._app()
        async with app.run_test(size=(140, 45)) as pilot:
            await self._send(pilot, "receita de pão")
            older = app.session_id
            await pilot.press("ctrl+n")
            await self._send(pilot, "plano de estudos")
            await pilot.press("ctrl+o")
            await pilot.pause(0.2)
            screen = app.screen
            cards = screen._cards()
            self.assertEqual([c.slot for c in cards], [1, 2])
            self.assertEqual(str(cards[0].query_one(".slot-badge").render()), "01")
            self.assertEqual(screen.focused.session_id, app.session_id)
            await pilot.press("right")
            self.assertEqual(screen.focused.session_id, older)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIs(app.screen, app.main_screen)

    async def test_status_screen_shows_history_and_escape_returns(self):
        app = self._app()
        async with app.run_test(size=(140, 45)) as pilot:
            for v in (10, 50, 90):
                app._set_telemetry("CPU", {"CPU": v, "RAM": 40, "GPU": 5, "REDE": 2048})
            await self._send(pilot, "/status")
            await pilot.pause(0.3)
            self.assertIsInstance(app.screen, tui_app.StatusScreen)
            cpu = app.screen.query_one("#meter-cpu")
            self.assertEqual(str(cpu.query_one(".meter-value").render()), "90%")
            self.assertTrue(cpu.has_class("-alta"))
            self.assertIn("█", str(cpu.query_one(".meter-chart").render()))
            self.assertEqual(str(app.screen.query_one("#status-level").render()), "ALTA")
            # atalhos da conversa somem dentro da tela cheia
            self.assertFalse(app.check_action("toggle_mode", ()))
            await pilot.press("escape")
            await pilot.pause()
            self.assertIs(app.screen, app.main_screen)

    async def test_skills_screen_toggles_cartridge(self):
        from services import skill_settings
        state_ = {"APP_CONTROL": True}

        def fake_list():
            return [{"id": "automation", "enabled": True,
                     "skills": [{"id": "APP_CONTROL", "enabled": state_["APP_CONTROL"]}]}]

        def fake_set(target, enabled):
            state_[target] = enabled
            return "skill"

        with patch.object(skill_settings, "list_skills", fake_list), \
             patch.object(skill_settings, "set_enabled", fake_set):
            app = self._app()
            async with app.run_test(size=(140, 45)) as pilot:
                await self._send(pilot, "/skills")
                await pilot.pause(0.3)
                self.assertIsInstance(app.screen, tui_app.SkillsScreen)
                cart = app.screen.query_one(".cartridge")
                self.assertTrue(cart.has_class("-on"))
                self.assertEqual(str(cart.query_one(".cart-icon").render()), "▣")
                self.assertEqual(str(cart.query_one(".cart-name").render()), "APP_CONTROL")
                self.assertEqual(str(cart.query_one(".cart-state").render()), "ON")
                self.assertIn("▮", str(cart.query_one(".cart-contacts").render()))
                await pilot.click(".cartridge")
                await pilot.pause(0.2)
                self.assertFalse(state_["APP_CONTROL"])
                self.assertTrue(app.screen.query_one(".cartridge").has_class("-off"))
                self.assertEqual(str(app.screen.query_one(".cart-state").render()), "OFF")
                self.assertIn("0 de 1", str(app.screen.query_one("#session-title").render()))

    async def test_log_screen_filters_buffer_and_shows_timeline(self):
        from core.logger import log
        app = self._app(FakeVoice("abre o spotify"))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("shift+tab")
            await self._wait_for(pilot, lambda: app.last_skill_turn and app.last_skill_turn["status"] == "ok")
            await pilot.press("shift+tab")
            log.warning("aviso de teste do /log")
            await self._send(pilot, "/log")
            await pilot.pause(0.3)
            self.assertIsInstance(app.screen, tui_app.LogScreen)
            await pilot.click("#filter-warn")
            await pilot.pause(0.2)
            lines = app.screen.query_one("#log-lines")
            self.assertTrue(lines.records)
            self.assertTrue(all(r["level"] == "WARN" for r in lines.records))
            self.assertIn("aviso de teste do /log", lines.records[-1]["message"])
            steps = [str(s.render()) for s in app.screen.query("#log-timeline .step")]
            self.assertIn("INTENT · APP_CONTROL", steps)
            self.assertEqual(steps[0], "VOZ")

    async def test_session_picker_shows_size_and_pins_and_deletes(self):
        app = self._app()
        async with app.run_test(size=(140, 45)) as pilot:
            await self._send(pilot, "receita de pão")
            await pilot.press("ctrl+n")
            await self._send(pilot, "plano de estudos")
            await pilot.press("ctrl+n")
            await pilot.press("ctrl+o")
            await pilot.pause()
            await pilot.pause(0.2)
            picker = app.screen
            first = picker._cards()[0]
            self.assertIs(picker.focused, first)
            meta = str(first.query_one(".slot-meta").render())
            self.assertIn("2 msgs · chat", meta)
            self.assertEqual(str(first.query_one(".slot-quote").render()), "“chat: eco de plano de estudos”")
            self.assertIn("▰", str(first.query_one(".slot-bar").render()))
            await pilot.press("p")
            await pilot.pause(0.2)
            self.assertEqual(str(picker._cards()[0].query_one(".slot-star").render()), "★")
            await pilot.press("delete", "delete")
            await pilot.pause(0.2)
            self.assertEqual(len(picker._cards()), 1)

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
