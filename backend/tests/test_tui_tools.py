"""TUI — comandos de ferramentas (/web, /gh, /briefing, /clip) via Pilot."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestGitHubCommand(ToolsAppCase):
    async def test_gh_routes_action_and_repo(self):
        from core import github_client
        app = self._app()
        with patch.object(github_client, "run_read", return_value="2 PRs") as run_read:
            async with app.run_test() as pilot:
                await self._send(pilot, "/gh commit dono/repo")
                self.assertEqual(self._last_reply(app).text, "2 PRs")
        run_read.assert_called_once_with("last_commit", "dono/repo")

    async def test_gh_default_is_prs_and_bad_action_warns(self):
        from core import github_client
        app = self._app()
        with patch.object(github_client, "run_read", return_value="ok") as run_read:
            async with app.run_test() as pilot:
                await self._send(pilot, "/gh")
                await self._send(pilot, "/gh deploy")
        run_read.assert_called_once_with("open_prs", None)


class TestBriefingCommand(ToolsAppCase):
    async def test_briefing_command_generates_and_marks(self):
        from core import briefing
        app = self._app()
        with patch.object(briefing, "generate", return_value="**Bom dia.**") as gen, \
             patch.object(briefing, "mark_ran") as mark:
            async with app.run_test() as pilot:
                await self._send(pilot, "/briefing")
                self.assertEqual(self._last_reply(app).text, "**Bom dia.**")
        gen.assert_called_once()
        mark.assert_called_once()

    async def test_no_auto_briefing_without_services(self):
        from core import briefing
        app = self._app()
        with patch.object(briefing, "generate") as gen:
            async with app.run_test() as pilot:
                await pilot.app.workers.wait_for_complete()
        gen.assert_not_called()

    async def test_auto_briefing_respects_pref_and_date(self):
        from core import briefing
        from services import user_prefs
        app = self._app()
        with patch.object(briefing, "generate", return_value="auto!") as gen, \
             patch.object(briefing, "mark_ran"), \
             patch.object(briefing, "should_run_today", return_value=True), \
             patch.object(user_prefs, "get", side_effect=lambda k: k == "briefing_auto"):
            async with app.run_test() as pilot:
                app._maybe_daily_briefing()
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(self._last_reply(app).text, "auto!")
            with patch.object(briefing, "should_run_today", return_value=False):
                async with self._app().run_test() as pilot:
                    pilot.app._maybe_daily_briefing()
                    await pilot.app.workers.wait_for_complete()
        gen.assert_called_once()


class TestBriefingIsSpoken(ToolsAppCase):
    """O briefing é sempre falado — automático, /briefing ou skill — em qualquer modo."""

    async def _wait_spoken(self, pilot, voice):
        for _ in range(100):
            if voice.spoken:
                return
            await pilot.pause(0.05)
        self.fail("briefing não foi falado")

    async def test_briefing_command_speaks_in_chat_with_voice_off(self):
        from core import briefing
        app = self._app()
        with patch.object(briefing, "generate", return_value="Bom dia."), \
             patch.object(briefing, "mark_ran"):
            async with app.run_test() as pilot:
                self.assertEqual(app.mode, "chat")
                self.assertFalse(state.voice_enabled)
                await self._send(pilot, "/briefing")
                await self._wait_spoken(pilot, app.voice)
        self.assertEqual(app.voice.spoken, ["Bom dia."])
        self.assertEqual(app.voice.forced, [True])

    async def test_auto_briefing_speaks_with_voice_off(self):
        from core import briefing
        from services import user_prefs
        app = self._app()
        with patch.object(briefing, "generate", return_value="auto!"), \
             patch.object(briefing, "mark_ran"), \
             patch.object(briefing, "should_run_today", return_value=True), \
             patch.object(user_prefs, "get", side_effect=lambda k: k == "briefing_auto"):
            async with app.run_test() as pilot:
                app._maybe_daily_briefing()
                await pilot.app.workers.wait_for_complete()
                await self._wait_spoken(pilot, app.voice)
        self.assertEqual(app.voice.spoken, ["auto!"])

    async def test_other_tools_stay_silent(self):
        from core import web
        app = self._app()
        with patch.object(web, "research", return_value="resumo"):
            async with app.run_test() as pilot:
                await self._send(pilot, "/web algo")
        self.assertEqual(app.voice.spoken, [])

    async def test_briefing_skill_in_copilot_is_forced(self):
        def stream(text, session_id, images, mode, on_route=None):
            if on_route:
                on_route("DAILY_BRIEFING")
            yield "Bom dia, Senhor."

        voice = FakeVoice("bom dia jarvis")
        app = tui_app.JarvisApp(stream_fn=stream, start_services=False, voice=voice)
        voice.app = app
        async with app.run_test() as pilot:
            await pilot.press("shift+tab")
            await self._wait_spoken(pilot, voice)
        self.assertEqual(voice.spoken, ["Bom dia, Senhor."])
        self.assertEqual(voice.forced, [True])


class TestInsights(ToolsAppCase):
    IDEA = "Tive uma ideia: um painel na cozinha que mostra a agenda da família inteira."

    async def test_chat_turn_goes_to_detector_and_notifies(self):
        seen = []
        app = self._app()
        app._insight_fn = lambda text, reply, origin: seen.append((text, reply, origin)) or "Painel da cozinha"
        async with app.run_test() as pilot:
            with patch.object(app, "notify") as notify:
                await self._send(pilot, self.IDEA)
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
            self.assertEqual(notify.call_args[0][0], "Painel da cozinha")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], self.IDEA)
        self.assertIn("eco de", seen[0][1])

    async def test_skill_and_explain_turns_are_not_checked(self):
        seen = []

        def stream(text, session_id, images, mode, on_route=None):
            if on_route:
                on_route("CALENDAR")
            yield "Amanhã: reunião às 10h."

        app = tui_app.JarvisApp(stream_fn=stream, start_services=False, voice=FakeVoice())
        app._insight_fn = lambda *a: seen.append(a)
        async with app.run_test() as pilot:
            await self._send(pilot, "o que eu tenho amanhã na agenda do trabalho, por favor?")
            app._stream_fn = _fake_stream
            app.explain_snippet("def f():\n    return {1: (2)}")
            await pilot.app.workers.wait_for_complete()
            await pilot.pause()
        self.assertEqual(seen, [])

    async def test_no_detector_without_services_and_errors_are_swallowed(self):
        app = self._app()
        self.assertIsNone(app._insight_fn)
        app._insight_fn = MagicMock(side_effect=RuntimeError("ollama fora"))
        async with app.run_test() as pilot:
            await self._send(pilot, self.IDEA)
            await pilot.app.workers.wait_for_complete()
            await pilot.pause()
            self.assertIn("eco de", self._last_reply(app).text)

    async def test_ideia_command(self):
        from services import insights
        app = self._app()
        with patch.object(insights, "save_text", return_value="Ideia registrada") as save:
            async with app.run_test() as pilot:
                await self._send(pilot, "/ideia vender o curso em módulos")
                self.assertEqual(self._last_reply(app).text, "Ideia registrada")
                await self._send(pilot, "/ideia")
        save.assert_called_once()
        self.assertEqual(save.call_args[0][0], "vender o curso em módulos")


class TestReminders(ToolsAppCase):
    QUIET = {"presentation": False, "dnd": True, "meeting": False, "fullscreen": False}
    FREE = {"presentation": False, "dnd": False, "meeting": False, "fullscreen": False}

    def setUp(self):
        super().setUp()
        self._backlog = list(state.dnd_backlog)
        state.dnd_backlog.clear()

    def tearDown(self):
        state.dnd_backlog[:] = self._backlog
        super().tearDown()

    async def _run(self, items, ctx):
        from services import notify_filter, reminders
        app = self._app()
        with patch.object(reminders, "collect", return_value=items), \
             patch.object(notify_filter, "context", return_value=ctx):
            async with app.run_test() as pilot:
                app._poll_reminders()
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                replies = [(m.text, m.meta) for m in app.query(tui_app.MessageView) if m.role == "assistant"]
        return app, replies

    async def test_reminder_is_shown_and_spoken(self):
        item = {"text": "Senhor, em 2 horas, às 14:00, o senhor tem Prova.", "kind": "lead", "urgent": False}
        app, replies = await self._run([item], self.FREE)
        self.assertEqual(replies[-1][0], item["text"])
        self.assertTrue(replies[-1][1].startswith("lembrete · "))
        self.assertEqual(app.voice.spoken, [item["text"]])
        self.assertEqual(app.voice.forced, [True])  # fala mesmo no Chat, com a voz desligada

    async def test_lead_waits_in_backlog_during_dnd(self):
        item = {"text": "Senhor, em 2 horas, às 14:00, o senhor tem Prova.", "kind": "lead", "urgent": False}
        app, replies = await self._run([item], self.QUIET)
        self.assertEqual(replies, [])
        self.assertEqual(app.voice.spoken, [])
        self.assertEqual(len(state.dnd_backlog), 1)

    async def test_urgent_shows_during_dnd_but_stays_silent(self):
        item = {"text": "Senhor, saia agora para Prova às 14:00.", "kind": "leave", "urgent": True}
        app, replies = await self._run([item], self.QUIET)
        self.assertEqual(replies[-1][0], item["text"])
        self.assertEqual(app.voice.spoken, [])
        self.assertEqual(state.dnd_backlog, [])

    async def test_no_timer_without_services(self):
        from services import reminders
        app = self._app()
        with patch.object(reminders, "collect") as collect:
            async with app.run_test() as pilot:
                await pilot.pause(0.1)
        collect.assert_not_called()

    async def test_lembrete_command(self):
        from services import reminders
        app = self._app()
        with patch.object(reminders, "create_from_text", return_value="criado") as create, \
             patch.object(reminders, "list_text", return_value="lista") as listing, \
             patch.object(reminders, "remove_text", return_value="removido") as remove:
            async with app.run_test() as pilot:
                await self._send(pilot, "/lembrete em 30 min tirar a roupa")
                self.assertEqual(self._last_reply(app).text, "criado")
                await self._send(pilot, "/lembrete")
                self.assertEqual(self._last_reply(app).text, "lista")
                await self._send(pilot, "/lembrete rm 2")
                self.assertEqual(self._last_reply(app).text, "removido")
                await self._send(pilot, "/lembrete rm")
        create.assert_called_once_with("em 30 min tirar a roupa")
        listing.assert_called_once()
        remove.assert_called_once_with(2)


class TestWebWatch(ToolsAppCase):
    FREE = {"presentation": False, "dnd": False, "meeting": False, "fullscreen": False}
    QUIET = {"presentation": False, "dnd": True, "meeting": False, "fullscreen": False}

    def setUp(self):
        super().setUp()
        self._backlog = list(state.dnd_backlog)
        state.dnd_backlog.clear()

    def tearDown(self):
        state.dnd_backlog[:] = self._backlog
        super().tearDown()

    async def _tick(self, items, ctx):
        from services import notify_filter, web_watch
        app = self._app()
        with patch.object(web_watch, "collect", return_value=items), \
             patch.object(notify_filter, "context", return_value=ctx):
            async with app.run_test() as pilot:
                app._poll_webwatch()
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                replies = [(m.text, m.meta) for m in app.query(tui_app.MessageView) if m.role == "assistant"]
        return app, replies

    async def test_change_is_shown_with_vigia_meta(self):
        item = {"text": "O preço em **loja.com.br** caiu de R$ 10,00 para R$ 8,00, Senhor.", "urgent": False}
        app, replies = await self._tick([item], self.FREE)
        self.assertEqual(replies[-1][0], item["text"])
        self.assertTrue(replies[-1][1].startswith("vigia · "))
        self.assertEqual(app.voice.spoken, [item["text"]])

    async def test_normal_change_waits_during_dnd_target_hit_shows(self):
        normal = {"text": "A página mudou.", "urgent": False}
        app, replies = await self._tick([normal], self.QUIET)
        self.assertEqual(replies, [])
        self.assertEqual(len(state.dnd_backlog), 1)
        hit = {"text": "Chegou no seu alvo.", "urgent": True}
        app, replies = await self._tick([hit], self.QUIET)
        self.assertEqual(replies[-1][0], hit["text"])
        self.assertEqual(app.voice.spoken, [])

    async def test_no_timer_without_services(self):
        from services import web_watch
        app = self._app()
        with patch.object(web_watch, "collect") as collect:
            async with app.run_test() as pilot:
                await pilot.pause(0.1)
        collect.assert_not_called()

    async def test_vigiar_command(self):
        from services import web_watch
        app = self._app()
        with patch.object(web_watch, "create_from_text", return_value="vigiando") as create, \
             patch.object(web_watch, "list_text", return_value="lista") as listing, \
             patch.object(web_watch, "remove_text", return_value="removido") as remove:
            async with app.run_test() as pilot:
                await self._send(pilot, "/vigiar https://loja.com.br/x preço abaixo de 300")
                self.assertEqual(self._last_reply(app).text, "vigiando")
                await self._send(pilot, "/vigiar")
                self.assertEqual(self._last_reply(app).text, "lista")
                await self._send(pilot, "/vigia rm 1")
                self.assertEqual(self._last_reply(app).text, "removido")
                await self._send(pilot, "/vigiar rm")
        create.assert_called_once_with("https://loja.com.br/x preço abaixo de 300")
        listing.assert_called_once()
        remove.assert_called_once_with(1)


class TestChecarCommand(ToolsAppCase):
    async def test_checar_and_usage(self):
        from core import factcheck
        app = self._app()
        with patch.object(factcheck, "check", return_value="**Veredito: ❌ FALSO**") as check:
            async with app.run_test() as pilot:
                await self._send(pilot, "/checar a Muralha da China é visível do espaço")
                reply = self._last_reply(app)
                self.assertEqual(reply.text, "**Veredito: ❌ FALSO**")
                self.assertTrue(reply.meta.startswith("checagem · "))
                await self._send(pilot, "/checar")
        check.assert_called_once_with("a Muralha da China é visível do espaço")


class TestFormularioCommand(ToolsAppCase):
    async def test_formulario_with_and_without_link(self):
        from services import form_fill
        app = self._app()
        with patch.object(form_fill, "request", return_value="Formulário **X** preenchido") as req:
            async with app.run_test() as pilot:
                await self._send(pilot, "/formulario https://forms.example.com/a")
                reply = self._last_reply(app)
                self.assertEqual(reply.text, "Formulário **X** preenchido")
                self.assertEqual(reply.meta, "formulário")
                await self._send(pilot, "/form")
        self.assertEqual([c.args for c in req.call_args_list], [("https://forms.example.com/a",), ("",)])


class TestEmailCommand(ToolsAppCase):
    async def test_list_read_and_usage(self):
        from services import mailbox
        app = self._app()
        with patch.object(mailbox, "priority_text", return_value="**E-mails por prioridade**") as listing, \
             patch.object(mailbox, "read_text", return_value=iter(["**Prova** — Ana\n\n", "resumo"])) as read:
            async with app.run_test() as pilot:
                await self._send(pilot, "/email")
                self.assertEqual(self._last_reply(app).text, "**E-mails por prioridade**")
                await self._send(pilot, "/email ler 2")
                self.assertEqual(self._last_reply(app).text, "**Prova** — Ana\n\nresumo")
                await self._send(pilot, "/email dançar")
        listing.assert_called_once()
        read.assert_called_once_with(2)

    async def test_reply_opens_confirm_screen(self):
        from core import pending
        from services import mailbox

        def arm(n, text):
            pending.arm("EMAIL_SEND", "Rascunho pronto. Confirma o envio?", lambda: "enviado", timeout_s=60)
            return "Rascunho pronto. Confirma o envio?"

        app = self._app()
        with patch.object(mailbox, "reply_text", side_effect=arm) as reply:
            async with app.run_test() as pilot:
                await self._send(pilot, "/email responder 1 diga que confirmo")
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                self.assertIsInstance(app.screen, tui_app.ConfirmScreen)
                await pilot.press("n")
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
        reply.assert_called_once_with(1, "diga que confirmo")
        self.assertIsNone(state.pending_critical_action)


class TestEmailTrashCommand(ToolsAppCase):
    async def test_apagar_routes_to_trash_request(self):
        from services import email_trash
        app = self._app()
        with patch.object(email_trash, "request", return_value="Mover para a Lixeira?") as req:
            async with app.run_test() as pilot:
                await self._send(pilot, "/email apagar 2 3")
                self.assertEqual(self._last_reply(app).text, "Mover para a Lixeira?")
        req.assert_called_once_with("2 3")


class TestInstallCommand(ToolsAppCase):
    async def test_install_and_download_route_to_software(self):
        from services import software
        app = self._app()
        with patch.object(software, "request", return_value="Instalar 7-Zip?") as req:
            async with app.run_test() as pilot:
                await self._send(pilot, "/instalar 7-zip")
                self.assertEqual(self._last_reply(app).text, "Instalar 7-Zip?")
                await self._send(pilot, "/baixar vlc")
        self.assertEqual(req.call_args_list[0].args, ("7-zip", software.INSTALL))
        self.assertEqual(req.call_args_list[1].args, ("vlc", software.DOWNLOAD))


class TestRedeCommand(ToolsAppCase):
    async def test_scan_trust_and_usage(self):
        from services import net_guard
        app = self._app()
        with patch.object(net_guard, "scan_text", return_value="**Perímetro de rede**") as scan, \
             patch.object(net_guard, "trust_text", return_value="anotado") as trust:
            async with app.run_test() as pilot:
                await self._send(pilot, "/rede")
                self.assertEqual(self._last_reply(app).text, "**Perímetro de rede**")
                await self._send(pilot, "/rede confiar 2")
                self.assertEqual(self._last_reply(app).text, "anotado")
                await self._send(pilot, "/rede dançar")
        scan.assert_called_once()
        trust.assert_called_once_with(2)

    async def test_kept_list_and_forget_needs_confirmation(self):
        from services import net_trust
        app = self._app()
        with patch.object(net_trust, "list_text", return_value="mantidos") as listing, \
             patch.object(net_trust, "forget", return_value="esquecido") as forget:
            async with app.run_test() as pilot:
                await self._send(pilot, "/rede mantidos")
                self.assertEqual(self._last_reply(app).text, "mantidos")
                await self._send(pilot, "/rede esquecer 1")
                self.assertIsInstance(app.screen, tui_app.ConfirmScreen)
                await pilot.press("n")
                await pilot.pause()
                forget.assert_not_called()
                await self._send(pilot, "/rede esquecer 1")
                await pilot.press("s")
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(self._last_reply(app).text, "esquecido")
        listing.assert_called_once()
        forget.assert_called_once_with(1)

    async def test_block_and_reset_need_confirmation(self):
        from services import net_guard
        app = self._app()
        with patch.object(net_guard, "block_ip", return_value="bloqueado") as block, \
             patch.object(net_guard, "reset_text", return_value="apagada") as reset:
            async with app.run_test() as pilot:
                await self._send(pilot, "/rede bloquear 185.10.10.10")
                self.assertIsInstance(app.screen, tui_app.ConfirmScreen)
                await pilot.press("n")
                await pilot.pause()
                block.assert_not_called()
                await self._send(pilot, "/rede bloquear 185.10.10.10")
                await pilot.press("s")
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(self._last_reply(app).text, "bloqueado")
                await self._send(pilot, "/rede reset")
                await pilot.press("s")
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(self._last_reply(app).text, "apagada")
        block.assert_called_once_with("185.10.10.10")
        reset.assert_called_once()

    async def test_pref_toggles_watch_and_no_watch_without_services(self):
        from core import netwatch
        from services import user_prefs
        app = self._app()
        async with app.run_test():
            self.assertIsNone(app._net_watch)
            with patch.object(user_prefs, "get", return_value=True), \
                 patch.object(netwatch.NetworkWatch, "check_once", return_value=[]):
                app.on_pref_changed("net_monitor")
                self.assertTrue(app._net_watch.running)
            with patch.object(user_prefs, "get", return_value=False):
                app.on_pref_changed("net_monitor")
            self.assertFalse(app._net_watch.running)

    async def test_status_screen_shows_perimeter(self):
        from frontend.screens import status as status_screen
        app = self._app()
        with patch.object(status_screen, "perimeter_text", return_value="portas expostas  1"):
            async with app.run_test() as pilot:
                await self._send(pilot, "/status")
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(str(app.screen.query_one("#status-net").content), "portas expostas  1")


TRACE = 'Traceback (most recent call last):\n  File "main.py", line 3, in <module>\nValueError: x'


class TestExplainSnippet(ToolsAppCase):
    """Explicar = turno do Chat (histórico + follow-up), direto ao LLM (force_chat)."""

    def _recording_app(self, calls):
        def stream(text, session_id, images, mode, on_route=None, force_chat=False):
            calls.append({"text": text, "mode": mode, "force_chat": force_chat})
            yield "diagnóstico pronto"
        return tui_app.JarvisApp(stream_fn=stream, start_services=False, voice=FakeVoice())

    async def _settle(self, pilot):
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()

    async def test_error_uses_error_prompt_and_is_saved_in_session(self):
        calls = []
        app = self._recording_app(calls)
        async with app.run_test() as pilot:
            self.assertTrue(app.explain_snippet(TRACE, source="seleção"))
            await self._settle(pilot)
            self.assertEqual(self._last_reply(app).text, "diagnóstico pronto")
            user = [m for m in app.query(tui_app.MessageView) if m.role == "user"][-1]
            self.assertIn("seleção · erro", user.meta)
            self.assertIn("ValueError: x", user.text)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["force_chat"])
        self.assertEqual(calls[0]["mode"], "chat")
        self.assertIn("Causa provável", calls[0]["text"])   # prompts/explain_error.md
        self.assertIn("ValueError: x", calls[0]["text"])
        rows = sessions.get_chat_history(app.session_id)
        self.assertEqual([r["role"] for r in rows], ["user", "assistant"])
        self.assertIn("ValueError: x", rows[0]["content"])   # o trecho fica na sessão: follow-up tem contexto
        self.assertNotIn("Causa provável", rows[0]["content"])

    async def test_code_uses_code_prompt_and_old_fakes_still_work(self):
        app = self._app()  # _fake_stream não aceita force_chat
        async with app.run_test() as pilot:
            app.explain_snippet("def f():\n    return {1: (2)}", source="clipboard")
            await self._settle(pilot)
            self.assertIn("pontos de atenção", self._last_reply(app).text)  # eco do prompts/explain_code.md
            user = [m for m in app.query(tui_app.MessageView) if m.role == "user"][-1]
            self.assertIn("clipboard · código", user.meta)

    async def test_busy_or_empty_does_nothing(self):
        calls = []
        app = self._recording_app(calls)
        async with app.run_test() as pilot:
            self.assertFalse(app.explain_snippet("   "))
            app.busy = True
            self.assertFalse(app.explain_snippet(TRACE))
            app.busy = False
            await self._settle(pilot)
        self.assertEqual(calls, [])

    async def test_agent_signal_takes_payload_closes_screens_and_goes_to_chat(self):
        from core import presence
        calls = []
        app = self._recording_app(calls)
        async with app.run_test() as pilot:
            app._start_services = True  # só o caminho do agente; o on_mount já rodou sem serviços
            await pilot.press("shift+tab")
            self.assertEqual(app.mode, "copilot")
            with patch.object(presence, "take_explain", side_effect=[TRACE, None]):
                app._on_summon("EXPLAIN")
                await self._settle(pilot)
                app._on_summon("EXPLAIN")  # sem trecho pendente: nada acontece
                await self._settle(pilot)
            self.assertEqual(app.mode, "chat")
            app._start_services = False
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["force_chat"])


class TestClipCommand(ToolsAppCase):
    async def test_clip_explains_in_chat_and_translates_in_tool_bubble(self):
        from core import clipboard
        app = self._app()
        code = "def f():\n    return {1: (2)}"
        with patch.object(clipboard, "read", return_value=code), \
             patch.object(clipboard, "act", return_value="traduzido") as act:
            async with app.run_test() as pilot:
                await self._send(pilot, "/clip")
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                self.assertIn("eco de", self._last_reply(app).text)   # virou turno do Chat
                self.assertIn("def f()", self._last_reply(app).text)
                await self._send(pilot, "/clip traduzir")
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(self._last_reply(app).text, "traduzido")
        self.assertEqual([c.args[0] for c in act.call_args_list], ["translate"])

    async def test_clip_empty_clipboard_says_so(self):
        from core import clipboard
        app = self._app()
        with patch.object(clipboard, "read", return_value=""):
            async with app.run_test() as pilot:
                await self._send(pilot, "/clip")
                await pilot.app.workers.wait_for_complete()
                await pilot.pause()
                self.assertIn("vazio", self._last_reply(app).text)

    async def test_clip_bad_action_and_empty_history(self):
        from core import clipboard
        from services import clip_history
        app = self._app()
        # banco de teste vazio: sem o patch, /clip hist lia o histórico real do usuário
        with patch.object(clip_history, "db", self.db), patch.object(clipboard, "act") as act:
            async with app.run_test() as pilot:
                await self._send(pilot, "/clip dançar")
                await self._send(pilot, "/clip hist")
                self.assertIn("Monitor de clipboard", self._last_reply(app).text)
        act.assert_not_called()

    async def test_history_search_use_and_act_on_item(self):
        from core import clipboard, selection
        from services import clip_history
        app = self._app()
        with patch.object(clip_history, "db", self.db), \
             patch.object(clipboard, "act", return_value="feito") as act, \
             patch.object(selection, "write_clipboard", return_value=True) as write:
            clip_history.add("text", "relatório de vendas do trimestre passado")
            clip_history.add("code", "def f():\n    return {1: (2)}")
            async with app.run_test() as pilot:
                await self._send(pilot, "/clip hist")
                self.assertIn("1. *código*", self._last_reply(app).text)
                self.assertIn("2. *texto*", self._last_reply(app).text)
                await self._send(pilot, "/clip buscar vendas")
                self.assertIn("relatório de vendas", self._last_reply(app).text)
                self.assertNotIn("def f", self._last_reply(app).text)
                await self._send(pilot, "/clip buscar nada-disso")
                self.assertIn("Nenhuma cópia", self._last_reply(app).text)
                await self._send(pilot, "/clip usar 2")
                self.assertIn("de volta ao clipboard", self._last_reply(app).text)
                await self._send(pilot, "/clip usar 9")
                self.assertIn("Não há item 9", self._last_reply(app).text)
                await self._send(pilot, "/clip resumir 2")
                self.assertEqual(self._last_reply(app).text, "feito")
                await self._send(pilot, "/clip explicar 9")
                self.assertIn("Não há item 9", self._last_reply(app).text)
        write.assert_called_once_with("relatório de vendas do trimestre passado")
        act.assert_called_once_with("summarize", "relatório de vendas do trimestre passado")

    async def test_clear_asks_confirmation(self):
        from services import clip_history
        app = self._app()
        with patch.object(clip_history, "db", self.db):
            clip_history.add("text", "relatório de vendas do trimestre passado")
            async with app.run_test() as pilot:
                await self._send(pilot, "/clip limpar")
                self.assertIsInstance(app.screen, tui_app.ConfirmScreen)
                await pilot.press("n")
                await pilot.pause()
                self.assertEqual(len(clip_history.recent()), 1)
                await self._send(pilot, "/clip limpar")
                await pilot.press("s")
                await pilot.pause()
                self.assertEqual(clip_history.recent(), [])

    async def test_monitor_writes_to_history(self):
        from services import clip_history, user_prefs
        app = self._app()
        text = "O relatório de vendas do mês passado está na pasta."
        async with app.run_test():
            with patch.object(clip_history, "db", self.db), \
                 patch.object(user_prefs, "get", return_value=True), \
                 patch("core.clipboard.read", return_value=""):
                app.on_pref_changed("clipboard_monitor")
                try:
                    app._clip_monitor.read_fn = lambda: text
                    app._clip_monitor.check_once()
                finally:
                    app._clip_monitor.stop()
                self.assertEqual(clip_history.recent()[0]["text"], text)

    async def test_pref_toggles_monitor_and_suggestion_cooldown(self):
        from services import user_prefs
        app = self._app()
        async with app.run_test() as pilot:
            with patch.object(user_prefs, "get", return_value=True), \
                 patch("core.clipboard.read", return_value=""):
                app.on_pref_changed("clipboard_monitor")
                self.assertTrue(app._clip_monitor.running)
            with patch.object(user_prefs, "get", return_value=False):
                app.on_pref_changed("clipboard_monitor")
            self.assertFalse(app._clip_monitor.running)
            before = len(app.query(tui_app.MessageView))
            app._on_clip_suggest("code", "x")
            app._on_clip_suggest("url", "y")  # dentro do cooldown: ignorado
            await pilot.pause()
            self.assertEqual(len(app.query(tui_app.MessageView)), before + 1)


if __name__ == "__main__":
    unittest.main()
