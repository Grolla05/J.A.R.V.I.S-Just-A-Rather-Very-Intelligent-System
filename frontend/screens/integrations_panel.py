"""Cards de /config → INTEGRAÇÕES (canvas: "15 · Configurações — Integrações").

Cada card mostra LED + nome + selo de estado, a descrição, o detalhe (conta,
fonte ou o que falta configurar) e a dica de tecla. Setas andam na grade 2×N,
Enter conecta e Del desconecta — a tela dona (SettingsScreen) faz o trabalho.
Cores só no jarvis.tcss, pelas classes -on/-wait/-off/-setup.
"""
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Label

COLUMNS = 2
_STATE_CLASSES = ("-on", "-wait", "-off", "-setup")


def _integrations():
    from services import integrations
    return integrations


class IntegrationCard(Vertical, can_focus=True):
    BINDINGS = [
        Binding("enter", "connect", "Conectar"),
        Binding("delete", "disconnect", "Desconectar"),
        Binding("up", "move(-2)", "Escolher", show=False),
        Binding("down", "move(2)", "Escolher", show=False),
        Binding("left", "move(-1)", "Escolher", show=False),
        Binding("right", "move(1)", "Escolher", show=False),
    ]

    def __init__(self, integration, **kwargs):
        super().__init__(classes="int-card", **kwargs)
        self.integration = integration

    def compose(self) -> ComposeResult:
        with Horizontal(classes="int-head"):
            yield Label("■", classes="int-led")
            yield Label(self.integration.name, classes="int-name", markup=False)
            yield Label("", classes="int-badge", markup=False)
        yield Label(self.integration.desc, classes="int-desc", markup=False)
        yield Label("", classes="int-detail", markup=False)
        yield Label("", classes="int-hint", markup=False)

    def on_mount(self):
        self.refresh_state()

    def refresh_state(self):
        integrations = _integrations()
        state, detail = integrations.state_of(self.integration)
        self.state = state
        for cls in _STATE_CLASSES:
            self.remove_class(cls)
        self.add_class(f"-{state}")
        self.query_one(".int-badge", Label).update(f" {integrations.BADGES.get(state, state.upper())} ")
        self.query_one(".int-detail", Label).update(detail or "")
        self.query_one(".int-hint", Label).update(self._hint(state))

    def _hint(self, state):
        if state == "wait":
            return "conclua no navegador"
        if state == "on" and self.integration.disconnect is not None:
            return "del  Desconectar"
        if state == "setup":
            return "enter  Como configurar"
        return f"enter  {self.integration.connect_label}"

    # ---------------------------------------------------------------- ações
    def _cards(self):
        return list(self.parent.query(IntegrationCard)) if self.parent else [self]

    def action_move(self, delta):
        cards = self._cards()
        target = cards.index(self) + delta
        if 0 <= target < len(cards):
            cards[target].focus()
        elif delta in (-1, -COLUMNS) and target < 0:
            self.screen.query_one("#cfg-menu").focus()  # sai da grade pela esquerda/topo

    def action_connect(self):
        handler = getattr(self.screen, "connect_integration", None)
        if callable(handler):
            handler(self.integration.id)

    def action_disconnect(self):
        handler = getattr(self.screen, "disconnect_integration", None)
        if callable(handler):
            handler(self.integration.id)
