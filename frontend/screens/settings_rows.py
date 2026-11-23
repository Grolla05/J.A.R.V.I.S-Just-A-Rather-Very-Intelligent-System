"""Peças do /config (canvas "10 · Configurações — Rotinas (seções)").

Lógica pura (seções, rótulos curtos, ajuda, montagem de uma linha) + os
widgets PrefRow (uma preferência: ▌ nome ◀ valor ▶ pontos, com a ajuda ↳ sob a
linha em foco) e QuipLine (fala do JARVIS digitando). As animações só rodam
por evento — trocar valor, falar — e param sozinhas: nada de timer contínuo.
"""
from dataclasses import dataclass

from rich.text import Text
from textual.binding import Binding
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

# grupo -> (ícone, subtítulo)
GROUP_META = {
    "VOZ": ("♪", "como o JARVIS fala com você"),
    "MICROFONE": ("◉", "como o JARVIS te escuta"),
    "ROTINAS": ("↻", "o que o JARVIS faz sozinho, sem você pedir"),
    "INTEGRAÇÕES": ("⇄", "contas conectadas pelo navegador"),
    "SISTEMA": ("⚙", "Windows, agente e atualizações"),
    "MODELO": ("◆", "cérebro local no Ollama"),
    "SOBRE": ("i", "versão e ambiente"),
}


@dataclass(frozen=True)
class Section:
    icon: str
    title: str
    keys: tuple
    hint: str
    column: int = 0


# Seções de cada grupo (cards). Duas colunas só onde há muitas opções.
SECTIONS = {
    "VOZ": (Section("♪", "FALA", ("tts_voice", "tts_rate", "tts_volume"),
                    "edge-tts neural · sem internet cai no pyttsx3"),),
    "MICROFONE": (Section("◉", "ESCUTA", ("mic_threshold", "attention_window"),
                          "vale na próxima vez que a voz for ligada"),),
    "ROTINAS": (
        Section("☀", "BRIEFING", ("briefing_auto", "briefing_news", "news_ai"),
                "/briefing força a qualquer hora · fontes em SISTEMA"),
        Section("✎", "ASSISTENTE", ("clipboard_monitor", "auto_insights"),
                "/clip sugere ações · /ideia anota na hora"),
        Section("⛨", "SEGURANÇA", ("net_monitor",), "/rede varre o perímetro na hora"),
        Section("◷", "AGENDA", ("commute_alert", "event_reminders", "reminder_lead", "reminder_final"),
                "aviso de saída usa /rota casa|trabalho", 1),
        Section("☾", "SILÊNCIO & PALCO", ("dnd_auto_meeting", "dnd_auto_fullscreen",
                                          "presentation_auto", "presentation_open"),
                "alertas críticos sempre passam", 1),
    ),
    "SISTEMA": (Section("⚙", "INICIALIZAÇÃO", ("autostart", "agent", "autoupdate"),
                        "fechar a TUI não fecha o agente da bandeja"),),
}

# Rótulos curtos: o título da seção já dá o contexto ("SILÊNCIO & PALCO › Em reunião")
SHORT_LABELS = {
    "mic_threshold": "Sensibilidade",
    "briefing_auto": "No 1º boot do dia",
    "briefing_news": "Com manchetes",
    "news_ai": "Manchetes pela IA",
    "event_reminders": "Lembretes",
    "reminder_lead": "Antecedência",
    "dnd_auto_meeting": "Em reunião",
    "dnd_auto_fullscreen": "Em tela cheia",
    "presentation_auto": "Apresentação auto",
    "presentation_open": "PowerPoint aberto",
}

# Ajuda da linha em foco (↳). Texto de UI, não prompt do LLM.
HELP = {
    "tts_voice": "Voz neural usada nas respostas faladas.",
    "tts_rate": "Mais rápido ou mais devagar que o normal.",
    "tts_volume": "Volume da fala; o do Windows continua valendo.",
    "mic_threshold": "Energia mínima para contar como fala; automática calibra sozinha.",
    "attention_window": 'Depois de um pedido, ouço sem precisar do "Jarvis".',
    "briefing_auto": "Resumo do dia na 1ª abertura de cada dia.",
    "briefing_news": "Inclui manchetes das fontes de SISTEMA.",
    "news_ai": "O modelo escolhe a manchete que importa em cada fonte.",
    "clipboard_monitor": "Sugere ações para o que você copia; nada vai para o log.",
    "auto_insights": "Ideias da conversa vão para Brainstorms no vault.",
    "commute_alert": "Clima, trânsito e 1º compromisso nesse horário, em dias úteis.",
    "event_reminders": "Aviso antes dos eventos do Google Agenda.",
    "reminder_lead": "Quanto antes de cada evento do Google Agenda eu aviso.",
    "reminder_final": "Último aviso; com rota conhecida vira aviso de saída.",
    "net_monitor": "Avisa porta nova, programa estranho ou aparelho intruso.",
    "dnd_auto_meeting": "Reunião na agenda: alertas comuns ficam para depois.",
    "dnd_auto_fullscreen": "App em tela cheia: alertas comuns ficam para depois.",
    "presentation_auto": "Slides em tela cheia fecham o mic e calam a voz.",
    "presentation_open": "PowerPoint aberto já conta como apresentação.",
    "autostart": "Sobe o agente junto com o Windows.",
    "agent": "Agente da bandeja: o atalho global abre o JARVIS de qualquer lugar.",
    "autoupdate": "No logon confere os Releases do GitHub e instala sozinho.",
}

VALUE_W = 11   # coluna do valor ("limiar 1200", "○ PARADO")
DOTS_W = 9     # até 9 opções (horários do aviso de saída)
FIXED_W = 2 + 1 + 2 + VALUE_W + 2 + 1 + DOTS_W  # tudo menos o nome
FLASH_FRAMES = 2
FLASH_S = 0.1
QUIP_CHARS = 30                 # caracteres por quadro da fala
QUIP_FPS = 8


@dataclass(frozen=True)
class RowState:
    """Uma linha do /config já resolvida (valor exibido, tipo, posição)."""
    key: str
    name: str
    value: str
    toggle: bool = False
    on: bool = False
    pos: int = 0
    total: int = 1

    @property
    def active(self):
        return self.on if self.toggle else self.value != "desligado"


def short_label(key, label):
    return SHORT_LABELS.get(key, label)


def compact_value(text):
    """'120 min antes' → '120 min' (a coluna do valor é estreita)."""
    return str(text).removesuffix(" antes")


def toggle_text(on, on_text="ON", off_text="OFF"):
    return f"● {on_text}" if on else f"○ {off_text}"


def fit(text, width):
    text = str(text)
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


def row_segments(row, width, focused=False, flash=0, on_text="ON", off_text="OFF"):
    """Segmentos (texto, estilo) de uma linha com `width` colunas. Estilos:
    bar, name, arrow, on, off, value, muted, flash, dot-past/now/next, pad.
    `flash` > 0 = quadros da animação de troca de valor."""
    name_w = max(4, width - FIXED_W)
    segs = [("▌" if focused else " ", "bar"), (" ", "pad"), (fit(row.name, name_w).ljust(name_w), "name"), (" ", "pad")]
    arrow = "arrow" if focused else "pad"
    segs.append(("◀ " if focused else "  ", arrow))
    if row.toggle:
        if flash >= FLASH_FRAMES:  # 1º quadro: o selo desliza ○──●
            text, style = "○──●" if row.on else "●──○", "flash"
        else:
            text, style = toggle_text(row.on, on_text, off_text), ("on" if row.on else "off")
            if flash:
                style = "flash"
    else:
        text = compact_value(row.value)
        style = "flash" if flash else ("muted" if row.value == "desligado" else "value")
    segs.append((fit(text, VALUE_W).center(VALUE_W), style))
    segs.append((" ▶" if focused else "  ", arrow))
    segs.append((" ", "pad"))
    dots = []
    if not row.toggle and row.total > 1:
        for i in range(min(row.total, DOTS_W)):
            dots.append(("▮", "dot-now" if i == row.pos else "dot-past" if i < row.pos else "dot-next"))
    segs.append((" " * (DOTS_W - len(dots)), "pad"))
    segs.extend(dots)
    return segs


def summary(rows):
    """(ativas, total) de uma lista de RowState."""
    rows = list(rows)
    return sum(1 for r in rows if r.active), len(rows)


def typed(text, frame, chars=QUIP_CHARS):
    """Trecho da fala visível no quadro `frame` (máquina de escrever)."""
    return str(text)[: max(0, frame) * chars]


class PrefRow(Widget, can_focus=True):
    """Uma preferência. ↑↓ andam entre as linhas; ←→ ajustam (a tela faz).
    Em foco: barra ciano, fundo de seleção, setas e a ajuda ↳ embaixo."""

    COMPONENT_CLASSES = {
        "pref--bar", "pref--name", "pref--arrow", "pref--on", "pref--off", "pref--value", "pref--muted",
        "pref--flash", "pref--dot-past", "pref--dot-now", "pref--dot-next", "pref--focus", "pref--help",
    }
    DEFAULT_CSS = "PrefRow { height: auto; width: 1fr; background: transparent; }"
    # As setas ficam na própria linha: o VerticalScroll do painel (ancestral)
    # tem bindings de rolagem nelas e esconderia os atalhos do rodapé.
    BINDINGS = [
        Binding("up", "move(-1)", "Escolher", key_display="↑↓"),
        Binding("down", "move(1)", "Escolher", show=False),
        Binding("left", "adjust(-1)", "Ajustar", show=False),
        Binding("right", "adjust(1)", "Ajustar", key_display="←→"),
    ]

    flash = reactive(0)

    def __init__(self, row, help_text="", on_text="ON", off_text="OFF", **kwargs):
        super().__init__(**kwargs)
        self.row = row
        self.help_text = help_text
        self.on_text, self.off_text = on_text, off_text
        self._flash_timer = None

    def set_row(self, row, on_text=None, off_text=None, animate=False):
        changed = row != self.row
        self.row = row
        if on_text is not None:
            self.on_text, self.off_text = on_text, off_text
        if animate and changed:
            self.start_flash()
        self.refresh()

    def start_flash(self):
        if self._flash_timer is not None:
            self._flash_timer.stop()
        self.flash = FLASH_FRAMES
        self._flash_timer = self.set_interval(FLASH_S, self._next_flash)

    def _next_flash(self):
        self.flash = max(0, self.flash - 1)
        if not self.flash and self._flash_timer is not None:
            self._flash_timer.stop()
            self._flash_timer = None

    def watch_flash(self, _flash):
        self.refresh()

    def on_focus(self):
        self.refresh(layout=True)

    def on_blur(self):
        self.refresh(layout=True)

    def get_content_height(self, container, viewport, width):
        return 2 if self.has_focus and self.help_text else 1

    def plain(self):
        """Texto da linha sem estilo (testes e leitores)."""
        return "".join(t for t, _ in row_segments(self.row, max(self.size.width, FIXED_W + 20),
                                                    self.has_focus, 0, self.on_text, self.off_text))

    def render(self):
        width = self.size.width or (FIXED_W + 20)
        focused = self.has_focus
        base = self.get_component_rich_style("pref--focus", partial=True) if focused else None
        text = Text(no_wrap=True, end="")
        for chunk, style in row_segments(self.row, width, focused, self.flash, self.on_text, self.off_text):
            rich = None if style == "pad" else self.get_component_rich_style(f"pref--{style}", partial=True)
            if base is not None:
                rich = base + rich if rich is not None else base
            text.append(chunk, rich)
        used = text.cell_len
        if used < width:
            text.append(" " * (width - used), base)
        if focused and self.help_text:
            help_style = self.get_component_rich_style("pref--help", partial=True)
            text.append("\n")
            text.append(fit(f"    ↳ {self.help_text}", width).ljust(width), help_style)
        return text

    def action_move(self, delta):
        handler = getattr(self.screen, "move_row", None)
        if callable(handler):
            handler(self, delta)

    def action_adjust(self, direction):
        handler = getattr(self.screen, "action_adjust", None)
        if callable(handler):
            handler(direction)


class QuipLine(Static):
    """Fala do JARVIS no rodapé do /config, digitada QUIP_CHARS por quadro
    com o cursor ▌ no fim. O timer some quando a frase termina."""

    COMPONENT_CLASSES = {"quip--cursor"}

    def __init__(self, text="", **kwargs):
        super().__init__("", **kwargs)
        self._text = text
        self._frame = 0
        self._timer = None

    @property
    def text(self):
        return self._text

    def on_mount(self):
        self._paint(len(self._text))

    def say(self, text):
        self._text = str(text)
        self._frame = 0
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_interval(1 / QUIP_FPS, self._tick)
        self._tick()

    def _tick(self):
        self._frame += 1
        shown = typed(self._text, self._frame)
        self._paint(len(shown))
        if len(shown) >= len(self._text) and self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _paint(self, n):
        out = Text(self._text[:n])
        out.append("▌", self.get_component_rich_style("quip--cursor", partial=True))
        self.update(out)
