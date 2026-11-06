"""/status — dashboard do sistema (canvas: "6 · Dashboard de sistema").

Grade 2×2 (CPU, RAM, GPU, REDE): nome e valor atual no topo do painel, gráfico
de barras espaçadas do histórico que o JarvisApp já coleta a cada
TELEMETRY_INTERVAL (cada barra na cor da sua faixa de carga) e o detalhe
embaixo. Ao lado: núcleo pixel-art, faixa de carga, top processos por memória
e o limiar crítico. Nada anima em loop: só muda quando chega amostra nova.
"""
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Grid, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

import core.state as state
from core import log, settings
from frontend import sprites
from frontend.screens.base import JarvisScreen
from frontend.widgets import PixelSprite

METERS = (("CPU", "%"), ("RAM", "%"), ("GPU", "%"), ("REDE", "B/s"))
NET_MIN_TOP = 1024 * 1024  # escala mínima do gráfico de rede (1 MB/s)
TOP_PROCESSES = 5
_ORB_COLOR = {"baixa": sprites.NEON, "moderada": sprites.NEON, "alta": sprites.DANGER}
_LEVEL_LABEL = {"baixa": "BAIXA", "moderada": "MODERADA", "alta": "ALTA"}
_UNITS = ("B", "KB", "MB", "GB")


def num(value, decimals=1):
    """Número em pt-BR: 22.7 → '22,7'; 32.0 → '32'."""
    text = f"{value:.{decimals}f}".replace(".", ",")
    return text[:-2] if decimals == 1 and text.endswith(",0") else text


def rate_unit(bps):
    """Unidade e divisor que cabem em `bps` (B/s, KB/s, MB/s, GB/s)."""
    bps = max(0.0, float(bps or 0))
    for i, unit in enumerate(_UNITS):
        if bps < 1024 ** (i + 1) or unit == "GB":
            return unit, 1024 ** i
    return "GB", 1024 ** 3


def human_rate(bps):
    unit, div = rate_unit(bps)
    return f"{num((bps or 0) / div, 0 if unit == 'B' else 1)} {unit}/s"


def net_detail(down, up):
    """'↓ 1,1 · ↑ 0,1 MB/s' — a unidade é a do maior dos dois."""
    unit, div = rate_unit(max(down or 0, up or 0))
    d = 0 if unit == "B" else 1
    return f"↓ {num((down or 0) / div, d)} · ↑ {num((up or 0) / div, d)} {unit}/s"


def human_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{num(n, 0 if unit in ('B', 'KB') else 1)} {unit}"
        n /= 1024
    return f"{num(n)} GB"


def format_uptime(seconds):
    seconds = max(0, int(seconds or 0))
    h, rest = divmod(seconds, 3600)
    return f"{h:02d}:{rest // 60:02d}:{rest % 60:02d}"


def window_label(samples, interval):
    seconds = samples * interval
    if seconds >= 120:
        return f"últimos {num(seconds / 60)} min"
    return f"últimos {seconds:.0f} s"


class BarChart(Widget):
    """Gráfico de barras espaçadas do histórico, ocupando o espaço do painel.
    Com `leveled`, cada barra pega a cor da faixa de carga do seu valor."""

    COMPONENT_CLASSES = {"chart--baixa", "chart--moderada", "chart--alta"}
    DEFAULT_CSS = "BarChart { width: 1fr; height: 1fr; }"

    def __init__(self, leveled=True, **kwargs):
        super().__init__(**kwargs)
        self.leveled = leveled
        self.values = []
        self.top = 100.0

    def set_values(self, values, top=100.0):
        self.values = list(values)
        self.top = top
        self.refresh()

    @property
    def slots(self):
        return sprites.bar_slots(self.size.width)

    def _style(self, value):
        level = sprites.load_level(value) if self.leveled else "baixa"
        return self.get_component_rich_style(f"chart--{level}", partial=True)

    def render(self):
        width, height = self.size.width, self.size.height
        if width <= 0 or height <= 0:
            return ""
        lines, shown = sprites.spaced_bar_chart(self.values, width, height, self.top)
        styles = [self._style(v) if v is not None else None for v in shown]
        text = Text(no_wrap=True, end="")
        for row, line in enumerate(lines):
            for i, char in enumerate(line):
                text.append(char, styles[i // 2] if char != " " and i % 2 == 0 else None)
            if row < len(lines) - 1:
                text.append("\n")
        return text


class ProcessList(Widget):
    """Top processos: nome (claro) · memória (apagada)."""

    COMPONENT_CLASSES = {"procs--name", "procs--size"}
    DEFAULT_CSS = "ProcessList { width: 1fr; height: auto; }"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.items = None  # None = carregando

    def set_items(self, items):
        self.items = list(items)
        self.refresh(layout=True)

    def get_content_height(self, container, viewport, width):
        return max(1, len(self.items or ()))

    def render(self):
        size_style = self.get_component_rich_style("procs--size", partial=True)
        if not self.items:
            return Text("carregando…" if self.items is None else "indisponível", size_style)
        name_style = self.get_component_rich_style("procs--name", partial=True)
        text = Text(no_wrap=True, overflow="ellipsis", end="")
        for i, (name, rss) in enumerate(self.items):
            text.append(name.removesuffix(".exe"), name_style)
            text.append(f" · {human_bytes(rss)}", size_style)
            if i < len(self.items) - 1:
                text.append("\n")
        return text


class Meter(Vertical):
    """Painel de uma métrica: nome + valor (topo), gráfico e detalhe."""

    def __init__(self, name, unit, **kwargs):
        super().__init__(classes="meter", **kwargs)
        self.metric = name
        self.unit = unit

    def compose(self) -> ComposeResult:
        with Horizontal(classes="meter-head"):
            yield Label(self.metric, classes="meter-name")
            yield Label("—", classes="meter-value")
        yield BarChart(leveled=self.unit == "%", classes="meter-chart")
        yield Label("", classes="meter-detail", markup=False)

    def update_values(self, history, detail=""):
        values = list(history)
        current = values[-1] if values else 0
        if self.unit == "%":
            top, text = 100.0, f"{current:.0f}%"
            level = sprites.load_level(current)
        else:  # rede: escala pelo pico recente (mín. 1 MB/s)
            top, text = max([NET_MIN_TOP, *values]), human_rate(current)
            level = "baixa"
        self.query_one(".meter-value", Label).update(text)
        for cls in ("-baixa", "-moderada", "-alta"):
            self.remove_class(cls)
        self.add_class(f"-{level}")
        self.query_one(".meter-chart", BarChart).set_values(values, top)
        self.query_one(".meter-detail", Label).update(detail)


class StatusScreen(JarvisScreen):
    BADGE = "STATUS"
    HEADLINE = "Diagnóstico do sistema"

    BINDINGS = [Binding("p", "pause", "Pausar")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.paused = False
        self._details = {}

    def body(self) -> ComposeResult:
        with Horizontal(id="status-body"):
            with Grid(id="status-grid"):
                for name, unit in METERS:
                    yield Meter(name, unit, id=f"meter-{name.lower()}")
            with Vertical(id="status-side"):
                yield Label("núcleo · carga", classes="hint")
                with Center(id="status-orb-box"):
                    yield PixelSprite(sprites.sprite("core_orb"), id="status-orb")
                yield Label("—", id="status-level")
                yield Label("top processos", classes="hint", id="status-procs-title")
                yield ProcessList(id="status-procs")
                yield Static(id="status-gap")
                yield Label(self._threshold_text(), id="status-threshold", classes="hint")

    def status_hint(self):
        interval = num(settings.TELEMETRY_INTERVAL)
        return "pausado · p retoma" if self.paused else f"atualiza a cada {interval} s"

    def _threshold_text(self):
        thresholds = getattr(state.sys_monitor, "thresholds", None)
        limit = _number(thresholds.get("cpu_max")) if isinstance(thresholds, dict) else None
        return f"limiar crítico: {limit or 90:.0f}%"

    def on_mount(self):
        super().on_mount()
        self.refresh_data()
        self.set_interval(settings.TELEMETRY_INTERVAL, self._tick)
        self._load_details()

    def _tick(self):
        if not self.paused:
            self.refresh_data()
            self._load_details()

    def action_pause(self):
        self.paused = not self.paused
        self._refresh_statusline()
        if not self.paused:
            self._tick()

    def refresh_data(self):
        history = getattr(self.app, "telemetry_history", {})
        details = self._details
        down, up = getattr(self.app, "last_net", (0.0, 0.0))
        texts = {
            "CPU": details.get("CPU", ""),
            "RAM": details.get("RAM", ""),
            "GPU": details.get("GPU", ""),
            "REDE": net_detail(down, up),
        }
        for name, _unit in METERS:
            self.query_one(f"#meter-{name.lower()}", Meter).update_values(history.get(name, ()), texts[name])
        loads = [list(history.get(n, ()))[-1] for n in ("CPU", "RAM", "GPU") if history.get(n)]
        level = sprites.load_level(max(loads) if loads else 0)
        self.query_one("#status-orb", PixelSprite).set_frames(
            sprites.sprite("core_orb", recolor={sprites.NEON: _ORB_COLOR[level]}))
        label = self.query_one("#status-level", Label)
        label.update(_LEVEL_LABEL[level])
        for cls in ("-baixa", "-moderada", "-alta"):
            label.remove_class(cls)
        label.add_class(f"-{level}")
        slots = self.query_one("#meter-cpu .meter-chart", BarChart).slots
        samples = min(len(history.get("CPU", ())), slots) or slots
        self.query_one("#session-title", Static).update(
            f"{self.HEADLINE} · {window_label(samples, settings.TELEMETRY_INTERVAL)}")

    @work(thread=True, group="status-details", exclusive=True)
    def _load_details(self):
        mon = state.sys_monitor
        info = {}
        try:
            info = mon.get_dashboard_details(TOP_PROCESSES)
            info = dict(info) if isinstance(info, dict) else {}
            general = mon.get_system_general()
            uptime = general.get("uptime") if isinstance(general, dict) else None
            info["uptime"] = uptime if isinstance(uptime, str) else ""
        except Exception as e:
            log.debug(f"Detalhes do /status indisponíveis: {e}")
        self.app.call_from_thread(self._apply_details, info)

    def _apply_details(self, info):
        self._details = dashboard_texts(info)
        self.query_one("#status-procs", ProcessList).set_items(top_processes(info))
        uptime = _uptime_text(info.get("uptime"))
        self.set_info(f"uptime {uptime}" if uptime else "")
        self.refresh_data()


def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def dashboard_texts(info):
    """Detalhes de CPU/RAM/GPU em pt-BR a partir de get_dashboard_details()."""
    details = {}
    if not isinstance(info, dict):
        return details
    cores, ghz = _number(info.get("cores")), _number(info.get("freq_ghz"))
    if cores:
        details["CPU"] = f"{cores:.0f} núcleos" + (f" · {num(ghz)} GHz" if ghz else "")
    used, total = _number(info.get("ram_used_gb")), _number(info.get("ram_total_gb"))
    if total:
        details["RAM"] = f"{num(used or 0)} / {num(total)} GB"
    name = info.get("gpu_name")
    if isinstance(name, str) and name:
        vram_used, vram_total = _number(info.get("vram_used_gb")), _number(info.get("vram_total_gb"))
        vram = f" · VRAM {num(vram_used or 0)} / {num(vram_total)} GB" if vram_total else ""
        details["GPU"] = name.replace("NVIDIA GeForce ", "") + vram
    return details


def top_processes(info):
    items = info.get("top_memory") if isinstance(info, dict) else None
    if not isinstance(items, (list, tuple)):
        return []
    return [(n, b) for n, b in (tuple(i) for i in items if isinstance(i, (list, tuple)) and len(i) == 2)
            if isinstance(n, str) and _number(b) is not None]


def _uptime_text(raw):
    """'1 day, 2:03:04' / '4:52:12' → '26:03:04' / '04:52:12'."""
    if not raw:
        return ""
    raw = str(raw)
    days = 0
    if "day" in raw:
        head, _, raw = raw.partition(",")
        days = int(head.split()[0])
    try:
        h, m, s = (int(float(x)) for x in raw.strip().split(":"))
    except ValueError:
        return raw
    return format_uptime(days * 86400 + h * 3600 + m * 60 + s)
