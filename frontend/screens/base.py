"""Base das telas cheias da TUI (/status, /skills, /log…).

Mesmo esqueleto da conversa (canvas "JARVIS TUI"): barra do topo com selo,
corpo, e uma linha única com telemetria (esquerda) + atalhos (direita).
Esc volta para a conversa.
"""
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Static

from frontend.widgets import StatusLine


class JarvisScreen(Screen):
    BADGE = ""
    HEADLINE = ""
    STATUS_REFRESH_S = 3.0

    BINDINGS = [Binding("escape", "close", "Voltar")]

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("J.A.R.V.I.S", id="brand")
            yield Static(self.BADGE, id="mode-badge")
            yield Static(self.HEADLINE, id="session-title")
            yield Static(self.info(), id="topbar-info")
        yield from self.body()
        with Horizontal(classes="statusbar"):
            yield StatusLine(id="screen-status", classes="status-left")
            yield Footer(show_command_palette=False)

    def body(self) -> ComposeResult:
        yield from ()

    def info(self):
        return ""

    def on_mount(self):
        self.set_class(bool(getattr(self.app, "critical", False)), "-critical")
        self._refresh_statusline()
        self.set_interval(self.STATUS_REFRESH_S, self._refresh_statusline)

    def _refresh_statusline(self):
        status = getattr(self.app, "status_text", None)
        self.query_one("#screen-status", StatusLine).update(status() if callable(status) else "")
        self.set_class(bool(getattr(self.app, "critical", False)), "-critical")

    def set_info(self, text):
        self.query_one("#topbar-info", Static).update(text)

    def action_close(self):
        self.dismiss(None)
