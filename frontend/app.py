"""J.A.R.V.I.S — interface de terminal (Textual).

Pacote `frontend` na raiz do repo; consome o backend (core/services) por import
direto — main.py do backend põe a raiz no sys.path. Dois modos, alternados com Shift+Tab:
- CHAT    → conversa por texto com o LLM (skills nunca executam);
- COPILOT → agente SÓ POR VOZ: o campo de texto dá lugar à barra de voz e à orb;
            o mesmo pipeline de stream, com skills liberadas, e a resposta é falada.
"""
import inspect
import logging
import re
import threading
import time
from collections import deque

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Static
from textual.worker import get_current_worker

import core.state as state
from core import db, log, settings
from frontend.commands import (
    Command,
    help_markdown,
    palette_entries,
    parse,
    parse_dnd_arg,
    parse_focus_arg,
    unescape,
)
from frontend.screens import (
    BootScreen,
    CommandPalette,
    HousePartyScreen,
    JarvisScreen,
    LogScreen,
    SessionPicker,
    SettingsScreen,
    ShutdownScreen,
    SkillsScreen,
    StatusScreen,
    VaultScreen,
    is_trigger,
)
from frontend.sprites import block_bar
from frontend.widgets import (
    ConfirmScreen,
    CopilotHero,
    MessageView,
    PromptInput,
    StatusLine,
    VoiceBar,
)
from services import sessions

MODES = ("chat", "copilot")
STREAM_FLUSH_S = 0.05  # re-render do Markdown no máx. a cada 50 ms durante o stream
TELEMETRY_HISTORY = 40  # amostras guardadas p/ os sparklines (40 × 3 s = 2 min)
NOTE_CONTEXT_MAX = 4000  # caracteres da nota do /vault que vão ao modelo


def _default_stream(text, session_id, images, mode, on_route=None):
    from services.brain import execute_command_stream
    return execute_command_stream(text, session_id=session_id, images=images, mode=mode, on_route=on_route)


class _DefaultVoice:
    """Sentidos reais (mic + TTS), importados só quando usados — import lazy
    mantém o boot sem microfone/pygame. Os testes injetam um fake."""

    def listen(self, on_level=None):
        from services.listen import listen
        return listen(on_level=on_level)

    def speak(self, text):
        from services.speak import speak
        speak(text, show=False)

    def pause(self):
        from services.listen import ear_pause
        ear_pause()

    def resume(self):
        from services.listen import ear_resume
        ear_resume()


def _now_hhmm():
    return time.strftime("%H:%M")


class JarvisApp(App, inherit_bindings=False):
    # inherit_bindings=False: o ctrl+q prioritário do App base furava a ordem
    # do rodapé ("Sair" antes de "Nova"); o ctrl+c dele é recolocado abaixo.
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
        # priority: o Input do Textual usa Ctrl+K para "apagar até o fim"
        Binding("ctrl+k", "palette", "Menu", priority=True),
        Binding("escape", "cancel", "Parar", show=False),
        Binding("ctrl+l", "clear", "Limpar", show=False),
        # sem priority: o Footer lista bindings prioritários primeiro, e Sair fica no fim
        Binding("ctrl+q", "quit", "Sair"),
        Binding("ctrl+c", "help_quit", show=False, system=True),
    ]

    # init=False: os watchers consultam widgets que só existem após o compose
    mode = reactive("chat", init=False)
    critical = reactive(False, init=False)
    busy = reactive(False, init=False)

    def __init__(self, stream_fn=None, start_services=True, voice=None, boot_fn=None, start_mode=None):
        """`boot_fn(report)` (core.boot.run_boot) mostra a tela de boot antes da
        conversa; None (testes, `start_services=False`) pula direto pro chat.
        `start_mode="copilot"` (main.py --copilot, aberto pelo Win+J) entra no
        Copilot assim que a conversa aparece."""
        super().__init__()
        self._start_mode = start_mode if start_mode in MODES else None
        self._presence_stop = threading.Event()  # encerra a escuta dos sinais do agente
        self._stream_fn = stream_fn or _default_stream
        self._start_services = start_services
        self._boot_fn = boot_fn
        self._shutting_down = False
        self.voice = voice or _DefaultVoice()
        self._clip_monitor = None
        self._clip_last_suggest = -1e9
        self.session_id = sessions.new_session_id()
        self.session_title = sessions.DEFAULT_TITLE
        self.pending_image = None   # anexo aguardando a próxima mensagem
        self.pending_note = None    # nota do /vault aguardando a próxima mensagem
        self.edit_message_id = None  # id da msg sendo editada (↑ / /edit)
        self._voice_thread = None
        self._voice_stop = threading.Event()  # encerra o loop de voz junto com o app
        self._telemetry = ""
        self._session_info = "nova sessão"  # "sessão N de M" (cache, evita SQL a cada refresh)
        self._skills_info = ""
        self._skills_active = 0
        # Histórico curto da telemetria (sparklines do /status) e último turno
        # com skill (timeline do /log). Só a thread da UI escreve aqui.
        self.telemetry_history = {name: deque(maxlen=TELEMETRY_HISTORY)
                                  for name in ("CPU", "RAM", "GPU", "REDE")}
        self.last_skill_turn = None
        self.last_net = (0.0, 0.0)
        self.health = {}  # {"OLL": (status, detalhe), ...} — core.health, a cada HEALTH_INTERVAL

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("J.A.R.V.I.S", id="brand")
            yield Static(id="mode-badge")
            yield Static(id="session-title")
            yield Static(id="topbar-info")
        yield CopilotHero(model=settings.OLLAMA_MODEL, id="copilot-hero")
        yield VerticalScroll(id="log")
        yield Static(id="attachbar")
        yield PromptInput(id="prompt", placeholder="Fale com o JARVIS…  (/help)")
        yield VoiceBar(id="voicebar")
        # Telemetria e atalhos dividem UMA linha (canvas "JARVIS TUI")
        with Horizontal(id="statusbar", classes="statusbar"):
            yield StatusLine(id="status-left", classes="status-left")
            yield Footer(show_command_palette=False)

    def on_mount(self):
        self._main_thread = threading.get_ident()
        self.main_screen.query_one("#attachbar").display = False
        self.main_screen.query_one("#voicebar").display = False
        self.main_screen.query_one("#copilot-hero").display = False
        self._refresh_counts()
        self._refresh_topbar()
        self._refresh_status()
        self.main_screen.query_one("#prompt").focus()
        state.announce = self._announce_from_any_thread
        if self._start_services:
            log.use_tui(_TuiLogHandler(self))
            state.sys_monitor.brain_callback = self._on_system_alert
            state.sys_monitor.start_proactive_monitor(interval=5)
            self.set_interval(settings.TELEMETRY_INTERVAL, self._poll_telemetry)
            self._poll_telemetry()
            self.set_interval(settings.HEALTH_INTERVAL, self._poll_health)
            self._poll_health()
            self._boot_greeting()
            self._sync_clipboard_monitor()
            self._register_presence()
        else:
            self.add_system("`[  OK  ]` Sistemas online.")
        if self._boot_fn:
            from core.boot import STEPS
            self.push_screen(BootScreen(self._boot_fn, total_steps=len(STEPS)), self._boot_closed)
        else:
            self._apply_start_mode()

    def _boot_closed(self, _result=None):
        self.main_screen.query_one("#prompt").focus()
        self._apply_start_mode()

    def _apply_start_mode(self):
        if self._start_mode and self._start_mode != self.mode:
            self.mode = self._start_mode
        self._start_mode = None

    # ------------------------------------------- agente residente (Win+J)
    def _register_presence(self):
        """Anuncia esta TUI ao agente (tui.json) e escuta os sinais dele."""
        try:
            from core import presence
            from core.window_utils import find_terminal_window
            presence.register_tui(find_terminal_window())
            presence.wait_signals(lambda name: self._call_ui(self._on_summon, name), self._presence_stop)
        except Exception as e:
            log.debug(f"Presença para o agente indisponível: {e}")

    def _unregister_presence(self):
        self._presence_stop.set()
        if not self._start_services:
            return
        try:
            from core import presence
            presence.unregister_tui()
        except Exception as e:
            log.debug(f"Falha ao remover a presença: {e}")

    def _on_summon(self, name):
        """Sinal do agente: SUMMON -> Copilot (fecha telas cheias e a paleta);
        TO_CHAT -> Chat. O ConfirmScreen (ação crítica) nunca é fechado."""
        if not self.is_running or self._shutting_down:
            return
        if name == "SUMMON":
            while len(self.screen_stack) > 1 and not isinstance(self.screen, (ConfirmScreen, BootScreen)):
                self.pop_screen()
            self.mode = "copilot"
        elif name == "TO_CHAT":
            self.mode = "chat"

    # ---------------------------------------------------------------- helpers
    @property
    def log_view(self) -> VerticalScroll:
        return self.main_screen.query_one("#log", VerticalScroll)

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
            self._skills_active = active
            self._skills_info = f"skills ativas: {active}"
        except Exception as e:
            log.debug(f"Contagem de skills indisponível: {e}")
            self._skills_active = 0
            self._skills_info = ""
        self.main_screen.query_one("#copilot-hero", CopilotHero).set_info(settings.OLLAMA_MODEL, self._skills_active)

    def _refresh_topbar(self):
        self.main_screen.query_one("#mode-badge", Static).update("COPILOT" if self.mode == "copilot" else "CHAT")
        title = (self.session_title or sessions.DEFAULT_TITLE).replace("\n", " ")[:70]
        self.main_screen.query_one("#session-title", Static).update(title)
        if self.critical:
            reasons = getattr(state.sys_monitor, "critical_reasons", None) or []
            info = " · ".join(["⚠ PROTOCOLO CRÍTICO", *reasons[:2]])
        elif self.mode == "copilot":
            info = " · ".join(p for p in ("somente voz", self._skills_info) if p)
        else:
            info = self._session_info
        self.main_screen.query_one("#topbar-info", Static).update(info)

    def status_text(self):
        """Lado esquerdo da linha de status: telemetria · saúde · voz · modelo · ocupado."""
        from core.health import status_line
        voice = "voz on" if state.voice_enabled else "voz off"
        busy = "   ▚ pensando…" if self.busy else ""
        model = settings.OLLAMA_MODEL or "?"
        parts = [p for p in (self._telemetry, status_line(self.health), self._focus_badge(), voice, model) if p]
        return "   ".join(parts) + busy

    def _refresh_status(self):
        self.main_screen.query_one("#status-left", StatusLine).update(self.status_text())

    # --------------------------------------------------------------- watchers
    @property
    def main_screen(self):
        """Tela da conversa — com um modal aberto, self.screen é o modal."""
        return self.screen_stack[0]

    def watch_mode(self, mode):
        copilot = mode == "copilot"
        self.main_screen.set_class(copilot, "-copilot")
        prompt = self.main_screen.query_one("#prompt", PromptInput)
        prompt.display = not copilot
        self.main_screen.query_one("#voicebar").display = copilot
        self.main_screen.query_one("#copilot-hero").display = copilot
        if not copilot:
            prompt.focus()
        self._set_voice(copilot)  # Copilot é só por voz; o Chat é só texto
        self._refresh_topbar()
        self.refresh_bindings()

    # Atalhos da conversa que não valem dentro das telas cheias (/status, /log…)
    _CONVERSATION_ACTIONS = {"toggle_mode", "new_session", "sessions", "regen", "toggle_voice", "cancel", "clear",
                             "palette"}

    def check_action(self, action, parameters):
        if action in self._CONVERSATION_ACTIONS and isinstance(self.screen, JarvisScreen):
            return False
        # ^t no Copilot não faz sentido (a voz já está ligada): some do rodapé
        if action == "toggle_voice" and self.mode == "copilot":
            return False
        return True

    def watch_critical(self, critical):
        self.main_screen.set_class(critical, "-critical")
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
        self.push_screen(SessionPicker(sessions.get_recent_sessions(20), self.session_id, service=sessions),
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
        prompt = self.main_screen.query_one("#prompt", PromptInput)
        prompt.value = last_user["content"]
        prompt.cursor_position = len(prompt.value)
        self.notify("Editando a última mensagem — Enter reenvia, Esc cancela.")

    def action_cancel(self):
        if self.edit_message_id is not None:
            self.edit_message_id = None
            self.main_screen.query_one("#prompt", PromptInput).value = ""
            return
        self.workers.cancel_group(self, "chat")

    def action_clear(self):
        self.log_view.remove_children()

    def action_palette(self):
        """Ctrl+K / /menu: paleta "▶ SELECT" com comandos, modo, foco e skills."""
        if isinstance(self.screen, (CommandPalette, ConfirmScreen)):
            return
        try:
            from services.skill_settings import list_skills
            skills = list_skills()
        except Exception as e:
            log.debug(f"Skills fora da paleta: {e}")
            skills = []
        self.push_screen(CommandPalette(palette_entries(skills, self.mode)), self._palette_chosen)

    def _palette_chosen(self, entry):
        if entry is None:
            self._focus_prompt()
            return
        if entry.kind == "command":
            self.run_command(Command(entry.value))
        elif entry.kind == "prefill":
            prompt = self.main_screen.query_one("#prompt", PromptInput)
            prompt.value = entry.value
            prompt.cursor_position = len(prompt.value)
            prompt.focus()
        elif entry.kind == "mode":
            self.mode = entry.value
        elif entry.kind == "focus":
            self._focus_action((entry.value, None), "")
        elif entry.kind == "skill":
            intent, enable = entry.value
            self._skills(f"{'on' if enable else 'off'} {intent}")
        if entry.kind != "prefill":
            self._focus_prompt()

    def _focus_prompt(self):
        if self.mode == "chat" and not isinstance(self.screen, JarvisScreen):
            self.main_screen.query_one("#prompt", PromptInput).focus()

    def action_toggle_voice(self):
        """Voz = Copilot: ^t (ou /voice) entra no Copilot ou volta ao Chat."""
        self.mode = "chat" if self.mode == "copilot" else "copilot"

    def _set_voice(self, on):
        if on == state.voice_enabled:
            return
        state.voice_enabled = on
        if on:
            self._ensure_voice_thread()
            self.add_system("Copilot por voz ativo. Diga \"Jarvis\" e peça uma ação.")
        else:
            try:
                self.voice.pause()
            except Exception as e:
                log.debug(f"Falha ao pausar o microfone: {e}")
            self.add_system("Voz desativada — de volta ao Chat.")
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
        if is_trigger(text):
            self.push_screen(HousePartyScreen())  # easter egg: não vai ao modelo
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
        elif name == "menu":
            self.action_palette()
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
            self.pending_note = None
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
        elif name == "status":
            self.push_screen(StatusScreen())
        elif name == "log":
            self.push_screen(LogScreen())
        elif name == "vault":
            self.push_screen(VaultScreen(arg), self._use_note)
        elif name == "web":
            self._web(arg)
        elif name == "gh":
            self._gh(arg)
        elif name == "briefing":
            self.tool_reply("briefing", self._make_briefing)
        elif name == "clip":
            self._clip(arg)
        elif name == "focus":
            self._focus_action(parse_focus_arg(arg), "Uso: /focus [minutos|stop|skip|status]")
        elif name == "dnd":
            self._focus_action(parse_dnd_arg(arg), "Uso: /dnd [on|off|minutos]")
        elif name == "config":
            self.push_screen(SettingsScreen())
        elif name == "clear":
            self.action_clear()
        elif name == "quit":
            self.shutdown_jarvis()

    # ------------------------------------------------------- ferramentas (/web…)
    def tool_reply(self, meta, fn, *args, speak=False):
        """Bolha do JARVIS preenchida por `fn(*args)` rodando num worker de thread."""
        view = self.add_message("assistant", "_Processando…_", meta=meta)
        self._tool_worker(view, fn, args, speak)
        return view

    @work(thread=True, group="tools")
    def _tool_worker(self, view, fn, args, speak):
        try:
            text = fn(*args) or "Nada a relatar, Senhor."
        except Exception as e:
            log.error(f"Ferramenta '{getattr(fn, '__name__', fn)}' falhou: {e}")
            text = f"**Erro:** `{e}`"
        self.call_from_thread(view.set_text, text)
        if speak and state.voice_enabled:
            self.voice.speak(text)

    def _focus_action(self, parsed, usage):
        """Pomodoro/Não Perturbe (services.focus) num worker: mexe em registro e banco."""
        if parsed is None:
            self.notify(usage, severity="warning")
            return
        action, minutes = parsed
        self.tool_reply(f"foco · {action}", self._apply_focus, action, minutes)

    def _apply_focus(self, action, minutes):
        from services.focus import focus
        text = focus.apply(action, minutes)
        self._call_ui(self._refresh_status)
        return text

    @staticmethod
    def _focus_badge():
        try:
            from services.focus import focus
            return focus.badge()
        except Exception as e:
            log.debug(f"Selo de foco indisponível: {e}")
            return ""

    def _web(self, query):
        if not query:
            self.notify("Uso: /web <pergunta>", severity="warning")
            return
        from core import web
        self.tool_reply(f"web · {query[:40]}", web.research, query)

    _GH_ALIASES = {"prs": "open_prs", "pr": "open_prs", "issues": "issues", "issue": "issues",
                   "commit": "last_commit", "ci": "ci", "actions": "ci"}

    def _gh(self, arg):
        from core import github_client
        parts = arg.split()
        action = self._GH_ALIASES.get(parts[0].lower(), None) if parts else "open_prs"
        if action is None:
            self.notify("Uso: /gh [prs|issues|commit|ci] [dono/repo]", severity="warning")
            return
        repo = parts[1] if len(parts) > 1 else None
        self.tool_reply(f"github · {parts[0] if parts else 'prs'}", github_client.run_read, action, repo)

    @staticmethod
    def _make_briefing():
        from core import briefing
        from services import user_prefs
        text = briefing.generate(include_news=user_prefs.get("briefing_news"))
        briefing.mark_ran()
        return text

    def _maybe_daily_briefing(self):
        """1º boot do dia (pref `briefing_auto`): briefing sozinho, falado se a voz estiver ligada."""
        from core import briefing
        from services import user_prefs
        if user_prefs.get("briefing_auto") and briefing.should_run_today():
            self._call_ui(lambda: self.tool_reply("briefing · automático", self._make_briefing, speak=True))

    # -------------------------------------------------------------- clipboard
    CLIP_SUGGEST_COOLDOWN = 30  # s entre avisos do monitor

    def on_pref_changed(self, key):
        """Chamado pelo /config ao mudar uma preferência."""
        if key == "clipboard_monitor":
            self._sync_clipboard_monitor()

    def _sync_clipboard_monitor(self):
        from services import user_prefs
        if user_prefs.get("clipboard_monitor"):
            if self._clip_monitor is None:
                from core.clipboard import ClipboardMonitor
                self._clip_monitor = ClipboardMonitor(self._on_clip_suggest)
            self._clip_monitor.start()
        elif self._clip_monitor is not None:
            self._clip_monitor.stop()

    def _on_clip_suggest(self, kind, _text):
        """Thread do monitor: aviso discreto, no máximo 1 a cada CLIP_SUGGEST_COOLDOWN."""
        from core.clipboard import SUGGESTION
        now = time.monotonic()
        if now - self._clip_last_suggest < self.CLIP_SUGGEST_COOLDOWN:
            return
        self._clip_last_suggest = now
        self._call_ui(self.add_system, SUGGESTION[kind])

    def _clip(self, arg):
        from core import clipboard
        arg = arg.strip().lower()
        if arg in ("hist", "historico", "histórico"):
            self.add_message("assistant", self._clip_history_markdown())
            return
        if arg and clipboard.resolve_action(None, arg) is None:
            self.notify("Uso: /clip [explicar|traduzir|resumir|hist]", severity="warning")
            return
        self.tool_reply(f"clipboard{' · ' + arg if arg else ''}", self._clip_act, arg)

    @staticmethod
    def _clip_act(arg):
        from core import clipboard
        text = clipboard.read()
        return clipboard.act(clipboard.resolve_action(clipboard.classify(text), arg), text)

    def _clip_history_markdown(self):
        history = list(self._clip_monitor.history) if self._clip_monitor else []
        if not history:
            return "Nada no histórico. Ligue o **Monitor de clipboard** no `/config`."
        names = {"code": "código", "english": "inglês", "url": "link"}
        lines = ["**Últimas cópias detectadas:**", ""]
        for kind, text in reversed(history):
            preview = " ".join(text.split())[:70].replace("`", "'")
            lines.append(f"- *{names[kind]}* · `{preview}`")
        return "\n".join(lines)

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
        self._refresh_attachbar()

    def _use_note(self, note):
        """Callback do /vault: a nota escolhida vai junto da próxima mensagem."""
        if note:
            self.pending_note = note
            self._refresh_attachbar()
            self.main_screen.query_one("#prompt", PromptInput).focus()

    def _refresh_attachbar(self):
        parts = []
        if self.pending_image:
            parts.append(f"📎 {self.pending_image['name']}")
        if self.pending_note:
            parts.append(f"▣ nota {self.pending_note['path'].rsplit('/', 1)[-1]}")
        bar = self.main_screen.query_one("#attachbar", Static)
        bar.display = bool(parts)
        if parts:
            bar.update(f" {' · '.join(parts)} — vai junto com a próxima mensagem   [dim]/detach remove[/]")

    def _with_note(self, text, note):
        """Texto que vai ao modelo: a mensagem + a nota do vault como contexto
        (prompt em backend/prompts/vault_note_context.md). O histórico guarda só a mensagem."""
        if not note:
            return text
        from core.prompts import load_prompt
        return load_prompt("vault_note_context.md", note_path=note["path"],
                           note_content=note["content"][:NOTE_CONTEXT_MAX], message=text)

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
        prompt = self.main_screen.query_one("#prompt", PromptInput)
        prompt.value = (prompt.value + " " + text).strip()
        prompt.cursor_position = len(prompt.value)
        prompt.focus()

    # ----------------------------------------------------------------- skills
    def _skills(self, arg):
        from services.skill_settings import set_enabled
        action, _, target = arg.partition(" ")
        if action in ("on", "off") and target:
            kind = set_enabled(target.strip(), action == "on")
            if kind:
                self.notify(f"{kind} '{target}' {'ativada' if action == 'on' else 'desativada'}.")
                self._refresh_counts()
                self._refresh_topbar()
            else:
                self.notify(f"Skill/categoria não encontrada: {target}", severity="error")
            return
        self.push_screen(SkillsScreen(), self._skills_closed)

    def _skills_closed(self, _result=None):
        self._refresh_counts()
        self._refresh_topbar()

    # ------------------------------------------------------------------- chat
    def send(self, text):
        image, note = self.pending_image, self.pending_note
        self.pending_image = self.pending_note = None
        self._refresh_attachbar()
        now = _now_hhmm()
        meta = now + (f" · anexo: {image['name']}" if image else "")
        meta += f" · nota: {note['path'].rsplit('/', 1)[-1]}" if note else ""
        reply = self._begin_turn(text, user_meta=meta)
        self._stream(text, image, self.mode, self.session_id, reply, self._with_note(text, note))

    def _begin_turn(self, text, user_meta):
        """Bolha do usuário + bolha vazia da resposta; marca a TUI como ocupada."""
        now = _now_hhmm()
        self.add_message("user", text, meta=user_meta)
        reply = self.add_message("assistant", "", meta=f"copilot · {now}" if self.mode == "copilot" else now)
        self.busy = True
        return reply

    @work(thread=True, exclusive=True, group="chat")
    def _stream(self, text, image, mode, session_id, reply, model_text=None):
        full = self._run_turn(text, image, mode, session_id, reply, worker=get_current_worker(),
                              model_text=model_text)
        if full == "PROTOCOL_SHUTDOWN":
            self.call_from_thread(self.shutdown_jarvis)

    def _run_turn(self, text, image, mode, session_id, reply, worker=None, on_output=None, model_text=None):
        """Roda UMA mensagem pelo brain numa thread de fundo e pinta a resposta.
        Usado pelo Chat (worker) e pelo Copilot por voz. on_output() avisa o
        1º sinal de resposta (skill roteada ou 1º trecho) — a orb passa a 'respondendo'.
        Retorna o texto final ('PROTOCOL_SHUTDOWN' se o brain pediu desligamento)."""
        full = ""
        base_meta = reply.meta
        skill = []  # intent da skill acionada (Copilot), p/ o badge no cabeçalho
        started = []

        def output_started():
            if on_output and not started:
                started.append(True)
                on_output()

        def on_route(intent):
            skill.append(intent)
            self.last_skill_turn = {"command": text, "intent": intent, "status": "run",
                                    "voice": on_output is not None, "time": _now_hhmm()}
            output_started()
            self.call_from_thread(reply.set_meta, f"{base_meta} · ▚ [{intent}] executando…")

        try:
            images, att_type, att_path = None, None, None
            if image:
                from core.uploads import save_base64_upload
                saved = save_base64_upload(image["data"], image["mime"], image["name"], kind="image")
                if saved:
                    images = [image["data"]]
                    att_type, att_path = "image", str(saved.relative_to(settings.DIR_UPLOADS))
            db.log_interaction("user", text, session_id, att_type, att_path, mode=mode)

            last_flush = 0.0
            for chunk in self._stream_fn(model_text or text, session_id, images, mode, on_route=on_route):
                if worker is not None and worker.is_cancelled:
                    full += "\n\n_(interrompido)_"
                    break
                if chunk:
                    output_started()
                full += chunk or ""
                now = time.monotonic()
                if now - last_flush >= STREAM_FLUSH_S:
                    self.call_from_thread(reply.set_text, full)
                    last_flush = now

            if full.strip() == "PROTOCOL_SHUTDOWN":
                return "PROTOCOL_SHUTDOWN"
            if not full.strip():
                full = "_Sem resposta do modelo. O Ollama está rodando?_"
            self.call_from_thread(reply.set_text, full)
            if skill:
                self.call_from_thread(reply.set_meta, f"{base_meta} · ■ [{skill[0]}] ✓")
                self._finish_skill_turn("ok", full)
            db.log_interaction("assistant", full, session_id, mode=mode)
        except Exception as e:
            log.error(f"Erro no stream do chat: {e}")
            self.call_from_thread(reply.set_text, f"**Erro:** `{e}`")
            if skill:
                self.call_from_thread(reply.set_meta, f"{base_meta} · ■ [{skill[0]}] ✗")
                self._finish_skill_turn("fail", str(e))
            full = ""
        finally:
            self.call_from_thread(self._stream_done, session_id)
        return full

    def _finish_skill_turn(self, status, result):
        turn = self.last_skill_turn
        if turn:
            self.last_skill_turn = {**turn, "status": status,
                                    "result": " ".join(str(result or "").split())[:60]}

    def _stream_done(self, session_id):
        self.busy = False
        pending = state.pending_critical_action
        if pending and pending.get("on_confirm"):
            # Skill do Copilot pediu confirmação (ex.: criar issue no GitHub)
            self._ask_pending_confirmation(pending.get("question", "Confirma a ação?"))
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
        self._ask_pending_confirmation(text)

    def _ask_pending_confirmation(self, text):
        """Abre o ConfirmScreen (30 s) se há ação crítica pendente e nenhum aberto."""
        pending = state.pending_critical_action
        if pending and not isinstance(self.screen, ConfirmScreen):
            self.main_screen.query_one("#voicebar", VoiceBar).set_awaiting(True)
            self.push_screen(ConfirmScreen(text, deadline=pending.get("timeout")), self._resolve_critical)

    def _resolve_critical(self, approved):
        self.main_screen.query_one("#voicebar", VoiceBar).set_awaiting(False)
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
        values, net_split = {}, None
        try:
            cpu = (mon.get_cpu_detailed() or {}).get("usage", 0) or 0
            ram = (mon.get_ram_usage() or {}).get("percent", 0) or 0
            gpu = (mon.get_gpu_info() or {}).get("load", 0) or 0
            values = {"CPU": cpu, "RAM": ram, "GPU": gpu}
            net_fn = getattr(mon, "get_network_speed", None)
            if callable(net_fn):
                net = net_fn() or {}
                net_split = (net.get("download_bps", 0) or 0, net.get("upload_bps", 0) or 0)
                values["REDE"] = sum(net_split)
            text = "   ".join(f"{name} {block_bar(value)} {value:.0f}%"
                              for name, value in (("CPU", cpu), ("RAM", ram), ("GPU", gpu)))
        except Exception as e:
            log.debug(f"Telemetria indisponível: {e}")
            text = "telemetria indisponível"
        self.call_from_thread(self._set_telemetry, text, values, net_split)

    def _set_telemetry(self, text, values=None, net_split=None):
        self._telemetry = text
        if net_split is not None:
            self.last_net = net_split  # (↓ B/s, ↑ B/s) p/ o /status
        for name, value in (values or {}).items():
            self.telemetry_history.setdefault(name, deque(maxlen=TELEMETRY_HISTORY)).append(value)
        self._refresh_status()

    # ----------------------------------------------------------------- health
    def _poll_health(self):
        self.run_worker(self._read_health, thread=True, group="health", exclusive=True)

    def _read_health(self):
        from core import health
        result = health.run_all()
        self.call_from_thread(self._set_health, result)

    def _set_health(self, result):
        from core.health import CHECKS, newly_failed
        for key in newly_failed(self.health, result):
            name = CHECKS.get(key, (key,))[0]
            self.notify(f"{name}: {result[key][1]}", severity="warning")
        self.health = dict(result)
        self._refresh_status()

    # ------------------------------------------------------------------ voice
    def _ensure_voice_thread(self):
        if self._voice_thread and self._voice_thread.is_alive():
            try:
                self.voice.resume()
            except Exception as e:
                log.debug(f"Falha ao retomar o microfone: {e}")
            return
        self._voice_thread = threading.Thread(target=self._voice_loop, daemon=True)
        self._voice_thread.start()

    def _listen_with_level(self):
        """voice.listen com o nível do mic indo p/ a barra de voz (se a voz
        injetada aceitar `on_level`; os fakes antigos dos testes não aceitam)."""
        try:
            accepts = "on_level" in inspect.signature(self.voice.listen).parameters
        except (TypeError, ValueError):
            accepts = False
        if not accepts:
            return self.voice.listen()
        return self.voice.listen(on_level=lambda lvl: self._call_ui(self._set_voice_level, lvl))

    def _set_voice_level(self, level):
        if not self.is_running:
            return
        self.main_screen.query_one("#voicebar", VoiceBar).set_level(level)

    def _set_orb(self, orb_state):
        self.main_screen.query_one("#copilot-hero", CopilotHero).set_state(orb_state)

    def _voice_loop(self):
        """Copilot por voz: ouve → mesmo pipeline de stream do Copilot → fala.
        Grava na sessão atual (aparece no Ctrl+O). Estados da orb:
        ouvindo (mic aberto) → pensando (comando recebido) → respondendo
        (1º trecho ou skill roteada, até o fim da fala) → ouvindo."""
        while not self._voice_stop.is_set():
            try:
                if not state.voice_enabled:
                    time.sleep(0.3)
                    continue
                self._call_ui(self._set_orb, "ouvindo")
                command = self._listen_with_level()
                if not command or not state.voice_enabled:
                    time.sleep(0.05)
                    continue
                self._call_ui(self._set_voice_level, None)  # saiu de "ouvindo": barras zeram
                self._call_ui(self._set_orb, "pensando")
                session_id = self.session_id
                reply = self._call_ui(self._begin_turn, command, f"voz · {_now_hhmm()}")
                full = self._run_turn(command, None, "copilot", session_id, reply,
                                      on_output=lambda: self._call_ui(self._set_orb, "respondendo"))
                self._call_ui(self._set_orb, "respondendo")
                self.voice.pause()
                try:
                    if full == "PROTOCOL_SHUTDOWN":
                        self.voice.speak("Desativando núcleo de força. Até logo, Senhor.")
                        self._call_ui(self.shutdown_jarvis)
                        return
                    if full:
                        self.voice.speak(full)
                finally:
                    self.voice.resume()
            except Exception as e:
                if self._voice_stop.is_set() or not self.is_running:
                    return  # app encerrado no meio do turno
                log.error(f"Erro no loop de voz: {e}")
                time.sleep(1)

    def on_unmount(self):
        self._voice_stop.set()
        if self._clip_monitor is not None:
            self._clip_monitor.stop()
        self._stop_focus()  # X do terminal/erro: notificações do Windows voltam
        self._unregister_presence()

    # ------------------------------------------------------------------- boot
    @work(thread=True, group="boot")
    def _boot_greeting(self):
        try:
            from services.focus import focus
            focus.restore_after_crash()  # caiu com o Não Perturbe ligado na última vez?
        except Exception as e:
            log.debug(f"Restauração do Não Perturbe falhou: {e}")
        try:
            from core import obsidian
            name = obsidian.get_memory("nome") or "Senhor"
        except Exception:
            name = "Senhor"
        self.call_from_thread(self.add_system, f"`[  OK  ]` Sistemas online. Bem-vindo de volta, {name}.")
        try:
            self._maybe_daily_briefing()
        except Exception as e:
            log.warning(f"Briefing automático falhou: {e}")

    def shutdown_jarvis(self):
        """Encerra com o desligamento CRT; chamado de novo (Ctrl+Q duas vezes) sai na hora."""
        if self._shutting_down:
            self._exit_now()
            return
        self._shutting_down = True
        log.info("Aplicação encerrada pela TUI.")
        self._stop_focus()
        self._unregister_presence()
        self._voice_stop.set()
        state.announce = None
        self.push_screen(ShutdownScreen(self._exit_now))

    def _stop_focus(self):
        """Fecha o Pomodoro e devolve as notificações do Windows ao sair."""
        if not self._start_services:
            return
        try:
            from services.focus import focus
            focus.stop()
        except Exception as e:
            log.debug(f"Falha ao encerrar o foco: {e}")

    def _exit_now(self):
        self._shutting_down = True
        self._voice_stop.set()
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
