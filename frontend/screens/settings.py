"""/config — painel de ajustes estilo RPG (canvas: "10 · Configurações").

Menu lateral com cursor ▶ (VOZ, MICROFONE, ROTINAS, INTEGRAÇÕES, SISTEMA, MODELO, SOBRE), opções ◀ ▶ com
barra de blocos e uma caixa de diálogo com o rosto pixel-art do JARVIS
comentando a escolha. Valores persistem em services.user_prefs (tabela config).
INTEGRAÇÕES troca as opções por cards (frontend/screens/integrations_panel.py).
"""
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from core import settings
from frontend import sprites
from frontend.screens.base import JarvisScreen
from frontend.screens.integrations_panel import IntegrationCard
from frontend.widgets import PixelSprite

INTEGRATIONS = "INTEGRAÇÕES"
MENU = ("VOZ", "MICROFONE", "ROTINAS", INTEGRATIONS, "SISTEMA", "MODELO", "SOBRE")

# SISTEMA não mora no user_prefs: o estado vive no registro (Run, AutoUpdate) e no mutex do agente.
SYSTEM_KEYS = ("autostart", "agent", "autoupdate")

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
    "commute_alert": "Aviso de saída ajustado: clima, trânsito e o 1º compromisso, só em dias úteis.",
    "dnd_auto_meeting": "Em reunião eu seguro os alertas. Os críticos passam, claro.",
    "dnd_auto_fullscreen": "Tela cheia é sagrada. Guardo os alertas para depois.",
    "autostart": "Anotado. Eu acordo junto com o Windows — café por sua conta.",
    "agent": "Agente em 2º plano. Win+J me chama de qualquer lugar.",
    "autoupdate": "Toda vez que o Windows me acordar, confiro o GitHub. Versão nova, eu mesmo instalo.",
    "agent_running":"Já estou de plantão. Para me dispensar, use o ícone da bandeja.",
    "int_wait": "Abri o navegador, Senhor. Autorize o acesso e eu cuido do resto.",
    "int_idle": "Enter conecta, Del desconecta. Tokens ficam no Cofre do Windows, Senhor.",
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
                    with Grid(id="cfg-cards"):
                        for integration in self._integrations().all_integrations():
                            yield IntegrationCard(integration, id=f"int-{integration.id}")
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

    @staticmethod
    def _integrations():
        from services import integrations
        return integrations

    def _keys(self):
        if self.group == INTEGRATIONS:
            return ()
        if self.group == "SISTEMA":
            return SYSTEM_KEYS
        return self._prefs().GROUPS.get(self.group, ())

    @staticmethod
    def _system_value(key):
        from core import autostart
        if key == "autostart":
            on = autostart.is_enabled()
            return "Iniciar com o Windows", "ligado" if on else "desligado", on
        if key == "autoupdate":
            from core import updater
            on = updater.is_enabled()
            return "Atualização automática", "ligado" if on else "desligado", on
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
        cards = self.query_one("#cfg-cards", Grid)
        cards.display = self.group == INTEGRATIONS
        if cards.display:
            self.refresh_cards()
        info = self.query_one("#cfg-info", Static)
        info.update(self._info_text())
        info.display = not cards.display  # os cards ocupam o painel; a dica vai na fala do JARVIS

    def refresh_cards(self):
        for card in self.query(IntegrationCard):
            card.refresh_state()

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
            update = ("no logon do Windows, pelo GitHub" if settings.IS_INSTALLED
                      else "só no app instalado (dev usa o git)")
            return (f"Atalho global  {hotkey}\n"
                    f"Versão        v{settings.VERSION} · atualiza {update}\n"
                    "O agente fica na bandeja: fechar a TUI não o fecha, e o atalho\n"
                    "reabre o JARVIS direto no Copilot.")
        if self.group == "ROTINAS":
            return ("Briefing: /briefing força a qualquer hora. Manchetes usam a busca web.\n"
                    "Clipboard: só sugere (/clip); nada copiado vai para o log.\n"
                    "Aviso de saída usa /rota casa|trabalho. Silêncio: alertas críticos sempre passam.")
        return ""

    # -------------------------------------------------------------- eventos
    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted):
        if event.option_list.id == "cfg-menu" and event.option.id != self.group:
            self.group = event.option.id
            self._render_group()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        if event.option_list.id == "cfg-menu":
            if self.group == INTEGRATIONS:
                self._focus_first_card()
                return
            options = self.query_one("#cfg-options", OptionList)
            if options.display:
                options.focus()

    def _focus_first_card(self):
        cards = list(self.query(IntegrationCard))
        if cards:
            cards[0].focus()
            self._quip(QUIPS["int_idle"])

    def action_switch_panel(self):
        menu = self.query_one("#cfg-menu", OptionList)
        if self.group == INTEGRATIONS:
            if menu.has_focus:
                self._focus_first_card()
            else:
                menu.focus()
            return
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
        elif key == "autoupdate":
            from core import updater
            updater.set_enabled(not updater.is_enabled())
        elif autostart.is_agent_running():
            quip = "agent_running"
        else:
            autostart.start_agent()
        self._render_group()
        self.query_one("#cfg-quip", Label).update(QUIPS.get(quip, IDLE) + " ▼")

    # ---------------------------------------------------------- integrações
    def _quip(self, text):
        self.query_one("#cfg-quip", Label).update(text + " ▼")

    def connect_integration(self, integration_id):
        self._connect_worker(integration_id)

    @work(thread=True, group="integrations")
    def _connect_worker(self, integration_id):
        def started():
            self.app.call_from_thread(self._on_connect_started)
        message = self._integrations().connect(integration_id, on_started=started)
        self.app.call_from_thread(self._on_integration_done, message)

    def _on_connect_started(self):
        self.refresh_cards()
        self._quip(QUIPS["int_wait"])

    def _on_integration_done(self, message):
        before = {card.id: getattr(card, "state", None) for card in self.query(IntegrationCard)}
        self.refresh_cards()
        self._quip(message)
        # Toast só quando algo mudou (conectou/desconectou). Instrução de configuração
        # já aparece na fala do JARVIS — repetir no canto empilhava avisos iguais.
        if any(card.state != before.get(card.id) for card in self.query(IntegrationCard)):
            self.app.notify(message, title="Integrações")

    def disconnect_integration(self, integration_id):
        from frontend.widgets import ConfirmScreen
        integration = self._integrations().get(integration_id)
        if integration is None or integration.disconnect is None:
            name = integration.name if integration else "Isso"
            self._quip(f"{name} não tem o que desconectar por aqui.")
            return

        def answer(confirmed):
            if confirmed:
                self._disconnect_worker(integration_id)

        self.app.push_screen(ConfirmScreen(f"Desconectar {integration.name}? O token salvo será apagado.",
                                           title="DESCONECTAR", yes="Desconectar", no="Manter"), answer)

    @work(thread=True, group="integrations")
    def _disconnect_worker(self, integration_id):
        message = self._integrations().disconnect(integration_id)
        self.app.call_from_thread(self._on_integration_done, message)
