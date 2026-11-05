"""Widgets da TUI do J.A.R.V.I.S (Textual)."""
import re
import time
from collections import deque
from datetime import date, datetime, timedelta

from rich.style import Style as RichStyle
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.style import Style
from textual.widget import Widget
from textual.widgets import Button, Footer, Input, Label, Markdown, OptionList, Static
from textual.widgets.markdown import MarkdownFence
from textual.widgets.option_list import Option

from frontend import orb, sprites

ROLE_LABEL = {"user": "você ›", "assistant": "jarvis ›", "system": "sistema ›"}
ORB_FPS = 8  # quadros/s do orb — só roda enquanto pensa ou responde
CONFIRM_SECONDS = 30  # prazo padrão do ConfirmScreen


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


class CodeFence(MarkdownFence):
    """Bloco de código com filete ciano e a linguagem no topo ("┌─ python")."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.border_title = self.lexer or "código"

    def _copy_context(self, block):
        super()._copy_context(block)
        self.border_title = self.lexer or "código"


class JarvisMarkdown(Markdown):
    BLOCKS = {**Markdown.BLOCKS, "fence": CodeFence, "code_block": CodeFence}


# Selo de skill no cabeçalho: "▚ [INTENT] executando…" / "■ [INTENT] ✓|✗"
_BADGE = re.compile(r"^(?P<head>.*?)(?P<led>[▚■]) \[(?P<intent>[A-Z0-9_]+)\] (?P<status>.+)$")
_BADGE_STATUS = {"✓": ("[ OK ]", "ok"), "✗": ("[ FAIL ]", "fail")}


class MessageView(Vertical):
    """Uma mensagem do log. Respostas do JARVIS renderizam Markdown."""

    COMPONENT_CLASSES = {"msg--ok", "msg--fail", "msg--run", "msg--skill"}

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
            yield JarvisMarkdown(self._text or "…", classes="msg-body")

    def _style(self, name):
        return Style.from_rich_style(self.get_component_rich_style(f"msg--{name}", partial=True))

    def _header(self):
        label = ROLE_LABEL.get(self.role, self.role)
        if not self._meta:
            return label
        # Content.assemble em vez de markup: o badge "[APP_CONTROL]" seria
        # lido como tag (e sumiria) — o escape do Textual não cobre MAIÚSCULAS.
        match = _BADGE.match(self._meta)
        if not match:
            return Content.assemble(label, " ", (self._meta, "dim"))
        status, kind = _BADGE_STATUS.get(match["status"].strip(), ("[ ▚▚ ]", "run"))
        led = self._style("skill" if kind == "ok" else kind)
        return Content.assemble(
            label, " ", (match["head"], "dim"),
            (match["led"], led), " ", (f"[{match['intent']}]", self._style("skill")), " ",
            (status, self._style(kind)),
        )

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


class StatusLine(Widget):
    """Lado esquerdo da linha de status. As barras de bloco (▰▱) ganham a cor
    da component class status--bar (ciano; vermelho no protocolo crítico)."""

    COMPONENT_CLASSES = {"status--bar"}
    DEFAULT_CSS = "StatusLine { width: auto; height: 1; }"

    text = reactive("", layout=True)

    def update(self, text):
        self.text = str(text)

    def render(self):
        bar = self.get_component_rich_style("status--bar", partial=True)
        out = Text(no_wrap=True, end="")
        for chunk in re.split(r"([▰▱]+)", self.text):
            out.append(chunk, bar if chunk and chunk[0] in "▰▱" else None)
        return out


class PromptInput(Input):
    """Input principal. ↑ com o campo vazio pede para editar a última mensagem."""

    BINDINGS = [Binding("up", "edit_last", "Editar última", show=False)]

    def action_edit_last(self):
        if not self.value:
            self.app.action_edit_last()


class JarvisOrb(Widget):
    """Orb pixel-art 16×16 em meio-bloco (16 colunas × 8 linhas).
    Cores vêm do jarvis.tcss (component classes orb--*). O timer só existe
    enquanto o estado é animado — em 'ouvindo' a orb fica parada."""

    COMPONENT_CLASSES = {f"orb--{code}" for code in orb.CODES}
    DEFAULT_CSS = "JarvisOrb { width: 16; height: 8; }"

    state = reactive("ouvindo")
    frame = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._timer = None

    def watch_state(self, state):
        self.frame = 0
        animated = orb.frame_count(state) > 1
        if animated and self._timer is None:
            self._timer = self.set_interval(1 / ORB_FPS, self._next_frame)
        elif not animated and self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _next_frame(self):
        self.frame = (self.frame + 1) % orb.frame_count(self.state)

    def render(self):
        return paint_grid(self, orb.frame(self.state, self.frame), "orb")


def paint_grid(widget, grid, prefix):
    """Pinta uma grade de códigos em meio-bloco; a cor de cada código vem da
    component class "<prefix>--<código>" do widget (jarvis.tcss)."""
    def color(code):
        return widget.get_component_rich_style(f"{prefix}--{code}", partial=True).color

    text = Text(no_wrap=True, end="")
    rows = orb.to_halfblocks(grid)
    for i, row in enumerate(rows):
        for char, top, bottom in row:
            if top is None:
                text.append(char)
                continue
            text.append(char, RichStyle(color=color(top), bgcolor=color(bottom) if bottom else None))
        if i < len(rows) - 1:
            text.append("\n")
    return text


class PixelSprite(Widget):
    """Sprite pixel-art genérico (frontend/sprites.py) em meio-bloco.

    `frames` é uma grade ou uma lista de grades. Com mais de um quadro e
    `animated=True`, roda a ORB_FPS; `animated=False` para o timer (nada de
    animação contínua fora de estados ativos)."""

    COMPONENT_CLASSES = {f"px--{code}" for code in sprites.CODES}
    DEFAULT_CSS = "PixelSprite { width: auto; height: auto; }"

    frame = reactive(0)
    animated = reactive(False, init=False)

    def __init__(self, frames, animated=False, **kwargs):
        super().__init__(**kwargs)
        self._frames = self._as_frames(frames)
        self._timer = None
        self._start_animated = animated

    @staticmethod
    def _as_frames(frames):
        # uma grade é lista de linhas; uma lista de quadros é lista de grades
        if frames and frames[0] and isinstance(frames[0][0], list):
            return list(frames)
        return [frames]

    def on_mount(self):
        if self._start_animated:
            self.animated = True

    def set_frames(self, frames):
        self._frames = self._as_frames(frames)
        self.frame = 0
        self.refresh(layout=True)

    def watch_animated(self, animated):
        if animated and len(self._frames) > 1 and self._timer is None:
            self._timer = self.set_interval(1 / ORB_FPS, self._next_frame)
        elif not animated and self._timer is not None:
            self._timer.stop()
            self._timer = None
            self.frame = 0

    def _next_frame(self):
        self.frame = (self.frame + 1) % len(self._frames)

    def get_content_width(self, container, viewport):
        return len(self._frames[0][0]) if self._frames[0] else 0

    def get_content_height(self, container, viewport, width):
        return (len(self._frames[0]) + 1) // 2

    def render(self):
        return paint_grid(self, self._frames[self.frame % len(self._frames)], "px")


class CopilotHero(Horizontal):
    """Boas-vindas do Copilot: orb + identificação + estado da voz."""

    def __init__(self, model="", skills=0, **kwargs):
        super().__init__(**kwargs)
        self._model = model
        self._skills = skills

    def compose(self) -> ComposeResult:
        yield JarvisOrb(id="orb")
        with Vertical(id="hero-text"):
            yield Label(Content.assemble(("J.A.R.V.I.S", "bold"), " · Copilot"), id="hero-title")
            yield Label(self._info(), id="hero-info")
            yield Label(id="hero-state")
            yield Label('Diga "Jarvis" e peça uma ação.', id="hero-hint")

    def on_mount(self):
        self.set_state(self.query_one(JarvisOrb).state)

    def _info(self):
        return f"{self._model or '?'} · {self._skills} skills de automação"

    def set_info(self, model, skills):
        self._model, self._skills = model, skills
        self.query_one("#hero-info", Label).update(self._info())

    @property
    def state(self):
        return self.query_one(JarvisOrb).state

    def set_state(self, state):
        self.query_one(JarvisOrb).state = state
        self.query_one("#hero-state", Label).update(f"▶ {orb.STATE_LABEL.get(state, state)}")


VOICE_WAVE = "▂▄█▅▇▃▁▁"


class VoiceBar(Horizontal):
    """Substitui o campo de texto no Copilot (que é só por voz)."""

    LISTENING = 'Ouvindo… diga "Jarvis" e peça uma ação'
    AWAITING = 'Aguardando sua resposta: diga "sim" ou "não"'

    WAVE_WIDTH = 24  # amostras do espectro (8 por segundo → ~3 s de histórico)
    VU_WIDTH = 15

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.levels = deque([0.0] * self.WAVE_WIDTH, maxlen=self.WAVE_WIDTH)

    def compose(self) -> ComposeResult:
        yield Static("●", id="voice-mic")
        yield Static(VOICE_WAVE, id="voice-wave")
        yield Static(self.LISTENING, id="voice-text", markup=False)
        yield Static(sprites.block_bar(0, self.VU_WIDTH, "█", "░"), id="voice-vu")
        yield Static("Esc interrompe", id="voice-hint")

    def set_level(self, level):
        """Nível real do microfone (0..1) — vem do RMS do listen.py. `None`
        zera tudo (fora do estado 'ouvindo' as barras ficam paradas em zero)."""
        if level is None:
            self.levels.extend([0.0] * self.WAVE_WIDTH)
            level = 0.0
        else:
            level = max(0.0, min(1.0, float(level)))
            self.levels.append(level)
        self.query_one("#voice-wave", Static).update(
            sprites.sparkline([v * 100 for v in self.levels], width=self.WAVE_WIDTH))
        self.query_one("#voice-vu", Static).update(
            sprites.block_bar(level * 100, self.VU_WIDTH, "█", "░"))

    def set_awaiting(self, awaiting):
        self.query_one("#voice-text", Static).update(self.AWAITING if awaiting else self.LISTENING)


class SessionPicker(ModalScreen):
    """Sessões recentes com filtro por título. Devolve o id escolhido (ou None)."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Fechar"),
        Binding("down", "focus_list", "Lista", show=False),
        Binding("p", "pin", "Fixar", show=False),
        Binding("delete", "delete", "Apagar", show=False),
    ]

    DELETE_CONFIRM_S = 3.0

    def __init__(self, sessions, current_id, service=None):
        """`service` (o módulo services.sessions) habilita p = fixar e
        Del Del = apagar; sem ele o picker só lista e abre."""
        super().__init__()
        self._sessions = sessions
        self._current = current_id
        self._service = service
        self._pending_delete = None  # (id, instante) do 1º Del

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            with Horizontal(id="picker-head"):
                yield Label("SESSÕES RECENTES", id="picker-title")
                yield Label("enter abre · esc fecha", classes="hint")
            yield Input(placeholder="filtrar: digite parte do título…", id="picker-filter")
            yield OptionList(*self._options(""), id="picker-list")
            yield Label("p fixa · Del Del apaga · /rename muda o título", classes="hint")

    def on_mount(self):
        self.query_one("#picker-filter", Input).focus()

    def _options(self, query):
        query = query.strip().lower()
        options = []
        for slot, s in enumerate(self._sessions, start=1):
            title = (s["title"] or "Nova conversa").replace("\n", " ")
            if query and query not in title.lower():
                continue
            mark = "▶" if s["id"] == self._current else " "
            pin = "★" if s["is_pinned"] else " "
            when = "fixada" if s["is_pinned"] else format_when(s.get("last_active"))
            count = s.get("msg_count") or 0
            # Barra = tamanho da conversa (1 bloco a cada 5 mensagens, até 10)
            size = sprites.block_bar(min(count, 50) * 2, 10, "▰", "▱")
            last = " ".join(str(s.get("last_message") or "").split())
            preview = f"“{last[:44]}…”" if len(last) > 44 else (f"“{last}”" if last else "")
            options.append(Option(
                f"{mark} {slot:02d} {pin} {title[:54]:<54} {when:>6}\n"
                f"       {size} {count:>3} msgs  {preview}", id=s["id"]))
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

    def _highlighted_id(self):
        option_list = self.query_one("#picker-list", OptionList)
        if option_list.highlighted is None or not option_list.option_count:
            return None
        option = option_list.get_option_at_index(option_list.highlighted)
        return None if option.disabled else option.id

    def _reload(self):
        option_list = self.query_one("#picker-list", OptionList)
        index = option_list.highlighted or 0
        self._sessions = self._service.get_recent_sessions(20)
        option_list.clear_options()
        option_list.add_options(self._options(self.query_one("#picker-filter", Input).value))
        if option_list.option_count:
            option_list.highlighted = min(index, option_list.option_count - 1)

    def action_pin(self):
        session_id = self._highlighted_id()
        if not session_id or not self._service:
            return
        current = next((s for s in self._sessions if s["id"] == session_id), None)
        pinned = not (current and current["is_pinned"])
        if self._service.toggle_session_pin(session_id, pinned):
            self.notify("Sessão fixada." if pinned else "Sessão desafixada.")
            self._reload()

    def action_delete(self):
        session_id = self._highlighted_id()
        if not session_id or not self._service:
            return
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
            self._reload()

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
        self._deadline = time.time() + CONFIRM_SECONDS if deadline is None else deadline

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm"):
            with Horizontal(id="confirm-head"):
                yield PixelSprite(sprites.sprite("alert"), id="confirm-icon")
                yield Label("AÇÃO CRÍTICA", id="confirm-title")
            yield Static(self._question, markup=False)
            yield Label(self._bar_text(), id="confirm-bar")
            yield Label(self._expiry_text(), id="confirm-expiry", classes="hint")
            with Horizontal(id="confirm-buttons"):
                yield Button("▶ s · Encerrar", id="confirm-yes")
                yield Button("n · Manter", id="confirm-no")
        # Mesma linha única da tela principal (telemetria + atalhos), mas com
        # os atalhos deste modal (s/n) — o Footer só enxerga a própria Screen.
        with Horizontal(id="confirm-statusbar", classes="statusbar"):
            yield StatusLine(id="confirm-status", classes="status-left")
            yield Footer(show_command_palette=False)

    def _status(self):
        status = getattr(self.app, "status_text", None)
        return status() if callable(status) else ""

    def _remaining(self):
        return max(0, int(round(self._deadline - time.time())))

    def _expiry_text(self):
        return f"Expira em {self._remaining()} s — sem resposta, nada é feito."

    def _bar_text(self):
        """Contagem regressiva em blocos (1 bloco por segundo, até 30)."""
        return sprites.block_bar(self._remaining() / CONFIRM_SECONDS * 100, CONFIRM_SECONDS, "█", "░")

    def on_mount(self):
        # Foco no "Manter" (padrão seguro) — e a mudança de foco é o que faz o
        # Footer do modal montar os atalhos s/n.
        self.query_one("#confirm-no", Button).focus()
        self.query_one("#confirm-status", StatusLine).update(self._status())
        self.set_interval(1, self._tick)

    def _tick(self):
        if self._remaining() <= 0:
            self.dismiss(False)
            return
        self.query_one("#confirm-expiry", Label).update(self._expiry_text())
        self.query_one("#confirm-bar", Label).update(self._bar_text())
        self.query_one("#confirm-status", StatusLine).update(self._status())

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "confirm-yes")
