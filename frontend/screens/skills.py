"""/skills — cartuchos das skills (canvas: "8 · Skills — cartuchos").

Um cartucho por skill, agrupado por categoria. Enter/espaço liga ou desliga a
skill em foco; `c` liga/desliga a categoria inteira. Ligado = encaixado (cor da
categoria); desligado = "fora do slot" (desce 1 linha, apagado).
"""
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal
from textual.widgets import Button, Label

from core import log
from frontend.screens.base import JarvisScreen

# Ícone de 1 célula por palavra-chave do INTENT (fallback ◆)
_GLYPHS = (("APP", "▣"), ("AUDIO", "♪"), ("KEYBOARD", "▤"), ("SCREEN", "▦"),
           ("MACRO", "✱"), ("STATUS", "≡"), ("CLEAR", "✕"), ("SECURITY", "◈"))


def glyph_for(intent):
    return next((g for key, g in _GLYPHS if key in intent.upper()), "◆")


class Cartridge(Button):
    """Cartucho de uma skill. `-on`/`-off` + `-cat-<categoria>` dão a cor."""

    def __init__(self, intent, category, enabled, category_enabled=True):
        super().__init__(self._label(intent, category, enabled), classes="cartridge")
        self.intent = intent
        self.category = category
        self.set_state(enabled, category_enabled)

    @staticmethod
    def _label(intent, category, enabled):
        state = "ON" if enabled else "OFF"
        return f"{glyph_for(intent)}\n{intent}\n■ {category}  {state}"

    def set_state(self, enabled, category_enabled=True):
        self.enabled_ = enabled and category_enabled
        self.label = self._label(self.intent, self.category, self.enabled_)
        self.set_class(self.enabled_, "-on")
        self.set_class(not self.enabled_, "-off")
        self.add_class(f"-cat-{self.category}")


class SkillsScreen(JarvisScreen):
    BADGE = "SKILLS"
    HEADLINE = "Cartuchos instalados"

    BINDINGS = [
        Binding("escape", "close", "Voltar"),
        Binding("space", "toggle", "Liga/desliga"),
        Binding("c", "toggle_category", "Categoria inteira"),
    ]

    def body(self) -> ComposeResult:
        yield Horizontal(id="skills-legend")
        yield Grid(id="skills-grid")
        yield Label("Skills só rodam no Copilot (voz).", classes="hint", id="skills-hint")

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

    def reload(self):
        cats = self._list()
        grid = self.query_one("#skills-grid", Grid)
        existing = {c.intent: c for c in self.query(Cartridge)}
        total = on = 0
        for cat in cats:
            for skill in cat["skills"]:
                total += 1
                on += bool(skill["enabled"] and cat["enabled"])
                cart = existing.get(skill["id"])
                if cart:
                    cart.set_state(skill["enabled"], cat["enabled"])
                else:
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
        if not total:
            grid.mount(Label("Nenhuma skill carregada.", classes="hint"))

    def _focused_cart(self):
        return self.focused if isinstance(self.focused, Cartridge) else None

    def on_button_pressed(self, event: Button.Pressed):
        if isinstance(event.button, Cartridge):
            event.stop()
            self._toggle(event.button)

    def action_toggle(self):
        cart = self._focused_cart()
        if cart:
            self._toggle(cart)

    def _toggle(self, cart):
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
