"""Widgets da TUI do J.A.R.V.I.S (Textual)."""
import time
from datetime import date, datetime, timedelta

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Markdown, OptionList, Static
from textual.widgets.option_list import Option

ROLE_LABEL = {"user": "você ›", "assistant": "jarvis ›", "system": "sistema ›"}


def format_when(last_active, today=None):
    """'YYYY-MM-DD HH:MM:SS' → 'HH:MM' (hoje), 'ontem' ou 'dd/mm'."""
    try:
        moment = datetime.strptime(str(last_active)[:19], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return ""
    today = today or date.today()
    if moment.date() == today:
        return moment.strftime("%H:%M")
    if moment.date() == today - timedelta(days=1):
        return "ontem"
    return moment.strftime("%d/%m")


class MessageView(Vertical):
    """Uma mensagem do log. Respostas do JARVIS renderizam Markdown."""

    def __init__(self, role, text="", meta="", **kwargs):
        super().__init__(classes=f"msg -{role}", **kwargs)
        self.role = role
        self._text = text
        self._meta = meta

    def compose(self) -> ComposeResult:
        yield Label(self._header(), classes="msg-header")
        if self.role == "user":
            yield Static(self._text, markup=False, classes="msg-body")
        else:
            yield Markdown(self._text or "…", classes="msg-body")

    def _header(self):
        label = ROLE_LABEL.get(self.role, self.role)
        if not self._meta:
            return label
        # Content.assemble em vez de markup: o badge "[APP_CONTROL]" seria
        # lido como tag (e sumiria) — o escape do Textual não cobre MAIÚSCULAS.
        return Content.assemble(label, " ", (self._meta, "dim"))

    @property
    def text(self):
        return self._text

    @property
    def meta(self):
        return self._meta

    def set_meta(self, meta):
        self._meta = meta
        self.query_one(".msg-header", Label).update(self._header())

    def set_text(self, text):
        """Atualiza o corpo (usado no streaming). Retorna o awaitable do update."""
        self._text = text
        body = self.query_one(".msg-body")
        if isinstance(body, Markdown):
            return body.update(text or "…")
        body.update(text)
        return None


class PromptInput(Input):
    """Input principal. ↑ com o campo vazio pede para editar a última mensagem."""

    BINDINGS = [Binding("up", "edit_last", "Editar última", show=False)]

    def action_edit_last(self):
        if not self.value:
            self.app.action_edit_last()


class SessionPicker(ModalScreen):
    """Sessões recentes com filtro por título. Devolve o id escolhido (ou None)."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Fechar"),
        Binding("down", "focus_list", "Lista", show=False),
    ]

    def __init__(self, sessions, current_id):
        super().__init__()
        self._sessions = sessions
        self._current = current_id

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            with Horizontal(id="picker-head"):
                yield Label("Sessões recentes", id="picker-title")
                yield Label("enter abre · esc fecha", classes="hint")
            yield Input(placeholder="filtrar: digite parte do título…", id="picker-filter")
            yield OptionList(*self._options(""), id="picker-list")
            yield Label("/rename muda o título · /pin fixa no topo", classes="hint")

    def on_mount(self):
        self.query_one("#picker-filter", Input).focus()

    def _options(self, query):
        query = query.strip().lower()
        options = []
        for s in self._sessions:
            title = (s["title"] or "Nova conversa").replace("\n", " ")
            if query and query not in title.lower():
                continue
            mark = "●" if s["id"] == self._current else " "
            pin = "★" if s["is_pinned"] else " "
            when = "fixada" if s["is_pinned"] else format_when(s.get("last_active"))
            options.append(Option(f"{mark} {pin} {title[:58]:<58} {when:>6}", id=s["id"]))
        if not options:
            options.append(Option("Nenhuma sessão encontrada.", id="__none__", disabled=True))
        return options

    def on_input_changed(self, event: Input.Changed):
        option_list = self.query_one("#picker-list", OptionList)
        option_list.clear_options()
        option_list.add_options(self._options(event.value))
        option_list.highlighted = 0

    def on_input_submitted(self, event: Input.Submitted):
        option_list = self.query_one("#picker-list", OptionList)
        index = option_list.highlighted or 0
        if option_list.option_count:
            option = option_list.get_option_at_index(index)
            if not option.disabled:
                self.dismiss(option.id)

    def action_focus_list(self):
        self.query_one("#picker-list", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        self.dismiss(event.option.id)


class ConfirmScreen(ModalScreen):
    """Confirmação s/n de ação crítica do Copilot; expira sozinha (= não)."""

    BINDINGS = [
        Binding("s,y", "dismiss(True)", "Confirmar"),
        Binding("n,escape", "dismiss(False)", "Cancelar"),
    ]

    def __init__(self, question, deadline=None):
        super().__init__()
        self._question = question
        self._deadline = time.time() + 30 if deadline is None else deadline

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm"):
            yield Label("⚠ Ação crítica", id="confirm-title")
            yield Static(self._question, markup=False)
            yield Label(self._expiry_text(), id="confirm-expiry", classes="hint")
            with Horizontal(id="confirm-buttons"):
                yield Button("s · Encerrar", id="confirm-yes")
                yield Button("n · Manter", id="confirm-no")

    def _remaining(self):
        return max(0, int(round(self._deadline - time.time())))

    def _expiry_text(self):
        return f"Expira em {self._remaining()} s — sem resposta, nada é feito."

    def on_mount(self):
        self.set_interval(1, self._tick)

    def _tick(self):
        if self._remaining() <= 0:
            self.dismiss(False)
            return
        self.query_one("#confirm-expiry", Label).update(self._expiry_text())

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "confirm-yes")
