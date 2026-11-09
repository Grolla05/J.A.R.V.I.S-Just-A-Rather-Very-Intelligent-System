"""/config — painel de ajustes estilo RPG (canvas: "10 · Configurações").

Menu lateral com cursor ▶ (VOZ, MICROFONE, ROTINAS, SISTEMA, MODELO, SOBRE), opções ◀ ▶ com
barra de blocos e uma caixa de diálogo com o rosto pixel-art do JARVIS
comentando a escolha. Valores persistem em services.user_prefs (tabela config).
"""
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from core import settings
from frontend import sprites
from frontend.screens.base import JarvisScreen
from frontend.widgets import PixelSprite

MENU = ("VOZ", "MICROFONE", "ROTINAS", "SISTEMA", "MODELO", "SOBRE")

# SISTEMA não mora no user_prefs: o estado vive no registro (Run) e no mutex do agente.
SYSTEM_KEYS = ("autostart", "agent")

# Fala do JARVIS ao mexer em cada preferência (texto de UI, não prompt do LLM)
QUIPS = {
    "tts_voice": "Nova voz carregada, Senhor. Espero que combine com o terno.",
    "tts_rate": "Velocidade ajustada. Prometo não atropelar as palavras.",
    "tts_volume": "Volume ajustado. Os vizinhos agradecem.",
    "mic_threshold": "Sensibilidade nova. Vale na próxima vez que eu abrir o microfone.",
    "attention_window": "Fico atento por esse tempo depois de cada pedido.",
    "briefing_auto": "Briefing matinal ajustado. Prometo ser breve. Quase sempre.",
    "briefing_news": "Manchetes ajustadas. Filtrar o drama fica por sua conta.",
    "clipboard_monitor": "De olho no clipboard. Só sugiro — não leio seus segredos em voz alta.",
    "autostart": "Anotado. Eu acordo junto com o Windows — café por sua conta.",
    "agent": "Agente em 2º plano. Win+J me chama de qualquer lugar.",
    "agent_running": "Já estou de plantão. Para me dispensar, use o ícone da bandeja.",
}
IDLE = "Escolha uma opção com ↑↓ e ajuste com ←→, Senhor."


class SettingsScreen(JarvisScreen):
    BADGE = "CONFIG"
    HEADLINE = "Painel de ajustes"

    BINDINGS = [
        Binding("escape", "close", "Voltar"),
        Binding("left", "adjust(-1)", "Ajustar", show=False),
        Binding("right", "adjust(1)", "Ajustar"),
        Binding("tab", "switch_panel", "Menu/opções", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.group = MENU[0]

    def body(self) -> ComposeResult:
        with Horizontal(id="cfg-body"):
            with Vertical(id="cfg-menu-box"):
                yield Label("MENU", classes="hint", id="cfg-menu-title")
                yield OptionList(*[Option(self._menu_label(g), id=g) for g in MENU], id="cfg-menu")
            with Vertical(id="cfg-main"):
                with Vertical(id="cfg-panel"):
                    yield Label(self.group, id="cfg-group")
                    yield OptionList(id="cfg-options")
                    yield Static("", id="cfg-info", markup=False)
                with Horizontal(id="cfg-dialog"):
                    yield PixelSprite(sprites.sprite("face"), id="cfg-face")
                    with Vertical(id="cfg-dialog-text"):
                        yield Label("JARVIS", id="cfg-speaker")
                        yield Label(IDLE + " ▼", id="cfg-quip")

    def _menu_label(self, group):
        return f"{'▶' if group == self.group else ' '} {group}"

    def on_mount(self):
        super().on_mount()
        self._render_group()
        self.query_one("#cfg-menu", OptionList).focus()

    # ------------------------------------------------------------- render
    def _prefs(self):
        from services import user_prefs
        return user_prefs

    def _keys(self):
        if self.group == "SISTEMA":
            return SYSTEM_KEYS
        return self._prefs().GROUPS.get(self.group, ())

    @staticmethod
    def _system_value(key):
        from core import autostart
        if key == "autostart":
            on = autostart.is_enabled()
            return "Iniciar com o Windows", "ligado" if on else "desligado", on
        on = autostart.is_agent_running()
        return "Agente em 2º plano", "rodando" if on else "parado", on

    def _option_text(self, key):
        if key in SYSTEM_KEYS:
            label, value, on = self._system_value(key)
            bar = sprites.block_bar(100 if on else 0, 10, "▰", "▱")
            return f"{label:<22} ◀ {value:^14} ▶  {bar}"
        p = self._prefs()
        value = p.display(key)
        bar = sprites.block_bar(p.level(key) * 100, 10, "▰", "▱")
        return f"{p.label(key):<22} ◀ {value:^14} ▶  {bar}"

    def _render_group(self):
        menu = self.query_one("#cfg-menu", OptionList)
        for i, group in enumerate(MENU):
            menu.replace_option_prompt_at_index(i, self._menu_label(group))
        self.query_one("#cfg-group", Label).update(self.group)
        options = self.query_one("#cfg-options", OptionList)
        index = options.highlighted or 0
        options.clear_options()
        keys = self._keys()
        for key in keys:
            options.add_option(Option(self._option_text(key), id=key))
        options.display = bool(keys)
        if keys:
            options.highlighted = min(index, len(keys) - 1)
        self.query_one("#cfg-info", Static).update(self._info_text())

    def _info_text(self):
        if self.group == "MODELO":
            return (f"Modelo        {settings.OLLAMA_MODEL}\n"
                    f"Host          {settings.OLLAMA_HOST}\n"
                    f"Contexto      {settings.OLLAMA_NUM_CTX or 'padrão do Ollama'}\n"
                    f"Camadas GPU   {settings.OLLAMA_NUM_GPU if settings.OLLAMA_NUM_GPU is not None else 'padrão'}\n\n"
                    "Troque no .env (OLLAMA_MODEL) e reinicie.")
        if self.group == "SOBRE":
            return (f"{settings.PROJECT_NAME} v{settings.VERSION}\n"
                    "TUI Textual · Ollama local · SQLite · Obsidian\n"
                    f"Idioma        {settings.DEFAULT_LANGUAGE}\n"
                    f"Microfone     índice {settings.MIC_INDEX}")
        if self.group == "MICROFONE":
            return "Mudanças no microfone valem na próxima vez que a voz for ligada."
        if self.group == "SISTEMA":
            hotkey = settings.GLOBAL_HOTKEY or "desligado (GLOBAL_HOTKEY vazio)"
            return (f"Atalho global  {hotkey}\n"
                    "O agente fica na bandeja: fechar a TUI não o fecha, e o atalho\n"
                    "reabre o JARVIS direto no Copilot.")
        if self.group == "ROTINAS":
            return ("Briefing: /briefing força a qualquer hora. Manchetes usam a busca web.\n"
                    "Clipboard: só sugere (/clip); nada copiado vai para o log.")
        return ""

    # -------------------------------------------------------------- eventos
    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted):
        if event.option_list.id == "cfg-menu" and event.option.id != self.group:
            self.group = event.option.id
            self._render_group()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        if event.option_list.id == "cfg-menu":
            options = self.query_one("#cfg-options", OptionList)
            if options.display:
                options.focus()

    def action_switch_panel(self):
        menu = self.query_one("#cfg-menu", OptionList)
        options = self.query_one("#cfg-options", OptionList)
        (options if menu.has_focus and options.display else menu).focus()

    def action_adjust(self, direction):
        options = self.query_one("#cfg-options", OptionList)
        if not options.display or options.highlighted is None:
            return
        key = options.get_option_at_index(options.highlighted).id
        if key in SYSTEM_KEYS:
            self._adjust_system(key)
            return
        self._prefs().step(key, direction)
        hook = getattr(self.app, "on_pref_changed", None)
        if callable(hook):
            hook(key)
        self._render_group()
        self.query_one("#cfg-quip", Label).update(QUIPS.get(key, IDLE) + " ▼")

    def _adjust_system(self, key):
        from core import autostart
        quip = key
        if key == "autostart":
            autostart.set_enabled(not autostart.is_enabled())
        elif autostart.is_agent_running():
            quip = "agent_running"
        else:
            autostart.start_agent()
        self._render_group()
        self.query_one("#cfg-quip", Label).update(QUIPS.get(quip, IDLE) + " ▼")
