"""Base das telas cheias da TUI (/status, /skills, /log…).

Mesmo esqueleto da conversa (canvas "JARVIS TUI"): barra do topo com selo,
corpo, e uma linha única com telemetria (esquerda) + atalhos (direita).
Esc volta para a conversa.
"""
from textual.app import ComposeResult
from textual.binding import Binding, BindingsMap
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Static

from frontend.widgets import StatusLine


class JarvisScreen(Screen):
    BADGE = ""
    HEADLINE = ""
    STATUS_REFRESH_S = 3.0

    BINDINGS = [Binding("escape", "close", "Voltar")]

    @classmethod
    def _merge_bindings(cls) -> BindingsMap:
        """Como no canvas, "esc Voltar" fecha o rodapé: o Textual mantém a
        posição da 1ª definição da tecla (a desta base), então movemos o Esc
        para o fim depois da mescla."""
        keys = dict(super()._merge_bindings().key_to_bindings)
        if "escape" in keys:
            keys["escape"] = keys.pop("escape")
        return BindingsMap.from_keys(keys)

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

    def status_hint(self):
        """Texto do lado esquerdo da linha de status. None = telemetria do app;
        cada tela pode trocar por uma dica própria (como no canvas)."""
        return None

    def on_mount(self):
        self.set_class(bool(getattr(self.app, "critical", False)), "-critical")
        self._refresh_statusline()
        self.set_interval(self.STATUS_REFRESH_S, self._refresh_statusline)

    def _refresh_statusline(self):
        text = self.status_hint()
        if text is None:
            status = getattr(self.app, "status_text", None)
            text = status() if callable(status) else ""
        self.query_one("#screen-status", StatusLine).update(text)
        self.set_class(bool(getattr(self.app, "critical", False)), "-critical")

    def set_info(self, text):
        self.query_one("#topbar-info", Static).update(text)

    def action_close(self):
        self.dismiss(None)
