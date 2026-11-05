"""/log — log de atividade (canvas: "9 · Log de atividade").

Lê o buffer em memória do logger (core.logger.RingBufferHandler), com filtro
por nível, pausa e a timeline do último turno do Copilot que acionou skill
(voz/texto → intent → skill → ✓/✗ → fala). Atualiza a cada 1 s enquanto
aberto; as 3 linhas mais novas ficam mais claras (fade de entrada).
"""
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Label

from frontend.screens.base import JarvisScreen

LEVELS = ("TODOS", "DEBUG", "INFO", "WARN", "ERROR")
REFRESH_S = 1.0


def filter_records(records, level):
    if level == "TODOS":
        return list(records)
    if level == "ERROR":
        return [r for r in records if r["level"] in ("ERROR", "CRITICAL")]
    return [r for r in records if r["level"] == level]


def timeline_steps(turn):
    """Passos da timeline do último turno com skill: [(rótulo, estado)],
    estado ∈ done | ok | fail | run."""
    if not turn:
        return []
    status = turn.get("status", "run")
    steps = [("VOZ" if turn.get("voice") else "TEXTO", "done"),
             (f"INTENT · {turn.get('intent', '?')}", "done"),
             ("SKILL", "done" if status != "run" else "run")]
    if status == "ok":
        steps.append(("✓ " + (turn.get("result") or "OK")[:28], "ok"))
    elif status == "fail":
        steps.append(("✗ FALHOU", "fail"))
    if turn.get("voice"):
        steps.append(("FALA", "done" if status != "run" else "run"))
    return steps


class LogLines(Widget):
    """Linhas do log pintadas com as cores do tema (component classes)."""

    COMPONENT_CLASSES = {"log--time", "log--module", "log--old", "log--mid", "log--new",
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
        for i, r in enumerate(self.records):
            age = "new" if i == n - 1 else "mid" if i >= n - 3 else "old"
            text.append(f"{r['time']}  ", self._s("time"))
            text.append(f"{r['level']:<6}", self._s(r["level"]))
            text.append(f"  {r['module'][:18]:<18}  ", self._s("module"))
            text.append(r["message"], self._s(age))
            if i < n - 1:
                text.append("\n")
        return text


class LogScreen(JarvisScreen):
    BADGE = "LOG"
    HEADLINE = "Atividade do J.A.R.V.I.S · seguindo"

    BINDINGS = [
        Binding("escape", "close", "Voltar"),
        Binding("f", "next_filter", "Filtro"),
        Binding("space", "pause", "Pausar"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.level = "TODOS"
        self.paused = False

    def body(self) -> ComposeResult:
        with Horizontal(id="log-filters"):
            for level in LEVELS:
                yield Button(level, id=f"filter-{level.lower()}", classes="log-filter")
        with Horizontal(id="log-timeline"):
            yield Label("", id="timeline-title", classes="hint")
        with VerticalScroll(id="log-scroll"):
            yield LogLines(id="log-lines")

    def on_mount(self):
        super().on_mount()
        self._mark_filters()
        self.refresh_log()
        self.set_interval(REFRESH_S, self.refresh_log)

    def _buffer(self):
        from core.logger import log
        buffer = getattr(log, "buffer", None)
        return buffer.snapshot() if buffer else []

    def refresh_log(self):
        if self.paused:
            return
        records = self._buffer()
        shown = filter_records(records, self.level)
        self.query_one("#log-lines", LogLines).set_records(shown[-300:])
        self.query_one("#log-scroll", VerticalScroll).scroll_end(animate=False)
        warns = sum(r["level"] == "WARN" for r in records)
        errors = sum(r["level"] in ("ERROR", "CRITICAL") for r in records)
        self.set_info(f"{len(records)} linhas · {warns} avisos · {errors} erros")
        self._render_timeline()

    def _render_timeline(self):
        turn = getattr(self.app, "last_skill_turn", None)
        key = repr(turn)
        if key == getattr(self, "_timeline_key", None):
            return  # nada mudou: não remonta (evita piscar a cada 1 s)
        self._timeline_key = key
        bar = self.query_one("#log-timeline", Horizontal)
        steps = timeline_steps(turn)
        title = (f'último turno com skill · "{turn["command"][:50]}"' if turn
                 else "nenhum turno com skill nesta execução")
        bar.query("Label.step, Label.wire").remove()
        self.query_one("#timeline-title", Label).update(title)
        for i, (label, kind) in enumerate(steps):
            bar.mount(Label(label, classes=f"step -{kind}"))
            if i < len(steps) - 1:
                bar.mount(Label("──", classes="wire"))

    def _mark_filters(self):
        for level in LEVELS:
            self.query_one(f"#filter-{level.lower()}", Button).set_class(level == self.level, "-active")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id and event.button.id.startswith("filter-"):
            event.stop()
            self.level = event.button.id.split("-", 1)[1].upper()
            self._mark_filters()
            self.refresh_log()

    def action_next_filter(self):
        self.level = LEVELS[(LEVELS.index(self.level) + 1) % len(LEVELS)]
        self._mark_filters()
        self.refresh_log()

    def action_pause(self):
        self.paused = not self.paused
        self.query_one("#session-title").update(
            "Atividade do J.A.R.V.I.S · " + ("pausado" if self.paused else "seguindo"))
        if not self.paused:
            self.refresh_log()
