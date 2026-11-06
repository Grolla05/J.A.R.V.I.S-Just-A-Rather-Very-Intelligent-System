"""Boot / splash (canvas: "5 · Boot / Splash").

Checagem estilo BIOS: cada etapa de `core.boot` vira uma linha `[  OK  ]`,
`[ WARN ]` ou `[ FAIL ]`, o logo é montado por scanline (1 linha por quadro,
8 fps) e uma barra de blocos mostra o progresso. Fecha sozinha ao terminar
(ou com Esc). O timer só existe durante o boot — é uma transição.
"""
from collections import deque

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label, Static

from core import settings
from frontend import sprites

FPS = 8
CLOSE_DELAY_S = 0.8
DONE = "__done__"

LOGO = (
    "     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗",
    "     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝",
    "     ██║███████║██████╔╝██║   ██║██║███████╗",
    "██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║",
    "╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║",
    " ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝",
)

TAGS = {"ok": "[  OK  ]", "warn": "[ WARN ]", "fail": "[ FAIL ]", "wait": "[ .... ]"}


class BootScreen(Screen):
    BINDINGS = [Binding("escape", "skip", "Pular")]

    def __init__(self, boot_fn, total_steps=7, **kwargs):
        """`boot_fn(report)` roda as checagens (core.boot.run_boot) numa thread."""
        super().__init__(**kwargs)
        self._boot_fn = boot_fn
        self._total = max(1, total_steps)
        self._events = deque()   # chegam da thread, saem 1 por quadro
        self._rows = {}          # etapa -> Horizontal da linha
        self._latest = {}        # etapa -> (status, detalhe) mais recente
        self._done_steps = 0
        self._finished = False
        self._logo_rows = 0
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="boot"):
            with Horizontal(id="boot-head"):
                yield Label(f"STARK-BIOS · {settings.PROJECT_NAME} v{settings.VERSION}", id="boot-bios")
                yield Label("Esc pula", classes="hint")
            with Horizontal(id="boot-logo-row"):
                yield Static("\n".join(sprites.scanline_reveal(LOGO, 0)), id="boot-logo")
                with Vertical(id="boot-ident"):
                    yield Label("Just A Rather Very Intelligent System", id="boot-tagline")
                    yield Label(f"modelo {settings.OLLAMA_MODEL}", classes="hint")
                    yield Label("scanline 0/6 · 8 fps", id="boot-scan", classes="hint")
            yield Vertical(id="boot-checks")
            with Horizontal(id="boot-progress-head"):
                yield Label("Carregando núcleo cognitivo", id="boot-progress-label")
                yield Label("0%", id="boot-pct")
            yield Label(sprites.block_bar(0, 40, "█", "░"), id="boot-bar")
            yield Label("", id="boot-final")

    def on_mount(self):
        self._timer = self.set_interval(1 / FPS, self._tick)
        self._start_boot()

    @work(thread=True, group="boot")
    def _start_boot(self):
        self._boot_fn(lambda step, status, detail="": self._events.append((step, status, detail)))

    # ---------------------------------------------------------------- quadros
    def _tick(self):
        if self._logo_rows < len(LOGO):
            self._logo_rows += 1
            self.query_one("#boot-logo", Static).update("\n".join(sprites.scanline_reveal(LOGO, self._logo_rows)))
            self.query_one("#boot-scan", Label).update(f"scanline {self._logo_rows}/{len(LOGO)} · 8 fps")
        if self._events:
            self._apply(*self._events.popleft())
        elif self._finished and self._timer is not None:
            self._timer.stop()
            self._timer = None
            self.query_one("#boot-final", Label).update("Sistemas online, Senhor. ▌")
            self.set_timer(CLOSE_DELAY_S, self._close)

    def _apply(self, step, status, detail):
        if step == DONE:
            self._finished = True
            self._set_progress(1.0)
            return
        checks = self.query_one("#boot-checks", Vertical)
        self._latest[step] = (status, detail)
        row = self._rows.get(step)
        if row is None:
            # markup=False: o Textual leria "[  OK  ]" como tag e apagaria o selo
            row = Horizontal(Label("", classes="boot-tag", markup=False),
                             Label(step, classes="boot-step", markup=False),
                             Label("", classes="boot-detail", markup=False), classes="boot-row")
            self._rows[step] = row
            checks.mount(row)
            self.call_after_refresh(self._paint_latest, step)
        else:
            self._paint_latest(step)
        if status != "wait":
            self._done_steps += 1
            self._set_progress(self._done_steps / self._total)

    def _paint_latest(self, step):
        """Pinta o estado MAIS RECENTE da etapa: a linha pode receber o 'ok'
        antes de terminar de montar, e a pintura atrasada não pode voltar a 'wait'."""
        row = self._rows.get(step)
        if row is not None and row.is_mounted:
            self._paint_row(row, *self._latest[step])

    def _paint_row(self, row, status, detail):
        tag = row.query_one(".boot-tag", Label)
        tag.update(TAGS.get(status, TAGS["wait"]))
        for s in TAGS:
            tag.remove_class(f"-{s}")
        tag.add_class(f"-{status}")
        row.query_one(".boot-detail", Label).update(detail)

    def _set_progress(self, fraction):
        pct = int(round(min(1.0, fraction) * 100))
        self.query_one("#boot-pct", Label).update(f"{pct}%")
        self.query_one("#boot-bar", Label).update(sprites.block_bar(pct, 40, "█", "░"))

    def _close(self):
        if self.is_current:
            self.dismiss(True)

    def action_skip(self):
        self.dismiss(False)
