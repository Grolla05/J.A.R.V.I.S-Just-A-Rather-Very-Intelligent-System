"""/config — painel de ajustes (canvas: "10 · Configurações — Rotinas (seções)").

Menu lateral com ícone, cursor ▶ e contagem (VOZ, MICROFONE, ROTINAS,
INTEGRAÇÕES, SISTEMA, MODELO, SOBRE). Cada grupo vira cards de seção
(settings_rows.SECTIONS) com linhas ▌ nome ◀ valor ▶: liga/desliga é um selo
● ON / ○ OFF, escolhas mostram a posição em pontos e a linha em foco traz a
ajuda ↳ embaixo. No rodapé, a fala do JARVIS digitando. Valores persistem em
services.user_prefs (tabela config); SISTEMA lê/grava o registro.
INTEGRAÇÕES troca as seções por cards (frontend/screens/integrations_panel.py).
SISTEMA tem ainda o campo das fontes de notícias do briefing (core/news.py).
Animações só por evento: troca de grupo (cards entram um a um), troca de valor
(o selo desliza e pisca) e a fala digitando.
"""
import asyncio
import time

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from core import settings
from frontend import sprites
from frontend.screens.base import JarvisScreen
from frontend.screens.integrations_panel import IntegrationCard
from frontend.screens.settings_rows import (
    GROUP_META,
    HELP,
    SECTIONS,
    PrefRow,
    QuipLine,
    RowState,
    row_segments,
    short_label,
    summary,
)
from frontend.widgets import PixelSprite

INTEGRATIONS = "INTEGRAÇÕES"
MENU = ("VOZ", "MICROFONE", "ROTINAS", INTEGRATIONS, "SISTEMA", "MODELO", "SOBRE")
CARD_REVEAL_S = 0.06  # troca de grupo: 1 card por quadro (5 cards ≈ 0,25 s)

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
    "news_ai": "Eu leio as três primeiras de cada jornal e escolho a que importa. Fofoca fica para depois.",
    "briefing_email": "Separo os e-mails que importam antes do café. Promoções ficam para nunca.",
    "remote_telegram": "Ponte do Telegram armada. O cérebro fica aqui; o celular é só o rádio.",
    "remote_discord": "Ponte do Discord armada. Respondo DM e menção — e só a quem está na lista.",
    "clipboard_monitor": "De olho no clipboard. Só sugiro — não leio seus segredos em voz alta.",
    "auto_insights": "Suas ideias vão para 🧠 Brainstorms no vault. As ruins também, Senhor.",
    "commute_alert": "Aviso de saída ajustado: clima, trânsito e o 1º compromisso, só em dias úteis.",
    "event_reminders": "Eu olho a sua agenda e aviso antes. Chegar na hora continua sendo com o senhor.",
    "reminder_lead": "Antecedência ajustada. Tempo de sobra para inventar uma desculpa melhor.",
    "reminder_final": "Aviso final ajustado. Com local e rota conhecidos, vira aviso de saída.",
    "net_monitor": "De guarda no perímetro: porta nova, programa estranho, aparelho intruso. Eu aviso; o senhor decide.",
    "dnd_auto_meeting": "Em reunião eu seguro os alertas. Os críticos passam, claro.",
    "dnd_auto_fullscreen": "Tela cheia é sagrada. Guardo os alertas para depois.",
    "presentation_auto": "Slides em tela cheia — PowerPoint, PDF, Canva: fecho o mic, calo a voz e mostro [SILENT].",
    "presentation_open": "PowerPoint aberto já conta como palco, mesmo fora da tela cheia.",
    "autostart": "Anotado. Eu acordo junto com o Windows — café por sua conta.",
    "agent": "Agente em 2º plano. Win+J me chama de qualquer lugar.",
    "autoupdate": "Toda vez que o Windows me acordar, confiro o GitHub. Versão nova, eu mesmo instalo.",
    "agent_running":"Já estou de plantão. Para me dispensar, use o ícone da bandeja.",
    "int_wait": "Abri o navegador, Senhor. Autorize o acesso e eu cuido do resto.",
    "int_idle": "Enter conecta, Del desconecta. Tokens ficam no Cofre do Windows, Senhor.",
    "news_saved": "Fontes salvas: {n}. As próximas manchetes do briefing saem delas, Senhor.",
}
IDLE = "Escolha uma opção com ↑↓ e ajuste com ←→, Senhor."


class SettingsScreen(JarvisScreen):
    BADGE = "CONFIG"
    HEADLINE = "Painel de ajustes"

    BINDINGS = [
        Binding("escape", "close", "Voltar"),
        Binding("left", "adjust(-1)", "Ajustar", show=False),
        Binding("right", "adjust(1)", "Ajustar", show=False),  # o rodapé mostra o da linha (←→)
        Binding("tab", "switch_panel", "Menu/opções"),
    ]

    def check_action(self, action, parameters):
        # ←→ dentro do campo de fontes movem o cursor do texto, não as opções
        if action == "adjust" and isinstance(self.focused, Input):
            return False
        return True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.group = MENU[0]
        self._built_group = None
        self._last_row = {}  # grupo -> chave da última linha em foco
        self._build_lock = asyncio.Lock()
        self._reveal_timer = None

    def body(self) -> ComposeResult:
        with Horizontal(id="cfg-body"):
            with Vertical(id="cfg-menu-box"):
                yield Label("MENU", classes="hint", id="cfg-menu-title")
                yield OptionList(*[Option(self._menu_label(g), id=g) for g in MENU], id="cfg-menu")
                yield Static("", id="cfg-menu-spacer")
                yield Label("✓ salvo no SQLite", id="cfg-saved")
                yield Label("nada alterado ainda", id="cfg-saved-at", classes="hint")
            with Vertical(id="cfg-main"):
                with Horizontal(id="cfg-head"):
                    yield Label("", id="cfg-group")
                    yield Label("", id="cfg-sub", classes="hint")
                    yield Static("", id="cfg-head-spacer")
                    yield Label("", id="cfg-summary-on")
                    yield Label("", id="cfg-summary-off")
                    yield Label("", id="cfg-summary-n")
                with VerticalScroll(id="cfg-panel"):
                    with Horizontal(id="cfg-sections"):
                        yield Vertical(id="cfg-col-0", classes="cfg-col")
                        yield Vertical(id="cfg-col-1", classes="cfg-col")
                    with Grid(id="cfg-cards"):
                        for integration in self._integrations().all_integrations():
                            yield IntegrationCard(integration, id=f"int-{integration.id}")
                    with Vertical(id="cfg-news"):
                        yield Label("Fontes de notícias do briefing (separadas por vírgula)", classes="hint")
                        with Horizontal(id="cfg-news-row"):
                            yield Input(id="cfg-news-input", placeholder="G1, BBC, CNN, DOI…")
                            yield Button("Salvar alterações", id="cfg-news-save")
                    yield Static("", id="cfg-info", markup=False)
                with Horizontal(id="cfg-quip-box"):
                    yield PixelSprite(sprites.sprite("face"), id="cfg-quip-face")
                    yield Label("jarvis ›", id="cfg-quip-who")
                    yield QuipLine(IDLE, id="cfg-quip")

    def _menu_label(self, group):
        icon = GROUP_META.get(group, ("·", ""))[0]
        count = self._group_count(group)
        cursor = "▶" if group == self.group else " "
        return f"{cursor} {icon}  {group:<12}{count:>3}"

    def _group_count(self, group):
        if group == INTEGRATIONS:
            try:
                return str(len(self._integrations().all_integrations()))
            except Exception:
                return ""
        keys = self._keys_of(group)
        return str(len(keys)) if keys else ""

    async def on_mount(self):
        super().on_mount()
        await self._render_group()
        self.query_one("#cfg-menu", OptionList).focus()

    # ------------------------------------------------------------- dados
    def _prefs(self):
        from services import user_prefs
        return user_prefs

    @staticmethod
    def _integrations():
        from services import integrations
        return integrations

    def _keys_of(self, group):
        return tuple(k for section in SECTIONS.get(group, ()) for k in section.keys)

    def _keys(self):
        return self._keys_of(self.group)

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

    def _row_state(self, key):
        """RowState + textos do selo de uma chave (prefs ou SISTEMA)."""
        if key in SYSTEM_KEYS:
            label, value, on = self._system_value(key)
            texts = ("RODANDO", "PARADO") if key == "agent" else ("ON", "OFF")
            return RowState(key, label, value, toggle=True, on=on), texts
        p = self._prefs()
        options = p.PREFS[key][1]
        current = p.get(key)
        if tuple(options) == (False, True):
            return RowState(key, short_label(key, p.label(key)), p.display(key), toggle=True, on=bool(current)), \
                ("ON", "OFF")
        pos = options.index(current) if current in options else 0
        return RowState(key, short_label(key, p.label(key)), p.display(key), pos=pos, total=len(options)), \
            ("ON", "OFF")

    def _option_text(self, key):
        """Linha da preferência em texto puro (testes e leitores de tela)."""
        row, (on_text, off_text) = self._row_state(key)
        return "".join(t for t, _ in row_segments(row, 60, False, 0, on_text, off_text))

    # ------------------------------------------------------------- render
    async def _render_group(self):
        """Monta o grupo atual: seções (cards) só quando o grupo muda."""
        menu = self.query_one("#cfg-menu", OptionList)
        for i, group in enumerate(MENU):
            menu.replace_option_prompt_at_index(i, self._menu_label(group))
        icon, sub = GROUP_META.get(self.group, ("·", ""))
        self.query_one("#cfg-group", Label).update(f"{icon} {self.group}")
        self.query_one("#cfg-sub", Label).update(sub)
        if self._built_group != self.group:
            await self._build_sections()
        cards = self.query_one("#cfg-cards", Grid)
        cards.display = self.group == INTEGRATIONS
        if cards.display:
            self.refresh_cards()
        news_box = self.query_one("#cfg-news", Vertical)
        if self.group == "SISTEMA" and not news_box.display:
            self.query_one("#cfg-news-input", Input).value = self._news().get_sources()
        news_box.display = self.group == "SISTEMA"
        info = self.query_one("#cfg-info", Static)
        text = self._info_text()
        info.update(text)
        info.display = bool(text) and not cards.display
        self._refresh_values()

    async def _build_sections(self):
        # Troca de grupo rápida (↑↓ no menu) dispara montagens seguidas: uma de cada vez
        async with self._build_lock:
            if self._built_group == self.group:
                return
            await self._build_sections_now()

    async def _build_sections_now(self):
        self._built_group = self.group
        sections = SECTIONS.get(self.group, ())
        cols = [self.query_one(f"#cfg-col-{i}", Vertical) for i in (0, 1)]
        for col in cols:
            await col.remove_children()
        by_column = ([], [])
        for n, section in enumerate(sections):
            rows = []
            for key in section.keys:
                row, (on_text, off_text) = self._row_state(key)
                rows.append(PrefRow(row, HELP.get(key, ""), on_text, off_text, id=f"pref-{key}"))
            card = Vertical(*rows, Label(section.hint, classes="cfg-card-hint", markup=False),
                            classes="cfg-card", id=f"sec-{n}")  # id sem acento (Textual recusa)
            card.border_title = f"{section.icon} {section.title}"
            by_column[min(section.column, 1)].append(card)
        for col, cards in zip(cols, by_column):
            if cards:
                await col.mount_all(cards)
        two_columns = any(s.column for s in sections)
        cols[1].display = two_columns
        self.query_one("#cfg-sections").display = bool(sections)
        self.query_one("#cfg-panel").scroll_home(animate=False)
        self._reveal_cards([c for col in by_column for c in col])

    def _reveal_cards(self, cards):
        """Troca de grupo: os cards entram um por quadro, na ordem de leitura.
        (O fade por opacidade do Textual deixava fundo velho nas linhas.)"""
        if self._reveal_timer is not None:
            self._reveal_timer.stop()
        pending = list(cards)
        for card in pending:
            card.styles.visibility = "hidden"

        def step():
            if pending:
                pending.pop(0).styles.visibility = "visible"
            if not pending and self._reveal_timer is not None:
                self._reveal_timer.stop()
                self._reveal_timer = None

        step()
        if pending:
            self._reveal_timer = self.set_interval(CARD_REVEAL_S, step)

    def _rows(self):
        return list(self.query(PrefRow))

    def _refresh_values(self, animate_key=None):
        """Atualiza valores, contagens das seções, resumo e topo — sem remontar."""
        states = []
        for widget in self._rows():
            row, (on_text, off_text) = self._row_state(widget.row.key)
            widget.set_row(row, on_text, off_text, animate=widget.row.key == animate_key)
            states.append(row)
        for card in self.query(".cfg-card"):
            active, total = summary(w.row for w in card.query(PrefRow))
            card.border_subtitle = f"{active}/{total}"
        # "N de M ativas" só faz sentido onde há liga/desliga (VOZ e MICROFONE só têm escolhas)
        active, total = summary(states) if any(r.toggle for r in states) else (0, 0)
        on = self.query_one("#cfg-summary-on", Label)
        off = self.query_one("#cfg-summary-off", Label)
        count = self.query_one("#cfg-summary-n", Label)
        for widget in (on, off, count):
            widget.display = bool(total)
        on.update("▮" * active)
        off.update("▮" * (total - active))
        count.update(f" {active}/{total}")
        self.set_info(f"{self.group} · {active} de {total} ativas" if total else self.group)

    @staticmethod
    def _news():
        from core import news
        return news

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
        if self.group == "SISTEMA":
            hotkey = settings.GLOBAL_HOTKEY or "desligado (GLOBAL_HOTKEY vazio)"
            update = ("no logon do Windows, pelo GitHub" if settings.IS_INSTALLED
                      else "só no app instalado (dev usa o git)")
            return (f"Atalho global  {hotkey}\n"
                    f"Versão         v{settings.VERSION} · atualiza {update}")
        return ""

    # -------------------------------------------------------------- eventos
    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted):
        if event.option_list.id == "cfg-menu" and event.option.id != self.group:
            self.group = event.option.id
            await self._render_group()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        if event.option_list.id == "cfg-menu":
            if self.group == INTEGRATIONS:
                self._focus_first_card()
                return
            self._focus_rows()

    def _focus_rows(self):
        """Foca a última linha usada do grupo (ou a 1ª). False se não há linhas."""
        rows = self._rows()
        if not rows:
            return False
        key = self._last_row.get(self.group)
        target = next((r for r in rows if r.row.key == key), rows[0])
        target.focus()
        return True

    def on_descendant_focus(self, event):
        if isinstance(event.widget, PrefRow):
            self._last_row[self.group] = event.widget.row.key

    def move_row(self, row, delta):
        rows = self._rows()
        target = rows.index(row) + delta
        if 0 <= target < len(rows):
            rows[target].focus()
        elif target < 0:
            self.query_one("#cfg-menu", OptionList).focus()  # sai pelo topo, volta ao menu

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
        in_rows = isinstance(self.focused, PrefRow)
        ring = ["menu"] + (["rows"] if self._rows() else [])
        if self.group == "SISTEMA":
            ring += ["input", "save"]
        current = ("rows" if in_rows else "menu" if menu.has_focus
                   else "input" if self.focused is self.query_one("#cfg-news-input")
                   else "save" if self.focused is self.query_one("#cfg-news-save") else None)
        nxt = ring[(ring.index(current) + 1) % len(ring)] if current in ring else ring[0]
        if nxt == "rows":
            self._focus_rows()
        elif nxt == "input":
            self.query_one("#cfg-news-input", Input).focus()
        elif nxt == "save":
            self.query_one("#cfg-news-save", Button).focus()
        else:
            menu.focus()

    # ------------------------------------------------------ fontes de notícias
    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cfg-news-save":
            self.save_news_sources()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "cfg-news-input":
            self.save_news_sources()

    def save_news_sources(self):
        field = self.query_one("#cfg-news-input", Input)
        news = self._news()
        try:
            saved = news.save_sources(field.value)
        except Exception as e:
            self._quip(f"Não consegui salvar as fontes: {e}")
            return
        field.value = saved
        self._mark_saved()
        self._quip(QUIPS["news_saved"].format(n=len(news.parse_sources(saved))))

    def _mark_saved(self):
        self.query_one("#cfg-saved-at", Label).update(f"alterado às {time.strftime('%H:%M:%S')}")

    def action_adjust(self, direction):
        row = self.focused
        if not isinstance(row, PrefRow):
            return
        key = row.row.key
        if key in SYSTEM_KEYS:
            self._adjust_system(key)
            return
        before = self._prefs().get(key)
        self._prefs().step(key, direction)
        if self._prefs().get(key) == before:
            return  # já no limite: nada muda, nada pisca
        hook = getattr(self.app, "on_pref_changed", None)
        if callable(hook):
            hook(key)
        self._refresh_values(animate_key=key)
        self._mark_saved()
        self._quip(QUIPS.get(key, IDLE))

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
        self._refresh_values(animate_key=key if quip == key else None)
        if quip == key:
            self._mark_saved()
        self._quip(QUIPS.get(quip, IDLE))

    # ---------------------------------------------------------- integrações
    def _quip(self, text):
        self.query_one("#cfg-quip", QuipLine).say(text)

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
