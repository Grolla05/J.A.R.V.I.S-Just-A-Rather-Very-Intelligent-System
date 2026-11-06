"""Save slots (Ctrl+O / /sessions) — canvas "11 · Histórico — save slots".

Tela cheia com um cartão por sessão numa grade de 2 colunas: número do slot,
título, ★ se fixada, "quando · N msgs · modo", a última fala do JARVIS e uma
barra do tamanho da conversa. Enter carrega, `p` fixa, Del Del apaga e `/`
abre a busca (título ou trecho da conversa). Devolve o id escolhido (ou None).
"""
import re
import time

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Label, Static

from frontend.screens.base import JarvisScreen
from frontend.widgets import format_slot_when

SLOT_FULL_AT = 50  # mensagens para a barra encher


def _plain(text):
    """Prévia em uma linha, sem marcação de Markdown."""
    return " ".join(re.sub(r"[*_`#>]", "", str(text or "")).split())


class SlotQuote(Static):
    """Última fala entre aspas, cortada na largura do cartão (fecha a aspa)."""

    def __init__(self, text, **kwargs):
        super().__init__(markup=False, **kwargs)
        self.text = text

    def render(self):
        if not self.text:
            return ""
        width = max(self.size.width, 4)
        if len(self.text) + 2 <= width:
            return f"“{self.text}”"
        return f"“{self.text[:width - 3].rstrip()}…”"


class SlotBar(Static):
    """Barra ▰ do tamanho da conversa, ocupando a largura do cartão; a parte
    vazia usa a cor de `slot-bar--empty`."""

    COMPONENT_CLASSES = {"slot-bar--empty"}

    def __init__(self, count, **kwargs):
        super().__init__(**kwargs)
        self.count = count

    def render(self):
        width = max(self.size.width, 1)
        filled = round(min(self.count, SLOT_FULL_AT) / SLOT_FULL_AT * width)
        if self.count and not filled:
            filled = 1
        empty = self.get_component_rich_style("slot-bar--empty", partial=True)
        return Text.assemble("▰" * filled, ("▰" * (width - filled), empty))


class SlotCard(Vertical, can_focus=True):
    """Cartão de um save. `-current` marca a sessão aberta."""

    def __init__(self, slot, session, current=False):
        super().__init__(classes="slot")
        self.slot = slot
        self.session = session
        self.session_id = session["id"]
        self.set_class(current, "-current")

    @property
    def title(self):
        return " ".join((self.session.get("title") or "Nova conversa").split())

    @property
    def preview(self):
        return _plain(self.session.get("last_reply") or self.session.get("last_message"))

    @property
    def meta(self):
        count = self.session.get("msg_count") or 0
        parts = [format_slot_when(self.session.get("last_active")), f"{count} msgs",
                 self.session.get("mode") or "chat"]
        return " · ".join(p for p in parts if p)

    def matches(self, query):
        query = query.strip().lower()
        return not query or query in self.title.lower() or query in self.preview.lower()

    def compose(self) -> ComposeResult:
        with Horizontal(classes="slot-head"):
            yield Label(f"{self.slot:02d}", classes="slot-badge")
            yield Label(self.title, classes="slot-title", markup=False)
            yield Label("★" if self.session.get("is_pinned") else "", classes="slot-star")
        yield Label(self.meta, classes="slot-meta", markup=False)
        yield SlotQuote(self.preview, classes="slot-quote")
        yield SlotBar(self.session.get("msg_count") or 0, classes="slot-bar")

    def on_click(self):
        self.screen.open_slot(self)


class SessionPicker(JarvisScreen):
    BADGE = "CARREGAR"
    HEADLINE = "Escolha um save"
    COLUMNS = 2
    DELETE_CONFIRM_S = 3.0

    BINDINGS = [
        Binding("enter", "open", "Carregar"),
        Binding("p", "pin", "Fixar"),
        Binding("delete", "delete", "Apagar"),
        Binding("slash", "search", "Busca"),
        Binding("escape", "back", "Voltar"),
        Binding("up", "move(-2)", show=False),
        Binding("down", "move(2)", show=False),
        Binding("left", "move(-1)", show=False),
        Binding("right", "move(1)", show=False),
    ]

    def __init__(self, sessions, current_id, service=None):
        """`service` (o módulo services.sessions) habilita p = fixar e
        Del Del = apagar; sem ele a tela só lista e carrega."""
        super().__init__()
        self._sessions = sessions
        self._current = current_id
        self._service = service
        self._pending_delete = None  # (id, instante) do 1º Del

    def body(self) -> ComposeResult:
        with VerticalScroll(id="slots-scroll"):
            yield Grid(id="slots-grid")
        with Horizontal(id="slots-search"):
            yield Label("busca ›", id="slots-search-label")
            yield Input(placeholder="trecho da conversa ou título  (/ para buscar)", id="slots-filter")

    def on_mount(self):
        super().on_mount()
        self._rebuild(focus_id=self._current)

    # --- montagem ---------------------------------------------------------
    def _cards(self, visible_only=True):
        cards = list(self.query(SlotCard))
        return [c for c in cards if c.display] if visible_only else cards

    def _rebuild(self, focus_id=None):
        grid = self.query_one("#slots-grid", Grid)
        grid.remove_children()
        cards = [SlotCard(n, s, s["id"] == self._current) for n, s in enumerate(self._sessions, start=1)]
        if cards:
            grid.mount_all(cards)
        else:
            grid.mount(Label("Nenhuma sessão salva ainda.", classes="hint"))
        self.query_one("#session-title", Static).update(
            f"{self.HEADLINE} · {len(self._sessions)} sessões")
        self.call_after_refresh(self._after_rebuild, focus_id)

    def _after_rebuild(self, focus_id):
        self._apply_filter(self.query_one("#slots-filter", Input).value)
        cards = self._cards()
        target = next((c for c in cards if c.session_id == focus_id), cards[0] if cards else None)
        if target:
            target.focus()
        else:
            self.query_one("#slots-filter", Input).focus()

    def _apply_filter(self, query):
        for card in self._cards(visible_only=False):
            card.display = card.matches(query)

    # --- foco / navegação -------------------------------------------------
    def _focused_card(self):
        return self.focused if isinstance(self.focused, SlotCard) else None

    def action_move(self, step):
        cards = self._cards()
        if not cards:
            return
        card = self._focused_card()
        if card is None:  # na busca: ↓ desce para a grade
            if step > 0:
                cards[0].focus()
            return
        index = cards.index(card) + step
        if 0 <= index < len(cards):
            cards[index].focus()
        elif step < 0 and index < 0 and step == -self.COLUMNS:
            self.query_one("#slots-filter", Input).focus()

    def action_search(self):
        self.query_one("#slots-filter", Input).focus()

    def action_back(self):
        if isinstance(self.focused, Input):
            cards = self._cards()
            if cards:
                cards[0].focus()
                return
        self.dismiss(None)

    def on_input_changed(self, event: Input.Changed):
        self._apply_filter(event.value)
        self.query_one("#slots-scroll").scroll_home(animate=False)

    def on_input_submitted(self, event: Input.Submitted):
        cards = self._cards()
        if cards:
            self.open_slot(cards[0])

    # --- ações ------------------------------------------------------------
    def open_slot(self, card):
        self.dismiss(card.session_id)

    def action_open(self):
        card = self._focused_card()
        if card:
            self.open_slot(card)

    def _reload(self, focus_id=None):
        self._sessions = self._service.get_recent_sessions(20)
        self._rebuild(focus_id=focus_id)

    def action_pin(self):
        card = self._focused_card()
        if not card or not self._service:
            return
        pinned = not card.session.get("is_pinned")
        if self._service.toggle_session_pin(card.session_id, pinned):
            self.notify("Sessão fixada." if pinned else "Sessão desafixada.")
            self._reload(focus_id=card.session_id)

    def action_delete(self):
        card = self._focused_card()
        if not card or not self._service:
            return
        session_id = card.session_id
        if session_id == self._current:
            self.notify("Não dá para apagar a sessão aberta.", severity="warning")
            return
        now = time.monotonic()
        pending = self._pending_delete
        if not pending or pending[0] != session_id or now - pending[1] > self.DELETE_CONFIRM_S:
            self._pending_delete = (session_id, now)
            self.notify("Pressione Del de novo para apagar esta sessão.", severity="warning")
            return
        self._pending_delete = None
        if self._service.delete_session(session_id):
            self.notify("Sessão apagada.")
            cards = self._cards()
            index = cards.index(card)
            neighbor = cards[index + 1] if index + 1 < len(cards) else (cards[index - 1] if index else None)
            self._reload(focus_id=neighbor.session_id if neighbor else None)
