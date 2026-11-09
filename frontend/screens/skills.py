"""/skills — cartuchos das skills (canvas: "8 · Skills — cartuchos").

Um cartucho retrô por skill: aba na cor da categoria, etiqueta com ícone e
INTENT, linha "■ categoria … ON" e os contatos dourados no rodapé.
Os cartuchos ficam agrupados por categoria (título + grade, com uma linha
separando uma categoria da outra) dentro de uma área rolável.
Enter/espaço/clique liga ou desliga a skill em foco; `c` liga/desliga a
categoria inteira. Ligado = encaixado (cor da categoria); desligado = "fora do
slot" (desce 1 linha, apagado).
"""
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Label, Rule, Static

from core import log
from frontend.screens.base import JarvisScreen

# Ícone de 1 célula por palavra-chave do INTENT (fallback ◆). Ordem importa:
# a 1ª palavra encontrada no INTENT vence.
_GLYPHS = (("SPOTIFY", "♫"), ("APP", "▣"), ("AUDIO", "♪"), ("KEYBOARD", "⌨"),
           ("SCREEN", "▦"), ("MACRO", "⚙"), ("STATUS", "≡"), ("REPORT", "≡"),
           ("CLEAN", "✕"), ("CLEAR", "✕"), ("SECURITY", "⛨"), ("WEB", "⌕"),
           ("GITHUB", "⎇"), ("BRIEFING", "☀"), ("CLIPBOARD", "⎘"), ("FOCUS", "◷"))
FALLBACK_GLYPH = "◆"
TAB = "▄" * 12  # aba de encaixe no topo do cartucho


def glyph_for(intent):
    return next((g for key, g in _GLYPHS if key in intent.upper()), FALLBACK_GLYPH)


class CartContacts(Static):
    """Contatos do cartucho (▮ ▮ ▮…) ocupando a largura."""

    def render(self):
        width = max(self.size.width, 1)
        return ("▮ " * (width // 2 + 1))[:width]


class Cartridge(Vertical, can_focus=True):
    """Cartucho de uma skill. `-on`/`-off` + `-cat-<categoria>` dão a cor."""

    def __init__(self, intent, category, enabled, category_enabled=True):
        super().__init__(classes=f"cartridge -cat-{category}")
        self.intent = intent
        self.category = category
        self.enabled_ = False
        self.set_state(enabled, category_enabled)

    def compose(self) -> ComposeResult:
        yield Static(TAB, classes="cart-tab")
        with Vertical(classes="cart-label"):
            yield Static(glyph_for(self.intent), classes="cart-icon", markup=False)
            yield Static(self.intent, classes="cart-name", markup=False)
        with Horizontal(classes="cart-info"):
            yield Static("■", classes="cart-dot")
            yield Static(self.category, classes="cart-cat", markup=False)
            yield Static(self._state_text(), classes="cart-state")
        yield Static(classes="cart-gap")
        yield CartContacts(classes="cart-contacts")

    def _state_text(self):
        return "ON" if self.enabled_ else "OFF"

    def set_state(self, enabled, category_enabled=True):
        self.enabled_ = bool(enabled and category_enabled)
        self.set_class(self.enabled_, "-on")
        self.set_class(not self.enabled_, "-off")
        for state in self.query(".cart-state"):
            state.update(self._state_text())

    def on_click(self):
        self.focus()
        self.screen.toggle_cartridge(self)


class SkillsScreen(JarvisScreen):
    BADGE = "SKILLS"
    HEADLINE = "Cartuchos instalados"

    BINDINGS = [
        Binding("escape", "close", "Voltar"),
        Binding("space", "toggle", "Liga/desliga"),
        Binding("enter", "toggle", "Liga/desliga", show=False),
        Binding("c", "toggle_category", "Categoria inteira"),
        Binding("up", "move(-4)", show=False),
        Binding("down", "move(4)", show=False),
        Binding("left", "move(-1)", show=False),
        Binding("right", "move(1)", show=False),
    ]
    COLUMNS = 4

    def body(self) -> ComposeResult:
        yield Horizontal(id="skills-legend")
        yield VerticalScroll(id="skills-scroll")

    def status_hint(self):
        return "skills só rodam no Copilot (voz)"

    def on_mount(self):
        super().on_mount()
        self.reload()
        self.call_after_refresh(self._focus_first)

    def _focus_first(self):
        carts = list(self.query(Cartridge))
        if carts:
            carts[0].focus()

    def _list(self):
        from services.skill_settings import list_skills
        try:
            return list_skills()
        except Exception as e:
            log.error(f"Falha ao listar skills: {e}")
            return []

    def _section_grid(self, category):
        """Grade da categoria; cria título + grade (e o separador antes, se não
        for a 1ª) no fim da área rolável quando ainda não existe."""
        grids = {g.category: g for g in self.query(".skills-grid")}
        if category in grids:
            return grids[category]
        scroll = self.query_one("#skills-scroll", VerticalScroll)
        if grids:
            scroll.mount(Rule(line_style="heavy", classes="skills-rule"))
        scroll.mount(Label(category.upper(), classes=f"skills-cat-title -cat-{category}", markup=False))
        grid = Grid(classes="skills-grid")
        grid.category = category
        scroll.mount(grid)
        return grid

    def reload(self):
        cats = self._list()
        existing = {c.intent: c for c in self.query(Cartridge)}
        total = on = 0
        for cat in cats:
            if not cat["skills"]:
                continue
            grid = None
            for skill in cat["skills"]:
                total += 1
                on += bool(skill["enabled"] and cat["enabled"])
                cart = existing.get(skill["id"])
                if cart:
                    cart.set_state(skill["enabled"], cat["enabled"])
                else:
                    grid = grid or self._section_grid(cat["id"])
                    grid.mount(Cartridge(skill["id"], cat["id"], skill["enabled"], cat["enabled"]))
        legend = self.query_one("#skills-legend", Horizontal)
        legend.remove_children()
        for cat in cats:
            count = len(cat["skills"])
            if not count:
                continue
            mark = "■" if cat["enabled"] else "□"
            legend.mount(Label(f"{mark} {cat['id']} · {count}", classes=f"legend -cat-{cat['id']}"))
        self.query_one("#session-title").update(f"Cartuchos instalados · {on} de {total} ligados")
        if not total and not self.query(".skills-empty"):
            self.query_one("#skills-scroll", VerticalScroll).mount(
                Label("Nenhuma skill carregada.", classes="hint skills-empty"))

    def _focused_cart(self):
        return self.focused if isinstance(self.focused, Cartridge) else None

    def action_move(self, step):
        carts = list(self.query(Cartridge))
        cart = self._focused_cart()
        if not carts or cart is None:
            return
        index = carts.index(cart) + step
        if 0 <= index < len(carts):
            carts[index].focus()

    def action_toggle(self):
        cart = self._focused_cart()
        if cart:
            self.toggle_cartridge(cart)

    def toggle_cartridge(self, cart):
        from services.skill_settings import set_enabled
        set_enabled(cart.intent, not cart.enabled_)
        self.reload()

    def action_toggle_category(self):
        from services.skill_settings import set_enabled
        cart = self._focused_cart()
        if not cart:
            return
        cat = next((c for c in self._list() if c["id"] == cart.category), None)
        if cat is not None:
            set_enabled(cart.category, not cat["enabled"])
            self.reload()
