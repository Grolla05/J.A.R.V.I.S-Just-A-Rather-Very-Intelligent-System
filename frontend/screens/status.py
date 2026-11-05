"""/status — dashboard do sistema (canvas: "6 · Dashboard de sistema").

Quatro painéis (CPU, RAM, GPU, REDE) com gráfico de barras do histórico que o
JarvisApp já coleta a cada TELEMETRY_INTERVAL, e um painel lateral com a
mini-orb (cor pela carga), top processos e uptime. Nada anima em loop: o
gráfico só muda quando chega amostra nova.
"""
from textual import work
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import Label, Static

import core.state as state
from core import log, settings
from frontend import sprites
from frontend.screens.base import JarvisScreen
from frontend.widgets import PixelSprite

CHART_HEIGHT = 6
METERS = (("CPU", "%"), ("RAM", "%"), ("GPU", "%"), ("REDE", "B/s"))
_ORB_COLOR = {"baixa": sprites.NEON, "moderada": sprites.WARN, "alta": sprites.DANGER}
_LEVEL_LABEL = {"baixa": "BAIXA", "moderada": "MODERADA", "alta": "ALTA"}


def human_rate(bps):
    for unit in ("B", "KB", "MB", "GB"):
        if bps < 1024 or unit == "GB":
            return f"{bps:.1f} {unit}/s" if unit != "B" else f"{bps:.0f} B/s"
        bps /= 1024
    return f"{bps:.1f} GB/s"


class Meter(Vertical):
    """Painel de uma métrica: nome + valor atual + gráfico de barras."""

    def __init__(self, name, unit, **kwargs):
        super().__init__(classes="meter", **kwargs)
        self.metric = name
        self.unit = unit

    def compose(self) -> ComposeResult:
        yield Label(self.metric, classes="meter-name")
        yield Label("—", classes="meter-value")
        yield Static("", classes="meter-chart")
        yield Label("", classes="meter-detail")

    def update_values(self, history, detail=""):
        values = list(history)
        current = values[-1] if values else 0
        if self.unit == "%":
            top, text = 100.0, f"{current:.0f}%"
            level = sprites.load_level(current)
        else:  # rede: escala pelo pico recente (mín. 1 MB/s)
            top, text = max([1024 * 1024, *values]), human_rate(current)
            level = "baixa"
        self.query_one(".meter-value", Label).update(text)
        for cls in ("-baixa", "-moderada", "-alta"):
            self.remove_class(cls)
        self.add_class(f"-{level}")
        chart = self.query_one(".meter-chart", Static)
        width = max(10, (chart.size.width or 40))
        chart.update("\n".join(sprites.bar_chart(values, width, CHART_HEIGHT, top)))
        self.query_one(".meter-detail", Label).update(detail)


class StatusScreen(JarvisScreen):
    BADGE = "STATUS"
    HEADLINE = "Diagnóstico do sistema · últimos 2 min"

    def body(self) -> ComposeResult:
        with Horizontal(id="status-body"):
            with Grid(id="status-grid"):
                for name, unit in METERS:
                    yield Meter(name, unit, id=f"meter-{name.lower()}")
            with Vertical(id="status-side"):
                yield Label("núcleo · carga", classes="hint")
                yield PixelSprite(sprites.sprite("mini_orb"), id="status-orb")
                yield Label("—", id="status-level")
                yield Label("top processos (RAM)", classes="hint")
                yield Static("carregando…", id="status-procs", markup=False)
                yield Label("", id="status-uptime", classes="hint")

    def on_mount(self):
        super().on_mount()
        self.refresh_data()
        self.set_interval(settings.TELEMETRY_INTERVAL, self.refresh_data)
        self._load_details()

    def refresh_data(self):
        history = getattr(self.app, "telemetry_history", {})
        details = getattr(self, "_details", {})
        for name, _unit in METERS:
            self.query_one(f"#meter-{name.lower()}", Meter).update_values(
                history.get(name, ()), details.get(name, ""))
        loads = [list(history.get(n, ()))[-1] for n in ("CPU", "RAM", "GPU") if history.get(n)]
        level = sprites.load_level(max(loads) if loads else 0)
        self.query_one("#status-orb", PixelSprite).set_frames(
            sprites.sprite("mini_orb", recolor={sprites.NEON: _ORB_COLOR[level]}))
        label = self.query_one("#status-level", Label)
        label.update(_LEVEL_LABEL[level])
        for cls in ("-baixa", "-moderada", "-alta"):
            label.remove_class(cls)
        label.add_class(f"-{level}")

    @work(thread=True, group="status-details", exclusive=True)
    def _load_details(self):
        mon = state.sys_monitor
        details, procs, uptime = {}, [], ""
        try:
            cpu = mon.get_cpu_detailed() or {}
            details["CPU"] = f"{cpu.get('cores_logical', '?')} núcleos · {cpu.get('freq_current', '')}"
            ram = mon.get_ram_usage() or {}
            details["RAM"] = f"{ram.get('used', '?')} / {ram.get('total', '?')}"
            gpu = mon.get_gpu_info() or {}
            details["GPU"] = f"{gpu.get('name', '?')} · {gpu.get('memory_used', '?')}"
            net = mon.get_network_speed() or {}
            details["REDE"] = f"↓ {net.get('download_speed', '?')} · ↑ {net.get('upload_speed', '?')}"
            procs = mon.get_top_processes("memory", 4) or []
            uptime = (mon.get_system_general() or {}).get("uptime", "")
        except Exception as e:
            log.debug(f"Detalhes do /status indisponíveis: {e}")
        self.app.call_from_thread(self._apply_details, details, procs, uptime)

    def _apply_details(self, details, procs, uptime):
        self._details = details
        self.query_one("#status-procs", Static).update("\n".join(procs) or "indisponível")
        self.query_one("#status-uptime", Label).update(f"uptime {uptime}" if uptime else "")
        self.set_info(f"uptime {uptime}" if uptime else "")
        self.refresh_data()
