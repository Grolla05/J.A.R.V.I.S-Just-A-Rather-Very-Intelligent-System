"""Fases 3 e 4 das telas 16-bit: nível do mic (RMS), preferências, boot,
/vault, /config, voz na VoiceBar, shutdown CRT e easter egg."""
import math
import os
import struct
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
import services.user_prefs as user_prefs  # noqa: E402
from core import boot  # noqa: E402
from core.config import settings  # noqa: E402


def _pcm(amplitude, n=1600):
    return b"".join(struct.pack("<h", int(amplitude * math.sin(i / 3))) for i in range(n))


class TestLevelTap(unittest.TestCase):
    def setUp(self):
        try:
            import services.listen as listen
        except ImportError as e:  # speech_recognition ausente no ambiente
            self.skipTest(f"speech_recognition indisponível: {e}")
        self.listen = listen

    def test_rms_level_silence_and_full(self):
        self.assertEqual(self.listen.rms_level(b""), 0.0)
        self.assertEqual(self.listen.rms_level(_pcm(0)), 0.0)
        self.assertAlmostEqual(self.listen.rms_level(_pcm(32000)), 1.0)
        mid = self.listen.rms_level(_pcm(3000))   # fala normal: meio da barra (dBFS)
        self.assertTrue(0.5 < mid < 0.85, mid)

    def test_level_respects_recognizer_threshold(self):
        """Abaixo do limiar de energia do recognizer = silêncio (barra zerada)."""
        self.assertEqual(self.listen.rms_level(_pcm(300), floor_rms=400), 0.0)
        self.assertGreater(self.listen.rms_level(_pcm(3000), floor_rms=400), 0.0)
        # quanto mais alto, maior o nível (monotônico)
        levels = [self.listen.rms_level(_pcm(a), floor_rms=300) for a in (600, 1500, 4000, 12000)]
        self.assertEqual(levels, sorted(levels))

    def test_tap_reports_peak_of_window(self):
        """Blocos entre dois avisos não se perdem: o aviso leva o pico da janela."""
        chunks = iter([_pcm(0, 10), _pcm(20000, 10), _pcm(0, 10)])

        class Stream:
            def read(self, size):
                return next(chunks)

        levels, now = [], [0.0]
        tap = self.listen._LevelTap(Stream(), levels.append, clock=lambda: now[0])
        tap.read(10)              # 1º aviso: silêncio
        now[0] = 0.05
        tap.read(10)              # fala alta, mas ainda dentro da janela
        now[0] = 0.2
        tap.read(10)              # bloco atual é silêncio; aviso traz o pico
        self.assertEqual(levels[0], 0.0)
        self.assertGreater(levels[1], 0.8)

    def test_tap_passes_audio_and_throttles(self):
        class Stream:
            def read(self, size):
                return _pcm(32000, size)

            def close(self):
                return "fechado"

        levels, now = [], [0.0]
        tap = self.listen._LevelTap(Stream(), levels.append, clock=lambda: now[0])
        data = tap.read(10)
        self.assertEqual(data, _pcm(32000, 10))  # áudio chega intacto ao recognizer
        now[0] = 0.05
        tap.read(10)                              # < 1/8 s: não avisa de novo
        now[0] = 0.3
        tap.read(10)
        self.assertEqual(len(levels), 2)
        self.assertEqual(tap.close(), "fechado")  # resto do stream passa direto


class _DbCase(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path, self._orig = path, settings.DB_PATH
        settings.DB_PATH = Path(path)
        self.db = database.DatabaseManager()
        self._patches = [patch.object(user_prefs, "db", self.db), patch.object(sessions, "db", self.db),
                         patch.object(tui_app, "db", self.db)]
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


class TestUserPrefs(_DbCase):
    def test_defaults_and_step_persist(self):
        self.assertEqual(user_prefs.get("tts_rate"), 10)
        self.assertEqual(user_prefs.step("tts_rate", 1), 20)
        self.assertEqual(user_prefs.get("tts_rate"), 20)
        self.assertEqual(user_prefs.display("tts_rate"), "+20%")

    def test_step_clamps_at_edges(self):
        for _ in range(10):
            user_prefs.step("tts_volume", 1)
        self.assertEqual(user_prefs.get("tts_volume"), 100)
        self.assertEqual(user_prefs.level("tts_volume"), 1.0)

    def test_garbage_in_db_falls_back_to_default(self):
        self.db.save_config("pref_tts_voice", "voz-que-nao-existe")
        self.assertEqual(user_prefs.get("tts_voice"), user_prefs.VOICES[0])
        with self.assertRaises(ValueError):
            user_prefs.set("tts_rate", 7)


class TestBoot(unittest.TestCase):
    def test_run_boot_reports_each_step_and_done(self):
        events = []
        steps = (("a", lambda: ("ok", "tudo certo")), ("b", lambda: 1 / 0))
        boot.run_boot(lambda *e: events.append(e), steps=steps)
        self.assertEqual(events[0], ("a", "wait", ""))
        self.assertEqual(events[1], ("a", "ok", "tudo certo"))
        self.assertEqual(events[3][:2], ("b", "fail"))
        self.assertEqual(events[-1], (boot.DONE, "ok", ""))


class FakeVaultClient:
    def __init__(self):
        self.searched = []

    def list_dir(self, path=""):
        return {"": ["Projetos/", "Sobre mim.md"], "Projetos/": ["rotina.md"]}.get(path, [])

    def search_results(self, query, limit=8):
        self.searched.append(query)
        return [{"filename": "Projetos/rotina.md", "score": 0.92}]

    def get_file(self, path):
        return "# Rotina\n\n- café às 9h"


def _fake_stream(text, session_id, images, mode, on_route=None):
    _fake_stream.last = text
    yield f"eco de {text}"


class TestScreens(_DbCase, unittest.IsolatedAsyncioTestCase):
    def _app(self, **kwargs):
        return tui_app.JarvisApp(stream_fn=_fake_stream, start_services=False, **kwargs)

    async def _wait(self, pilot, cond, timeout=10.0):
        import time
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return
            await pilot.pause(0.05)
        self.fail("condição não atingida a tempo")

    async def _cmd(self, app, pilot, text):
        app.main_screen.query_one("#prompt").value = text
        await pilot.press("enter")
        await pilot.pause(0.3)

    async def test_voicebar_shows_real_level_and_resets(self):
        app = self._app()
        async with app.run_test(size=(140, 45)) as pilot:
            bar = app.main_screen.query_one("#voicebar")
            bar.set_level(1.0)
            await pilot.pause()
            self.assertTrue(str(bar.query_one("#voice-wave").render()).endswith("█"))
            self.assertEqual(str(bar.query_one("#voice-vu").render()), "█" * 15)
            bar.set_level(None)
            await pilot.pause()
            self.assertEqual(str(bar.query_one("#voice-vu").render()), "░" * 15)
            self.assertNotIn("█", str(bar.query_one("#voice-wave").render()))

    async def test_voicebar_rises_fast_and_falls_smoothly(self):
        app = self._app()
        async with app.run_test(size=(140, 45)) as pilot:
            bar = app.main_screen.query_one("#voicebar")
            self.assertNotIn("█", str(bar.query_one("#voice-wave").render()))  # sem onda falsa
            bar.set_level(1.0)
            bar.set_level(0.0)
            await pilot.pause()
            self.assertAlmostEqual(bar.shown, bar.RELEASE)  # cai suave, não zera de uma vez
            bar.set_level(0.9)
            self.assertAlmostEqual(bar.shown, 0.9)          # sobe na hora

    async def test_config_adjusts_and_persists(self):
        app = self._app()
        async with app.run_test(size=(140, 45)) as pilot:
            await self._cmd(app, pilot, "/config")
            self.assertIsInstance(app.screen, tui_app.SettingsScreen)
            await pilot.press("tab")       # foca as opções do grupo VOZ
            await pilot.press("down")      # Velocidade
            await pilot.press("right")
            await pilot.pause()
            self.assertEqual(user_prefs.get("tts_rate"), 20)
            self.assertIn("+20%", str(app.screen.query_one("#cfg-options").get_option_at_index(1).prompt))
            self.assertIn("Velocidade", str(app.screen.query_one("#cfg-quip").render()))

    async def test_config_has_no_dialog_box_and_quip_lives_in_panel(self):
        app = self._app()
        async with app.run_test(size=(140, 45)) as pilot:
            await self._cmd(app, pilot, "/config")
            screen = app.screen
            self.assertFalse(screen.query("#cfg-dialog"))
            self.assertFalse(screen.query("#cfg-face"))
            quip = screen.query_one("#cfg-quip")
            self.assertIs(quip.parent, screen.query_one("#cfg-panel"))
            self.assertFalse(screen.query_one("#cfg-news").display)  # só em SISTEMA

    async def test_config_system_saves_news_sources(self):
        from core import autostart, news, updater
        with patch.object(news, "_db", return_value=self.db), \
             patch.object(autostart, "is_enabled", return_value=True), \
             patch.object(autostart, "is_agent_running", return_value=True), \
             patch.object(updater, "is_enabled", return_value=False):
            app = self._app()
            async with app.run_test(size=(140, 45)) as pilot:
                await self._cmd(app, pilot, "/config")
                screen = app.screen
                screen.query_one("#cfg-menu").highlighted = 4  # SISTEMA
                await pilot.pause()
                self.assertEqual(screen.group, "SISTEMA")
                field = screen.query_one("#cfg-news-input")
                self.assertTrue(screen.query_one("#cfg-news").display)
                self.assertEqual(field.value, news.DEFAULT_SOURCES)
                for _ in range(3):              # menu → opções → campo
                    if field.has_focus:
                        break
                    await pilot.press("tab")
                self.assertTrue(field.has_focus)
                field.value = "G1 , BBC,,g1, DOI"
                field.cursor_position = 3
                await pilot.press("left")       # ←→ movem o cursor, não ajustam opções
                self.assertEqual(field.cursor_position, 2)
                await pilot.press("tab")        # → botão
                self.assertTrue(screen.query_one("#cfg-news-save").has_focus)
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(news.get_sources(self.db), "G1, BBC, DOI")
                self.assertEqual(field.value, "G1, BBC, DOI")
                self.assertIn("Fontes salvas: 3", str(screen.query_one("#cfg-quip").render()))

    async def test_config_integrations_cards_connect_and_disconnect(self):
        import threading

        import services.integrations as integrations
        release, state = threading.Event(), {"on": False}

        def connect():
            release.wait(3)
            state["on"] = True
            return "Fake conectado."

        def disconnect():
            state["on"] = False
            return "Fake desconectado."

        fake = integrations.Integration(
            "fake", "Fake Agenda", "desc", lambda: ("on", "conta x") if state["on"] else ("off", "pronto"),
            connect, disconnect)
        other = integrations.Integration("other", "Outro", "desc", lambda: ("setup", "falta .env"), lambda: "")
        with patch.object(integrations, "all_integrations", return_value=[fake, other]), \
             patch.object(integrations, "get", lambda i: {"fake": fake, "other": other}.get(i)):
            app = self._app()
            async with app.run_test(size=(150, 48)) as pilot:
                await self._cmd(app, pilot, "/config")
                screen = app.screen
                menu = screen.query_one("#cfg-menu")
                menu.highlighted = 3  # INTEGRAÇÕES
                await pilot.pause()
                self.assertEqual(screen.group, "INTEGRAÇÕES")
                self.assertTrue(screen.query_one("#cfg-cards").display)
                self.assertFalse(screen.query_one("#cfg-options").display)
                await pilot.press("enter")          # menu → 1º card
                card = screen.query_one("#int-fake")
                self.assertTrue(card.has_focus)
                self.assertTrue(card.has_class("-off"))
                self.assertTrue(screen.query_one("#int-other").has_class("-setup"))
                await pilot.press("enter")          # conecta
                await self._wait(pilot, lambda: card.has_class("-wait"))
                self.assertIn("AGUARDANDO", str(card.query_one(".int-badge").render()))
                release.set()
                await self._wait(pilot, lambda: card.has_class("-on"))
                self.assertIn("conta x", str(card.query_one(".int-detail").render()))
                self.assertIn("Fake conectado", str(screen.query_one("#cfg-quip").render()))
                await pilot.press("delete")         # pede confirmação
                await pilot.pause(0.2)
                self.assertIsInstance(app.screen, tui_app.ConfirmScreen)
                await pilot.press("s")
                await self._wait(pilot, lambda: card.has_class("-off"))
                await pilot.press("right")          # anda na grade
                self.assertTrue(screen.query_one("#int-other").has_focus)

    async def test_commute_alert_fires_once_per_day(self):
        import datetime

        import frontend.app as app_mod
        app = self._app()
        async with app.run_test(size=(140, 45)) as pilot:
            user_prefs.set("commute_alert", 450)
            monday = datetime.datetime(2026, 11, 9, 7, 35)
            with patch.object(app_mod.JarvisApp, "_make_commute_alert", staticmethod(lambda: "**Hora de sair**")), \
                 patch.object(app, "_speak_always"):
                self.assertTrue(app._check_commute_alert(monday))
                await app.workers.wait_for_complete()
                self.assertFalse(app._check_commute_alert(monday))   # 1×/dia
            await pilot.pause()
            self.assertEqual(self.db.get_config("commute_alert_last"), "2026-11-09")
            texts = [str(v._text) for v in app.main_screen.query("MessageView")]
            self.assertTrue(any("Hora de sair" in t for t in texts))

    async def test_vault_search_preview_and_use_in_chat(self):
        import frontend.screens.vault as vault
        client = FakeVaultClient()
        with patch.object(vault, "_client", lambda: client):
            app = self._app()
            async with app.run_test(size=(150, 45)) as pilot:
                await self._cmd(app, pilot, "/vault rotina")
                self.assertIsInstance(app.screen, tui_app.VaultScreen)
                await self._wait(pilot, lambda: not app.screen.query_one("#vault-use").disabled)
                self.assertEqual(client.searched, ["rotina"])
                self.assertFalse(app.screen.query_one("#radar").animated)  # radar para depois da busca
                await pilot.click("#vault-use")
                await pilot.pause(0.2)
                self.assertIs(app.screen, app.main_screen)
                self.assertIn("rotina.md", str(app.main_screen.query_one("#attachbar").render()))
                await self._cmd(app, pilot, "o que tenho de manhã?")
                await app.workers.wait_for_complete()
                self.assertIn("café às 9h", _fake_stream.last)        # nota foi ao modelo
                history = sessions.get_chat_history(app.session_id)
                self.assertEqual(history[0]["content"], "o que tenho de manhã?")  # histórico limpo

    async def test_boot_screen_shows_checks_then_closes(self):
        def fake_boot(report):
            report("core.config", "wait", "")
            report("core.config", "ok", ".env carregado")
            report("services.listen", "fail", "microfone 1 ausente")
            report(boot.DONE, "ok", "")

        app = self._app(boot_fn=fake_boot)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.2)
            self.assertIsInstance(app.screen, tui_app.BootScreen)
            tags = lambda: [str(t.render()) for t in app.screen.query(".boot-tag")]  # noqa: E731
            await self._wait(pilot, lambda: "[ FAIL ]" in tags())
            self.assertIn("[  OK  ]", tags())
            await self._wait(pilot, lambda: app.screen is app.main_screen)

    async def test_quiet_boot_skips_screen_and_notifies_problems(self):
        # Aberto pelo agente (--copilot): sem tela de boot, checagens em segundo
        # plano, sem a etapa do microfone e problemas viram notificação
        seen = {}

        def fake_boot(report, steps=boot.STEPS):
            seen["steps"] = [name for name, _ in steps]
            report("core.obsidian", "warn", "vault offline")
            report(boot.DONE, "ok", "")

        app = self._app(boot_fn=fake_boot, quiet_boot=True)
        with patch.object(app, "notify") as notify:
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause(0.2)
                self.assertIs(app.screen, app.main_screen)
                self.assertFalse(any(isinstance(s, tui_app.BootScreen) for s in app.screen_stack))
                await app.workers.wait_for_complete()
                await pilot.pause()
                self.assertNotIn(boot.MIC_STEP, seen["steps"])
                self.assertIn("core.config", seen["steps"])
                self.assertTrue(any("vault offline" in str(c) for c in notify.call_args_list))

    async def test_boot_row_has_status_without_waiting_for_mount(self):
        # Regressão do CI: a linha era pintada depois de montar e, num runner
        # lento, o selo ficava vazio para sempre
        app = self._app(boot_fn=lambda report: None)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.2)
            screen = app.screen
            screen._apply("services.listen", "fail", "microfone 1 ausente")
            tag, info = screen._rows["services.listen"]
            self.assertEqual(str(tag.render()), "[ FAIL ]")   # sem pause: ainda montando
            self.assertTrue(tag.has_class("-fail"))
            screen._apply("services.listen", "ok", "microfone 1")
            self.assertEqual(str(tag.render()), "[  OK  ]")
            self.assertFalse(tag.has_class("-fail"))
            await pilot.pause()
            self.assertEqual(str(info.render()), "microfone 1")

    async def test_quit_plays_crt_then_exits(self):
        app = self._app()
        async with app.run_test(size=(80, 24)) as pilot:
            with patch.object(app, "exit") as exit_:
                app.main_screen.query_one("#prompt").value = "/quit"
                await pilot.press("enter")
                await pilot.pause(0.02)
                self.assertIsInstance(app.screen, tui_app.ShutdownScreen)
                exit_.assert_not_called()  # ainda animando
                await self._wait(pilot, lambda: exit_.called)
                self.assertTrue(app.screen.query_one("#crt").display)

    async def test_escape_twice_skips_animation(self):
        app = self._app()
        async with app.run_test(size=(80, 24)) as pilot:
            with patch.object(app, "exit") as exit_:
                await pilot.press("escape")
                await pilot.pause(0.05)
                self.assertIsInstance(app.screen, tui_app.ShutdownScreen)
                await pilot.press("escape")
                await pilot.pause(0.05)
                exit_.assert_called()

    async def test_escape_while_busy_only_stops_stream(self):
        app = self._app()
        async with app.run_test(size=(80, 24)) as pilot:
            app.busy = True
            await pilot.press("escape")
            await pilot.pause(0.05)
            self.assertIs(app.screen, app.main_screen)
            self.assertFalse(app._shutting_down)
            app.busy = False

    async def test_escape_in_full_screen_goes_back(self):
        app = self._app()
        async with app.run_test(size=(140, 45)) as pilot:
            await self._cmd(app, pilot, "/config")
            await pilot.press("escape")
            await pilot.pause(0.1)
            self.assertIs(app.screen, app.main_screen)
            self.assertFalse(app._shutting_down)

    async def test_house_party_easter_egg_skips_model(self):
        _fake_stream.last = None
        app = self._app()
        async with app.run_test(size=(140, 45)) as pilot:
            await self._cmd(app, pilot, "House Party")
            self.assertIsInstance(app.screen, tui_app.HousePartyScreen)
            await self._wait(pilot, lambda: all(s.display for s in app.screen.query("PixelSprite")))
            self.assertIn("8 de 8", str(app.screen.query_one("#party-count").render()))
            self.assertIsNone(_fake_stream.last)
            await pilot.press("x")
            await pilot.pause()
            self.assertIs(app.screen, app.main_screen)


if __name__ == "__main__":
    unittest.main()
