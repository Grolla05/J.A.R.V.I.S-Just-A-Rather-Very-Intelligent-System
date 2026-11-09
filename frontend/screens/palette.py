"""Ctrl+K — paleta de comandos estilo seletor de cartucho ("▶ SELECT").

Moldura centralizada sobre a conversa: filtro no topo, lista agrupada
(COMANDOS, MODO, FOCO, SKILLS) com busca fuzzy (frontend.commands) e cursor ▶.
Enter executa, ↑↓ navegam, Esc fecha. O dismiss devolve a PaletteEntry
escolhida (ou None) e o JarvisApp despacha.
"""
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option

from frontend.commands import filter_entries
from frontend.screens.skills import glyph_for

_GROUP_GLYPH = {"COMANDOS": "›", "MODO": "⇄", "FOCO": "◷"}
LABEL_WIDTH = 26


def entry_glyph(entry):
    return glyph_for(entry.label) if entry.group == "SKILLS" else _GROUP_GLYPH.get(entry.group, "◆")


def entry_prompt(entry):
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append(f"{entry_glyph(entry)} ", style="bold")
    text.append(entry.label[:LABEL_WIDTH].ljust(LABEL_WIDTH), style="bold")
    text.append(f" {entry.group.lower():<8} ", style="dim")
    text.append(entry.desc, style="dim")
    return text


class CommandPalette(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Fechar"),
        Binding("down", "cursor(1)", show=False, priority=True),
        Binding("up", "cursor(-1)", show=False, priority=True),
    ]

    def __init__(self, entries):
        super().__init__()
        self.entries = list(entries)
        self.matches = list(self.entries)

    def compose(self) -> ComposeResult:
        with Vertical(id="palette"):
            yield Label("▶ SELECT", id="palette-title")
            yield Input(placeholder="buscar comando, skill ou ação…", id="palette-filter")
            yield OptionList(id="palette-list")
            yield Label("↑↓ navega · Enter executa · Esc fecha", id="palette-hint", classes="hint")

    def on_mount(self):
        self._fill()
        self.query_one("#palette-filter", Input).focus()

    def _fill(self):
        options = self.query_one("#palette-list", OptionList)
        options.clear_options()
        options.add_options([Option(entry_prompt(e), id=str(i)) for i, e in enumerate(self.matches)])
        if self.matches:
            options.highlighted = 0

    def on_input_changed(self, event: Input.Changed):
        self.matches = filter_entries(self.entries, event.value)
        self._fill()

    def action_cursor(self, step):
        options = self.query_one("#palette-list", OptionList)
        if not self.matches:
            return
        current = options.highlighted or 0
        options.highlighted = (current + step) % len(self.matches)

    def _choose(self, index):
        if index is not None and 0 <= index < len(self.matches):
            self.dismiss(self.matches[index])

    def on_input_submitted(self, event: Input.Submitted):
        event.stop()
        self._choose(self.query_one("#palette-list", OptionList).highlighted)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        event.stop()
        self._choose(event.option_index)
