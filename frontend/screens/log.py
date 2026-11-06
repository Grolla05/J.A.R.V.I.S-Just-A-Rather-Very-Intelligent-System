"""/log — log de atividade (canvas: "9 · Log de atividade").

Lê o buffer em memória do logger (core.logger.RingBufferHandler): filtros por
nível, busca (`/`), pausa e a timeline do último turno do Copilot que acionou
skill (voz/texto → intent → skill → ✓/✗ → fala). No topo, o arquivo de log do
dia; na linha de status, linhas · avisos · erros. Atualiza a cada 1 s enquanto
aberto; as 3 linhas mais novas ficam mais claras e erros ganham fundo vermelho.
"""
import re
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static

from frontend.screens.base import JarvisScreen

LEVELS = ("TODOS", "DEBUG", "INFO", "WARN", "ERROR")
REFRESH_S = 1.0
MODULE_WIDTH = 22
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Emojis dos logs (✅ 🧠 🔥 ⚠️…) ocupam 2 células e fogem do visual 16-bit
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-⛿✅❌✨⭐⏳️‍]")


def clean_message(message):
    return " ".join(_EMOJI.sub("", str(message or "")).split())


def filter_records(records, level, query=""):
    if level == "TODOS":
        shown = list(records)
    elif level == "ERROR":
        shown = [r for r in records if r["level"] in ("ERROR", "CRITICAL")]
    else:
        shown = [r for r in records if r["level"] == level]
    query = (query or "").strip().lower()
    if query:
        shown = [r for r in shown if query in r["message"].lower() or query in r["module"].lower()]
    return shown


def count_text(records):
    """'1.204 linhas · 3 avisos · 1 erro' (pt-BR, com singular)."""
    def plural(n, one, many):
        return f"{n:,}".replace(",", ".") + " " + (one if n == 1 else many)
    warns = sum(r["level"] == "WARN" for r in records)
    errors = sum(r["level"] in ("ERROR", "CRITICAL") for r in records)
    return " · ".join((plural(len(records), "linha", "linhas"), plural(warns, "aviso", "avisos"),
                       plural(errors, "erro", "erros")))


def log_title(file_path):
    """Caminho do log do dia relativo à raiz do projeto (canvas: backend/logs/…)."""
    if not file_path:
        return "Atividade do J.A.R.V.I.S"
    path = Path(file_path)
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def timeline_steps(turn):
    """Passos da timeline do último turno com skill: [(rótulo, estado)],
    estado ∈ done | ok | fail | run | speech."""
    if not turn:
        return []
    status = turn.get("status", "run")
    steps = [("VOZ" if turn.get("voice") else "TEXTO", "done"),
             (f"INTENT · {turn.get('intent', '?')}", "done"),
             ("SKILL", "done" if status != "run" else "run")]
    if status == "ok":
        steps.append(("✓ " + clean_message(turn.get("result") or "OK")[:28].upper(), "ok"))
    elif status == "fail":
        steps.append(("✗ FALHOU", "fail"))
    if turn.get("voice"):
        steps.append(("FALA", "speech" if status != "run" else "run"))
    return steps


class LogLines(Widget):
    """Linhas do log pintadas com as cores do tema (component classes)."""

    COMPONENT_CLASSES = {"log--time", "log--module", "log--old", "log--mid", "log--new", "log--error-row",
                         "log--DEBUG", "log--INFO", "log--WARN", "log--ERROR", "log--CRITICAL"}
    DEFAULT_CSS = "LogLines { height: auto; width: 1fr; }"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.records = []

    def set_records(self, records):
        self.records = records
        self.refresh(layout=True)

    def get_content_height(self, container, viewport, width):
        return max(1, len(self.records))

    def _s(self, name):
        return self.get_component_rich_style(f"log--{name}", partial=True)

    def render(self):
        text = Text(no_wrap=True, overflow="ellipsis", end="")
        n = len(self.records)
        if not n:
            text.append("Nenhum registro ainda.", self._s("old"))
            return text
        width = self.size.width
        for i, r in enumerate(self.records):
            age = "new" if i == n - 1 else "mid" if i >= n - 3 else "old"
            line = Text(no_wrap=True, end="")
            line.append(f"{r['time']:<12}  ", self._s("time"))
            line.append(f"{r['level']:<6}", self._s(r["level"]))
            line.append(f"  {r['module'][:MODULE_WIDTH]:<{MODULE_WIDTH}}  ", self._s("module"))
            line.append(clean_message(r["message"]), self._s(age))
            if r["level"] in ("ERROR", "CRITICAL"):
                if width > 0:
                    line.truncate(width, pad=True)
                line.stylize(self._s("error-row"))
            text.append_text(line)
            if i < n - 1:
                text.append("\n")
        return text


class LogScreen(JarvisScreen):
    BADGE = "LOG"

    BINDINGS = [
        Binding("f", "next_filter", "Filtro"),
        Binding("slash", "search", "Busca"),
        Binding("space", "pause", "Pausar"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.level = "TODOS"
        self.query_text = ""
        self.paused = False
        self._counts = ""

    @property
    def HEADLINE(self):  # noqa: N802 — sobrescreve o atributo da base
        from core.logger import log
        return log_title(getattr(log, "file_path", None))

    def body(self) -> ComposeResult:
        with Horizontal(id="log-filters"):
            for level in LEVELS:
                yield Button(level, id=f"filter-{level.lower()}", classes="log-filter")
        with Vertical(id="log-timeline"):
            yield Label("", id="timeline-title", classes="hint")
            yield Horizontal(id="timeline-steps")
        yield Input(placeholder="buscar no log (Enter mantém · Esc limpa)", id="log-search")
        with VerticalScroll(id="log-scroll"):
            yield LogLines(id="log-lines")

    def status_hint(self):
        return self._counts

    def on_mount(self):
        super().on_mount()
        self.query_one("#log-search", Input).display = False
        self._mark_filters()
        self._set_title()
        self.refresh_log()
        self.set_interval(REFRESH_S, self.refresh_log)

    def _set_title(self):
        state = "pausado" if self.paused else "seguindo"
        search = f" · busca: {self.query_text}" if self.query_text else ""
        self.query_one("#session-title", Static).update(f"{self.HEADLINE} · {state}{search}")

    def _buffer(self):
        from core.logger import log
        buffer = getattr(log, "buffer", None)
        return buffer.snapshot() if buffer else []

    def refresh_log(self, force=False):
        if self.paused and not force:
            return
        records = self._buffer()
        shown = filter_records(records, self.level, self.query_text)
        self.query_one("#log-lines", LogLines).set_records(shown[-300:])
        self.query_one("#log-scroll", VerticalScroll).scroll_end(animate=False)
        self._counts = count_text(records)
        self._refresh_statusline()
        self._render_timeline()

    def _render_timeline(self):
        turn = getattr(self.app, "last_skill_turn", None)
        key = repr(turn)
        if key == getattr(self, "_timeline_key", None):
            return  # nada mudou: não remonta (evita piscar a cada 1 s)
        self._timeline_key = key
        bar = self.query_one("#timeline-steps", Horizontal)
        steps = timeline_steps(turn)
        if turn:
            who = "do Copilot" if turn.get("voice") else "com skill"
            title = f'último turno {who} · "{turn["command"][:50]}"'
        else:
            title = "nenhum turno com skill nesta execução"
        bar.remove_children()
        self.query_one("#timeline-title", Label).update(title)
        bar.display = bool(steps)
        for i, (label, kind) in enumerate(steps):
            bar.mount(Label(label, classes=f"step -{kind}", markup=False))
            if i < len(steps) - 1:
                bar.mount(Label("────", classes="wire"))

    def _mark_filters(self):
        for level in LEVELS:
            self.query_one(f"#filter-{level.lower()}", Button).set_class(level == self.level, "-active")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id and event.button.id.startswith("filter-"):
            event.stop()
            self.level = event.button.id.split("-", 1)[1].upper()
            self._mark_filters()
            self.refresh_log(force=True)

    def action_next_filter(self):
        self.level = LEVELS[(LEVELS.index(self.level) + 1) % len(LEVELS)]
        self._mark_filters()
        self.refresh_log(force=True)

    # --- busca ------------------------------------------------------------
    def action_search(self):
        search = self.query_one("#log-search", Input)
        search.display = True
        search.focus()

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "log-search":
            self.query_text = event.value
            self._set_title()
            self.refresh_log(force=True)

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "log-search":
            event.input.display = bool(self.query_text)
            self.query_one("#log-scroll").focus()

    def action_close(self):
        search = self.query_one("#log-search", Input)
        if search.has_focus or self.query_text:
            search.value = ""  # dispara Input.Changed → limpa a busca
            search.display = False
            self.query_one("#log-scroll").focus()
            return
        super().action_close()

    def action_pause(self):
        self.paused = not self.paused
        self._set_title()
        if not self.paused:
            self.refresh_log()
