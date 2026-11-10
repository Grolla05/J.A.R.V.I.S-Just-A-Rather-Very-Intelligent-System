"""Desligamento estilo CRT (canvas: "13 · Shutdown CRT").

Mostra 3 linhas de encerramento com `[  OK  ]` e então os 5 quadros do CRT
(tela cheia → faixa → linha → linha curta → ponto), ~100 ms cada. No fim
chama `on_done()` (que faz o `app.exit()`). Esc de novo pula a animação.
"""
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, Static

from frontend import sprites

LINES = ("Salvando sessão…", "Encerrando stream do Ollama…", "Liberando microfone…")
LINE_S = 0.12   # intervalo entre as linhas de encerramento
FRAME_S = 0.1   # quadro do CRT


class ShutdownScreen(Screen):
    BINDINGS = [Binding("escape", "now", "Sair já", priority=True)]

    def __init__(self, on_done, **kwargs):
        super().__init__(**kwargs)
        self._on_done = on_done
        self._step = 0
        self._frames = None
        self._finished = False

    def compose(self) -> ComposeResult:
        with Vertical(id="shutdown-lines"):
            for text in LINES:
                yield Label(f"{text:<32}", classes="shutdown-line", markup=False)  # "[  OK  ]" não é tag
            yield Label("", id="shutdown-bye")
        yield Static("", id="crt")

    def on_mount(self):
        self.query_one("#crt", Static).display = False
        self._timer = self.set_interval(LINE_S, self._tick)

    def _tick(self):
        lines = list(self.query(".shutdown-line"))
        if self._step < len(lines):
            label = lines[self._step]
            label.update(f"{LINES[self._step]:<32} [  OK  ]")
            label.add_class("-ok")
        elif self._step == len(lines):
            self.query_one("#shutdown-bye", Label).update("Até logo, Senhor.")
        else:
            if self._frames is None:
                self._timer.stop()
                self.query_one("#shutdown-lines").display = False
                crt = self.query_one("#crt", Static)
                crt.display = True
                size = self.size
                self._frames = sprites.crt_frames(max(3, size.width), max(3, size.height))
                self._frame = 0
                self._timer = self.set_interval(FRAME_S, self._crt_tick)
                self._crt_tick()
            return
        self._step += 1

    def _crt_tick(self):
        crt = self.query_one("#crt", Static)
        if self._frame < len(self._frames):
            crt.update("\n".join(self._frames[self._frame]))
            self._frame += 1
            return
        crt.update("")
        self._timer.stop()
        self._finish()

    def _finish(self):
        if not self._finished:
            self._finished = True
            self._on_done()

    def action_now(self):
        self._finish()
