"""Atualização disponível (canvas: "16 · Atualização disponível").

Aparece ao abrir a TUI (boot normal, Win+J, bandeja, ou aberta pelo agente no
logon) quando o Release do GitHub é mais novo que o VERSION instalado
(`core.updater.check_available`). Orb parada no centro — sem timer: a única
animação contínua permitida é a do Copilot — e o aviso embaixo. Enter instala
(a tela fecha com True, a app pede a instalação ao agente via
`core.updater.request_install` e sai); Esc adia por 24 h (fecha com False).
Outras teclas não fazem nada, e nos primeiros GRACE_S nenhuma tecla conta:
a tela pode abrir por cima do chat enquanto o usuário digita.
"""
import time

from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label, Static

from frontend.widgets import JarvisOrb

HEADLINE = "ATUALIZAÇÃO DISPONÍVEL!!"
PROMPT = "Enter para instalar · Esc para adiar 24 h"
INSTALLING = "Instalando… o J.A.R.V.I.S fecha e volta sozinho, Senhor."


def version_line(current, latest):
    return f"instalada v{current}  ──▶  nova v{latest}"


class UpdateScreen(Screen):
    AUTO_FOCUS = None
    GRACE_S = 0.5  # teclas logo após abrir são ignoradas (o usuário podia estar digitando)

    def __init__(self, current, latest, **kwargs):
        super().__init__(**kwargs)
        self.current = current
        self.latest = latest
        self._pressed = False
        self._opened_at = time.monotonic()

    def compose(self) -> ComposeResult:
        with Horizontal(id="update-head"):
            yield Static("J.A.R.V.I.S", id="update-brand")
            yield Static("UPDATE", id="update-badge")
            yield Static("Release do GitHub", id="update-source")
        with Vertical(id="update-body"):
            with Center():
                yield JarvisOrb(id="update-orb")
            with Center():
                yield Label(HEADLINE, id="update-headline")
            with Center():
                yield Label(version_line(self.current, self.latest), id="update-versions", markup=False)
            with Center():
                yield Label("Setup baixado do Release, SHA-256 conferido antes de instalar.", classes="hint")
            with Center():
                yield Label(f"{PROMPT} ▌", id="update-prompt", markup=False)
        with Horizontal(id="update-foot"):
            yield Static("enter Instalar   esc Adiar 24 h", id="update-keys")

    def on_mount(self):
        self._opened_at = time.monotonic()

    def on_key(self, event):
        # Engole tudo: atalhos da conversa não valem por baixo desta tela
        event.stop()
        event.prevent_default()
        if self._pressed or time.monotonic() - self._opened_at < self.GRACE_S:
            return
        if event.key == "enter":
            self._pressed = True
            self.query_one("#update-prompt", Label).update(INSTALLING)
            self.dismiss(True)
        elif event.key == "escape":
            self._pressed = True
            self.dismiss(False)
