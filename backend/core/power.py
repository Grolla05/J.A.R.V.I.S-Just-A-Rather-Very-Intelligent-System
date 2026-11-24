"""Consumo de energia em tempo real: GPU medida + estimativa do resto.

Desktop não tem sensor do consumo total. Aqui:
- GPU NVIDIA: watts reais do `nvidia-smi` (power.draw); sem ele, GPU entra como 0;
- CPU: estimativa pela carga × TDP (`POWER_CPU_TDP_W`), com 15 % parado;
- resto (placa-mãe, RAM, discos, ventoinhas): base fixa `POWER_BASE_W`;
- tudo dividido pela eficiência da fonte (`POWER_PSU_EFF`) = o que sai da tomada.

`meter` (singleton) integra W × tempo em kWh por dia e grava em
`config.power_daily` (últimos `KEEP_DAYS` dias). Quem alimenta é a telemetria
da TUI (a cada TELEMETRY_INTERVAL); com a TUI fechada nada é contado.
Funções puras e leituras injetáveis: os testes não chamam nvidia-smi nem banco.
"""
import shutil
import subprocess
import threading
import time
from datetime import date, datetime, timedelta

from .config import settings
from .logger import log

CREATE_NO_WINDOW = 0x08000000
GPU_CACHE_S = 3.0      # o tick da telemetria é 3 s: uma chamada ao nvidia-smi por tick
GPU_TIMEOUT_S = 2
CPU_IDLE_FRACTION = 0.15
MAX_GAP_S = 60.0       # intervalo maior (PC suspenso, TUI travada) não vira consumo
SAVE_EVERY_S = 300.0
KEEP_DAYS = 31
CONFIG_KEY = "power_daily"

_gpu_cache = {"at": 0.0, "value": None, "missing": False}


def parse_power_draw(output):
    """Soma o power.draw (W) de todas as GPUs; linha '[N/A]' ou vazia → ignorada."""
    total, found = 0.0, False
    for line in (output or "").splitlines():
        try:
            total += float(line.strip())
            found = True
        except ValueError:
            continue
    return round(total, 1) if found else None


def gpu_watts(run=None, which=shutil.which, now=time.monotonic):
    """Watts da GPU NVIDIA (None sem nvidia-smi ou sem leitura). Cache de GPU_CACHE_S."""
    t = now()
    if _gpu_cache["missing"] or t - _gpu_cache["at"] < GPU_CACHE_S:
        return _gpu_cache["value"]
    _gpu_cache["at"] = t
    exe = which("nvidia-smi")
    if not exe:
        _gpu_cache.update(missing=True, value=None)
        return None
    run = run or subprocess.run
    try:
        result = run([exe, "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                     capture_output=True, text=True, timeout=GPU_TIMEOUT_S, creationflags=CREATE_NO_WINDOW)
        value = parse_power_draw(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError) as e:
        log.debug(f"[POWER] nvidia-smi falhou: {e}")
        value = None
    _gpu_cache["value"] = value
    return value


def estimate(cpu_load, gpu_w=None, tdp=None, base=None, eff=None):
    """{'total', 'cpu', 'gpu', 'base', 'gpu_real'} em watts (tomada)."""
    tdp = settings.POWER_CPU_TDP_W if tdp is None else tdp
    base = settings.POWER_BASE_W if base is None else base
    eff = settings.POWER_PSU_EFF if eff is None else eff
    load = min(max(float(cpu_load or 0), 0.0), 100.0) / 100
    cpu = tdp * (CPU_IDLE_FRACTION + (1 - CPU_IDLE_FRACTION) * load)
    gpu = float(gpu_w) if gpu_w is not None else 0.0
    eff = eff if 0 < eff <= 1 else 1.0
    total = (base + cpu + gpu) / eff
    return {"total": round(total, 1), "cpu": round(cpu, 1), "gpu": round(gpu, 1),
            "base": round(base, 1), "gpu_real": gpu_w is not None}


def cost(kwh, tariff=None):
    tariff = settings.POWER_TARIFF_KWH if tariff is None else tariff
    return round(kwh * tariff, 2)


def brl(value):
    return f"R$ {value:.2f}".replace(".", ",")


def kwh_text(kwh):
    return f"{kwh:.2f} kWh".replace(".", ",")


def _db_load():
    from core import db
    data = db.get_config(CONFIG_KEY)
    return data if isinstance(data, dict) else {}


def _db_save(data):
    from core import db
    db.save_config(CONFIG_KEY, data)


class PowerMeter:
    """Integra amostras de watts em kWh por dia (thread-safe)."""

    def __init__(self, load=_db_load, save=_db_save):
        self._load, self._save = load, save
        self._lock = threading.Lock()
        self._daily = None
        self._last_at = None     # datetime da última amostra
        self._saved_at = None
        self.last = None         # último estimate() recebido

    def _ensure(self):
        if self._daily is None:
            try:
                self._daily = {k: float(v) for k, v in (self._load() or {}).items()}
            except Exception as e:
                log.debug(f"[POWER] histórico indisponível: {e}")
                self._daily = {}

    def add(self, reading, now=None):
        """`reading` = dict do estimate() (ou watts). Integra desde a amostra anterior."""
        now = now or datetime.now()
        watts = reading["total"] if isinstance(reading, dict) else float(reading)
        with self._lock:
            self._ensure()
            self.last = reading if isinstance(reading, dict) else {"total": watts}
            prev, self._last_at = self._last_at, now
            if prev is None:
                self._saved_at = now
                return
            gap = (now - prev).total_seconds()
            if gap <= 0 or gap > MAX_GAP_S:
                return
            midnight = datetime.combine(now.date(), datetime.min.time())
            if prev < midnight:  # amostra atravessou a meia-noite: divide
                self._accumulate(prev.date(), watts, (midnight - prev).total_seconds())
                self._accumulate(now.date(), watts, (now - midnight).total_seconds())
            else:
                self._accumulate(now.date(), watts, gap)
            if (now - self._saved_at).total_seconds() >= SAVE_EVERY_S:
                self._flush_locked(now)

    def _accumulate(self, day, watts, seconds):
        key = day.isoformat()
        self._daily[key] = self._daily.get(key, 0.0) + watts * seconds / 3_600_000

    def _flush_locked(self, now):
        cutoff = (now.date() - timedelta(days=KEEP_DAYS)).isoformat()
        self._daily = {k: v for k, v in self._daily.items() if k > cutoff}
        self._saved_at = now
        try:
            self._save({k: round(v, 4) for k, v in self._daily.items()})
        except Exception as e:
            log.debug(f"[POWER] não gravou o histórico: {e}")

    def flush(self, now=None):
        with self._lock:
            if self._daily is not None:
                self._flush_locked(now or datetime.now())

    def day_kwh(self, day=None):
        with self._lock:
            self._ensure()
            return self._daily.get((day or date.today()).isoformat(), 0.0)

    def month_kwh(self, today=None):
        today = today or date.today()
        prefix = today.strftime("%Y-%m-")
        with self._lock:
            self._ensure()
            return sum(v for k, v in self._daily.items() if k.startswith(prefix))


meter = PowerMeter()


def read_now(cpu_load=None):
    """Leitura na hora (fora da telemetria da TUI: voz, briefing, chat)."""
    if cpu_load is None:
        import psutil
        cpu_load = psutil.cpu_percent(interval=0.3)
    return estimate(cpu_load, gpu_watts())


def current():
    """Última amostra da telemetria; sem ela, mede agora."""
    return meter.last or read_now()


def reading_text(reading):
    gpu = f"GPU {reading['gpu']:.0f} W {'medidos' if reading.get('gpu_real') else '(sem leitura)'}"
    return f"~{reading['total']:.0f} W na tomada (CPU ~{reading['cpu']:.0f} W estimados · {gpu})"


def summary_text(reading=None):
    """Resumo falado/escrito: agora, hoje e mês com custo."""
    reading = reading or current()
    today, month = meter.day_kwh(), meter.month_kwh()
    return (f"Consumo agora: {reading_text(reading)}. "
            f"Hoje: {kwh_text(today)} ({brl(cost(today))}). "
            f"Este mês: {kwh_text(month)} ({brl(cost(month))}), tarifa {brl(settings.POWER_TARIFF_KWH)}/kWh. "
            "Estimativa: só a GPU é medida; conta enquanto o JARVIS está aberto.")
