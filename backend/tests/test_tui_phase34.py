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

    async def test_ctrl_q_twice_skips_animation(self):
        app = self._app()
        async with app.run_test(size=(80, 24)) as pilot:
            with patch.object(app, "exit") as exit_:
                await pilot.press("ctrl+q")
                await pilot.pause(0.05)
                await pilot.press("ctrl+q")
                await pilot.pause(0.05)
                exit_.assert_called()

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
