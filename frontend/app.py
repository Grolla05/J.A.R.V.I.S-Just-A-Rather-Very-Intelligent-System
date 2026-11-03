"""J.A.R.V.I.S — interface de terminal (Textual).

Pacote `frontend` na raiz do repo; consome o backend (core/services) por import
direto — main.py do backend põe a raiz no sys.path. Dois modos, alternados com Shift+Tab:
- CHAT    → só conversa com o LLM (skills nunca executam);
- COPILOT → agente: o mesmo pipeline, mas com skills liberadas.
"""
import logging
import re
import threading
import time

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Static
from textual.worker import get_current_worker

import core.state as state
from core import db, log, settings
from frontend.commands import help_markdown, parse, unescape
from frontend.widgets import ConfirmScreen, MessageView, PromptInput, SessionPicker
from services import sessions

MODES = ("chat", "copilot")
STREAM_FLUSH_S = 0.05  # re-render do Markdown no máx. a cada 50 ms durante o stream


def _default_stream(text, session_id, images, mode, on_route=None):
    from services.brain import execute_command_stream
    return execute_command_stream(text, session_id=session_id, images=images, mode=mode, on_route=on_route)


def _now_hhmm():
    return time.strftime("%H:%M")


class JarvisApp(App):
    CSS_PATH = "jarvis.tcss"
    TITLE = "J.A.R.V.I.S"
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        # priority: sobrepõe o focus_previous padrão do Textual
        Binding("shift+tab", "toggle_mode", "Modo", priority=True),
        Binding("ctrl+n", "new_session", "Nova"),
        Binding("ctrl+o", "sessions", "Sessões"),
        Binding("ctrl+r", "regen", "Regenerar"),
        Binding("ctrl+t", "toggle_voice", "Voz"),
        Binding("escape", "cancel", "Parar", show=False),
        Binding("ctrl+l", "clear", "Limpar", show=False),
        Binding("ctrl+q", "quit", "Sair", priority=True),
    ]

    # init=False: os watchers consultam widgets que só existem após o compose
    mode = reactive("chat", init=False)
    critical = reactive(False, init=False)
    busy = reactive(False, init=False)

    def __init__(self, stream_fn=None, start_services=True):
        super().__init__()
        self._stream_fn = stream_fn or _default_stream
        self._start_services = start_services
        self.session_id = sessions.new_session_id()
        self.session_title = sessions.DEFAULT_TITLE
        self.pending_image = None   # anexo aguardando a próxima mensagem
        self.edit_message_id = None  # id da msg sendo editada (↑ / /edit)
        self._voice_thread = None
        self._voice_session_id = f"voice_{sessions.new_session_id()}"
        self._telemetry = ""
        self._session_info = "nova sessão"  # "sessão N de M" (cache, evita SQL a cada refresh)
        self._skills_info = ""

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("J.A.R.V.I.S", id="brand")
            yield Static(id="mode-badge")
            yield Static(id="session-title")
            yield Static(id="topbar-info")
        yield VerticalScroll(id="log")
        yield Static(id="attachbar")
        yield PromptInput(id="prompt", placeholder="Fale com o JARVIS…  (/help)")
        with Horizontal(id="statusbar"):
            yield Static(id="status-left")
            yield Static("shift+tab troca o modo · /help", id="status-right")
        yield Footer()

    def on_mount(self):
        self._main_thread = threading.get_ident()
        self.query_one("#attachbar").display = False
        self._refresh_counts()
        self._refresh_topbar()
        self._refresh_status()
        self.query_one("#prompt").focus()
        state.announce = self._announce_from_any_thread
        if self._start_services:
            log.use_tui(_TuiLogHandler(self))
            state.sys_monitor.brain_callback = self._on_system_alert
            state.sys_monitor.start_proactive_monitor(interval=5)
            self.set_interval(settings.TELEMETRY_INTERVAL, self._poll_telemetry)
            self._poll_telemetry()
            self._boot_greeting()
        else:
            self.add_system("Sistemas online.")

    # ---------------------------------------------------------------- helpers
    @property
    def log_view(self) -> VerticalScroll:
        return self.query_one("#log", VerticalScroll)

    def add_message(self, role, text, meta=""):
        view = MessageView(role, text, meta=meta)
        self.log_view.mount(view)
        self.log_view.scroll_end(animate=False)
        return view

    def add_system(self, text):
        return self.add_message("system", text)

    def _call_ui(self, fn, *args):
        """Executa na thread da UI, venha a chamada de onde vier."""
        if threading.get_ident() == getattr(self, "_main_thread", None):
            return fn(*args)
        return self.call_from_thread(fn, *args)

    def _refresh_counts(self):
        """Recalcula 'sessão N de M' e 'skills ativas: K' (consulta o SQLite)."""
        recent = sessions.get_recent_sessions(50)
        ids = [s["id"] for s in recent]
        if self.session_id in ids:
            self._session_info = f"sessão {ids.index(self.session_id) + 1} de {len(ids)}"
        else:
            self._session_info = "nova sessão"
        try:
            from services.skill_settings import list_skills
            active = sum(1 for cat in list_skills() for s in cat["skills"] if s["enabled"])
            self._skills_info = f"skills ativas: {active}"
        except Exception as e:
            log.debug(f"Contagem de skills indisponível: {e}")
            self._skills_info = ""

    def _refresh_topbar(self):
        self.query_one("#mode-badge", Static).update("COPILOT" if self.mode == "copilot" else "CHAT")
        title = (self.session_title or sessions.DEFAULT_TITLE).replace("\n", " ")[:70]
        self.query_one("#session-title", Static).update(title)
        if self.critical:
            info = "⚠ PROTOCOLO CRÍTICO"
        elif self.mode == "copilot":
            info = self._skills_info
        else:
            info = self._session_info
        self.query_one("#topbar-info", Static).update(info)

    def _refresh_status(self):
        voice = "voz on" if state.voice_enabled else "voz off"
        busy = "   pensando…" if self.busy else ""
        model = settings.OLLAMA_MODEL or "?"
        self.query_one("#status-left", Static).update(f"{self._telemetry}   {voice}   {model}{busy}")

    # --------------------------------------------------------------- watchers
    def watch_mode(self, mode):
        self.screen.set_class(mode == "copilot", "-copilot")
        prompt = self.query_one("#prompt", PromptInput)
        prompt.placeholder = (
            "Peça uma ação ao Copilot…  (skills ativas)" if mode == "copilot"
            else "Fale com o JARVIS…  (/help)"
        )
        self._refresh_topbar()

    def watch_critical(self, critical):
        self.screen.set_class(critical, "-critical")
        self._refresh_topbar()

    def watch_busy(self, _busy):
        self._refresh_status()

    # ---------------------------------------------------------------- actions
    def action_toggle_mode(self):
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]

    def action_new_session(self):
        if self.busy:
            return
        self.session_id = sessions.new_session_id()
        self.session_title = sessions.DEFAULT_TITLE
        self.edit_message_id = None
        self.log_view.remove_children()
        self._refresh_counts()
        self._refresh_topbar()
        self.add_system("Nova sessão iniciada.")

    def action_sessions(self):
        if self.busy:
            return
        self.push_screen(SessionPicker(sessions.get_recent_sessions(20), self.session_id),
                         self._open_session)

    def action_regen(self):
        if self.busy:
            return
        last_user = self._last_user_message()
        if not last_user:
            self.notify("Nada para regenerar.", severity="warning")
            return
        sessions.delete_history_from(self.session_id, last_user["id"])
        self.load_session(self.session_id)
        self.send(last_user["content"])

    def action_edit_last(self):
        if self.busy:
            return
        last_user = self._last_user_message()
        if not last_user:
            return
        self.edit_message_id = last_user["id"]
        prompt = self.query_one("#prompt", PromptInput)
        prompt.value = last_user["content"]
        prompt.cursor_position = len(prompt.value)
        self.notify("Editando a última mensagem — Enter reenvia, Esc cancela.")

    def action_cancel(self):
        if self.edit_message_id is not None:
            self.edit_message_id = None
            self.query_one("#prompt", PromptInput).value = ""
            return
        self.workers.cancel_group(self, "chat")

    def action_clear(self):
        self.log_view.remove_children()

    def action_toggle_voice(self):
        state.voice_enabled = not state.voice_enabled
        if state.voice_enabled:
            self._ensure_voice_thread()
            self.add_system("Voz ativada. Diga \"Jarvis\" para chamar.")
        else:
            from services.listen import ear_pause
            ear_pause()
            self.add_system("Voz desativada.")
        self._refresh_status()

    async def action_quit(self):
        self.shutdown_jarvis()

    # --------------------------------------------------------------- sessions
    def _open_session(self, session_id):
        if session_id:
            self.load_session(session_id)

    def load_session(self, session_id):
        self.session_id = session_id
        self.session_title = sessions.get_session_title(session_id)
        self.edit_message_id = None
        self.log_view.remove_children()
        for msg in sessions.get_chat_history(session_id, 50):
            meta = msg["time"] + (f" · anexo: {msg['attachment']}" if msg["attachment"] else "")
            self.add_message(msg["role"], msg["content"], meta=meta)
        self._refresh_counts()
        self._refresh_topbar()

    def _last_user_message(self):
        history = sessions.get_chat_history(self.session_id, 50)
        return next((m for m in reversed(history) if m["role"] == "user"), None)

    # ------------------------------------------------------------------ input
    def on_input_submitted(self, event: PromptInput.Submitted):
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        command = parse(text)
        if command:
            self.run_command(command)
            return
        if self.busy:
            self.notify("Aguarde a resposta atual (Esc interrompe).", severity="warning")
            event.input.value = text
            return
        if self.edit_message_id is not None:
            sessions.delete_history_from(self.session_id, self.edit_message_id)
            self.edit_message_id = None
            self.load_session(self.session_id)
        self.send(unescape(text))

    def run_command(self, cmd):
        name, arg = cmd.name, cmd.arg
        if not cmd.known:
            self.notify(f"Comando desconhecido: /{name}. Veja /help.", severity="warning")
        elif name == "help":
            self.add_message("assistant", help_markdown())
        elif name == "new":
            self.action_new_session()
        elif name == "sessions":
            self.action_sessions()
        elif name == "rename":
            if not arg:
                self.notify("Uso: /rename <título>", severity="warning")
            elif sessions.update_session_title(self.session_id, arg):
                self.session_title = arg
                self._refresh_topbar()
        elif name == "pin":
            current = next((s for s in sessions.get_recent_sessions(50) if s["id"] == self.session_id), None)
            pinned = not (current and current["is_pinned"])
            if sessions.toggle_session_pin(self.session_id, pinned):
                self.notify("Sessão fixada." if pinned else "Sessão desafixada.")
        elif name == "regen":
            self.action_regen()
        elif name == "edit":
            self.action_edit_last()
        elif name == "attach":
            self._attach(arg)
        elif name == "detach":
            self._set_pending_image(None)
        elif name == "mode":
            if arg in MODES:
                self.mode = arg
            elif arg:
                self.notify("Uso: /mode chat | copilot", severity="warning")
            else:
                self.action_toggle_mode()
        elif name == "voice":
            self.action_toggle_voice()
        elif name == "skills":
            self._skills(arg)
        elif name == "clear":
            self.action_clear()
        elif name == "quit":
            self.shutdown_jarvis()

    # ------------------------------------------------------------ attachments
    def _attach(self, path):
        from core.uploads import load_local_file
        if not path:
            self.notify("Uso: /attach <caminho do arquivo>", severity="warning")
            return
        try:
            upload = load_local_file(path)
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        if upload["kind"] == "image":
            self._set_pending_image(upload)
        else:
            self.notify(f"Transcrevendo {upload['name']}…")
            self._transcribe(upload)

    def _set_pending_image(self, upload):
        self.pending_image = upload
        bar = self.query_one("#attachbar", Static)
        bar.display = upload is not None
        if upload:
            bar.update(f" 📎 {upload['name']} — vai junto com a próxima mensagem   [dim]/detach remove[/]")

    @work(thread=True, group="transcribe")
    def _transcribe(self, upload):
        from core.transcription import transcribe_audio_file
        from core.uploads import save_base64_upload
        saved = save_base64_upload(upload["data"], upload["mime"], upload["name"], kind="audio")
        text = transcribe_audio_file(str(saved)) if saved else None
        self.call_from_thread(self._fill_prompt_from_transcription, text)

    def _fill_prompt_from_transcription(self, text):
        if not text:
            self.notify("Falha na transcrição do áudio.", severity="error")
            return
        prompt = self.query_one("#prompt", PromptInput)
        prompt.value = (prompt.value + " " + text).strip()
        prompt.cursor_position = len(prompt.value)
        prompt.focus()

    # ----------------------------------------------------------------- skills
    def _skills(self, arg):
        from services.skill_settings import list_skills, set_enabled
        action, _, target = arg.partition(" ")
        if action in ("on", "off") and target:
            kind = set_enabled(target.strip(), action == "on")
            if kind:
                self.notify(f"{kind} '{target}' {'ativada' if action == 'on' else 'desativada'}.")
            else:
                self.notify(f"Skill/categoria não encontrada: {target}", severity="error")
            return
        lines = []
        for cat in list_skills():
            lines.append(f"**{cat['id']}** {'' if cat['enabled'] else '_(desligada)_'}")
            lines += [f"- {'✅' if s['enabled'] else '⛔'} `{s['id']}`" for s in cat["skills"]]
        lines.append("\n`/skills on|off <skill|categoria>` para alternar.")
        self.add_message("assistant", "\n".join(lines) if len(lines) > 1 else "Nenhuma skill carregada.")

    # ------------------------------------------------------------------- chat
    def send(self, text):
        image = self.pending_image
        self._set_pending_image(None)
        now = _now_hhmm()
        self.add_message("user", text, meta=now + (f" · anexo: {image['name']}" if image else ""))
        reply = self.add_message("assistant", "", meta=f"copilot · {now}" if self.mode == "copilot" else now)
        self.busy = True
        self._stream(text, image, self.mode, self.session_id, reply)

    @work(thread=True, exclusive=True, group="chat")
    def _stream(self, text, image, mode, session_id, reply):
        worker = get_current_worker()
        full = ""
        base_meta = reply.meta
        skill = []  # intent da skill acionada (Copilot), p/ o badge no cabeçalho

        def on_route(intent):
            skill.append(intent)
            self.call_from_thread(reply.set_meta, f"{base_meta} · [{intent}] executando…")

        try:
            images, att_type, att_path = None, None, None
            if image:
                from core.uploads import save_base64_upload
                saved = save_base64_upload(image["data"], image["mime"], image["name"], kind="image")
                if saved:
                    images = [image["data"]]
                    att_type, att_path = "image", str(saved.relative_to(settings.DIR_UPLOADS))
            db.log_interaction("user", text, session_id, att_type, att_path)

            last_flush = 0.0
            for chunk in self._stream_fn(text, session_id, images, mode, on_route=on_route):
                if worker.is_cancelled:
                    full += "\n\n_(interrompido)_"
                    break
                full += chunk or ""
                now = time.monotonic()
                if now - last_flush >= STREAM_FLUSH_S:
                    self.call_from_thread(reply.set_text, full)
                    last_flush = now

            if full.strip() == "PROTOCOL_SHUTDOWN":
                self.call_from_thread(self.shutdown_jarvis)
                return
            if not full.strip():
                full = "_Sem resposta do modelo. O Ollama está rodando?_"
            self.call_from_thread(reply.set_text, full)
            if skill:
                self.call_from_thread(reply.set_meta, f"{base_meta} · [{skill[0]}] ✓")
            db.log_interaction("assistant", full, session_id)
        except Exception as e:
            log.error(f"Erro no stream do chat: {e}")
            self.call_from_thread(reply.set_text, f"**Erro:** `{e}`")
            if skill:
                self.call_from_thread(reply.set_meta, f"{base_meta} · [{skill[0]}] ✗")
        finally:
            self.call_from_thread(self._stream_done, session_id)

    def _stream_done(self, session_id):
        self.busy = False
        if session_id == self.session_id:
            if self.session_title == sessions.DEFAULT_TITLE:
                self.session_title = sessions.get_session_title(session_id)
            self._refresh_counts()
            self._refresh_topbar()
        self.log_view.scroll_end(animate=False)

    # ------------------------------------------------------- alerts / announce
    def _announce_from_any_thread(self, text):
        self._call_ui(self._show_announcement, text)

    def _show_announcement(self, text):
        self.add_system(text)
        pending = state.pending_critical_action
        if pending and not isinstance(self.screen, ConfirmScreen):
            self.push_screen(ConfirmScreen(text, deadline=pending.get("timeout")), self._resolve_critical)

    def _resolve_critical(self, approved):
        self._confirm_worker(bool(approved))

    @work(thread=True, group="confirm")
    def _confirm_worker(self, approved):
        from services.brain import confirm_pending_action
        result = confirm_pending_action(approved)
        self.call_from_thread(self.add_system, result or ("Ação cancelada." if not approved else "Nada a fazer."))

    def _on_system_alert(self, message, is_proactive=False, is_status_signal=False):
        """brain_callback do SystemInfo (roda na thread do monitor)."""
        if is_status_signal:
            if message in ("CRITICAL_START", "CRITICAL_END"):
                self._call_ui(setattr, self, "critical", message == "CRITICAL_START")
            return
        from core.alerts import process_system_alert
        process_system_alert(message, is_proactive)  # anuncia via state.announce

    # -------------------------------------------------------------- telemetry
    def _poll_telemetry(self):
        self.run_worker(self._read_telemetry, thread=True, group="telemetry", exclusive=True)

    def _read_telemetry(self):
        mon = state.sys_monitor
        try:
            cpu = (mon.get_cpu_detailed() or {}).get("usage", 0) or 0
            ram = (mon.get_ram_usage() or {}).get("percent", 0) or 0
            gpu = (mon.get_gpu_info() or {}).get("load", 0) or 0
            text = f"CPU {cpu:.0f}%   RAM {ram:.0f}%   GPU {gpu:.0f}%"
        except Exception as e:
            log.debug(f"Telemetria indisponível: {e}")
            text = "telemetria indisponível"
        self.call_from_thread(self._set_telemetry, text)

    def _set_telemetry(self, text):
        self._telemetry = text
        self._refresh_status()

    # ------------------------------------------------------------------ voice
    def _ensure_voice_thread(self):
        if self._voice_thread and self._voice_thread.is_alive():
            from services.listen import ear_resume
            ear_resume()
            return
        self._voice_thread = threading.Thread(target=self._voice_loop, daemon=True)
        self._voice_thread.start()

    def _voice_loop(self):
        """Loop de voz antigo do main.py, agora opcional e espelhado no log."""
        from services.brain import execute_command
        from services.listen import ear_pause, ear_resume, listen
        from services.speak import speak
        while True:
            try:
                if not state.voice_enabled:
                    time.sleep(0.5)
                    continue
                command = listen()
                if not command or not state.voice_enabled:
                    continue
                self._call_ui(self.add_message, "user", command, "🎙 voz")
                db.log_interaction("user", command, self._voice_session_id)
                response = execute_command(command, session_id=self._voice_session_id)
                if response == "PROTOCOL_SHUTDOWN":
                    ear_pause()
                    speak("Desativando núcleo de força. Até logo, Senhor.")
                    self._call_ui(self.shutdown_jarvis)
                    return
                if response:
                    db.log_interaction("assistant", response, self._voice_session_id)
                    self._call_ui(self.add_message, "assistant", response, "🎙 voz")
                    ear_pause()
                    try:
                        speak(response, show=False)
                    finally:
                        ear_resume()
            except Exception as e:
                log.error(f"Erro no loop de voz: {e}")
                time.sleep(1)

    # ------------------------------------------------------------------- boot
    @work(thread=True, group="boot")
    def _boot_greeting(self):
        try:
            from core import obsidian
            name = obsidian.get_memory("nome") or "Senhor"
        except Exception:
            name = "Senhor"
        self.call_from_thread(self.add_system, f"Sistemas online. Bem-vindo de volta, {name}.")

    def shutdown_jarvis(self):
        log.info("Aplicação encerrada pela TUI.")
        state.announce = None
        self.exit()


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class _TuiLogHandler(logging.Handler):
    """Leva WARNING+ do JarvisLogger para as notificações da TUI."""

    def __init__(self, app):
        super().__init__(level=logging.WARNING)
        self._app = app

    def emit(self, record):
        try:
            msg = _ANSI.sub("", record.getMessage())[:300]
            severity = "error" if record.levelno >= logging.ERROR else "warning"
            self._app._call_ui(lambda: self._app.notify(msg, severity=severity))
        except Exception:
            pass
