"""Easter egg (canvas: "14 · House Party Protocol").

Digitar "house party" no Chat abre esta tela: 8 armaduras genéricas em pixel
art entram 1 por quadro (8 fps), cada uma com sua paleta. Qualquer tecla fecha.
A animação é só a entrada — depois o timer para.
"""
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label

from frontend import sprites
from frontend.widgets import PixelSprite

TRIGGER = "house party"
FPS = 8

# (corpo, acabamento) por armadura — códigos de cor do sprites.py
PALETTES = (
    (sprites.DANGER, sprites.WARN), (sprites.MUTED, sprites.WHITE),
    (sprites.WARN, sprites.DANGER), (sprites.OCEAN, sprites.WHITE),
    (sprites.DEEP, sprites.MUTED), (sprites.DEEP, sprites.NEON),
    (sprites.OCEAN, sprites.PALE), (sprites.DANGER, sprites.WHITE),
)


def is_trigger(text):
    return " ".join(str(text).lower().split()) in (TRIGGER, f"{TRIGGER} protocol", f"protocolo {TRIGGER}")


def suit(body, trim):
    return sprites.sprite("armor", recolor={sprites.DANGER: body, sprites.WHITE: trim})


class HousePartyScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="party"):
            yield Label("HOUSE PARTY PROTOCOL", id="party-title")
            yield Label("unidades online · 0 de 8", id="party-count", classes="hint")
            with Horizontal(id="party-suits"):
                for i, (body, trim) in enumerate(PALETTES):
                    with Vertical(classes="party-suit"):
                        sprite = PixelSprite(suit(body, trim), id=f"suit-{i}")
                        sprite.display = False
                        yield sprite
                        yield Label(f"MK-{i + 1:02d}", classes="party-id")
            yield Label("jarvis › Como quiser, Senhor. Embora eu duvide que isso ajude no TCC.", id="party-quip")
            yield Label("qualquer tecla volta", classes="hint")

    def on_mount(self):
        self._shown = 0
        self._timer = self.set_interval(1 / FPS, self._next)

    def _next(self):
        if self._shown >= len(PALETTES):
            self._timer.stop()
            return
        self.query_one(f"#suit-{self._shown}", PixelSprite).display = True
        self._shown += 1
        self.query_one("#party-count", Label).update(f"unidades online · {self._shown} de {len(PALETTES)}")

    def on_key(self, event: events.Key):
        event.stop()
        self.dismiss(None)
