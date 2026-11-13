"""Briefing diário: saudação, clima, computador, GitHub, agenda, trânsito e notícias.

`collect()` junta as fontes — cada uma isolada em try, uma falha não derruba o
resto. `to_markdown()` monta o texto em seções fixas (um tema por bloco, cada
item numa linha); `build()` só pede ao Ollama uma frase de fecho no tom do
JARVIS — o corpo nunca passa pelo LLM, para a formatação não se perder.
`should_run_today()/mark_ran()` controlam o automático (1º boot do dia) pela
chave `briefing_last_date` da tabela `config`.
"""
import datetime
import time

from core.logger import log
from core.prompts import load_prompt

LAST_DATE_KEY = "briefing_last_date"
NET_SAMPLE_S = 1.0  # janela da amostra de rede (o briefing roda em worker de thread)
BR = "  \n"         # quebra de linha dura no Markdown (o Textual respeita)


def _today():
    return datetime.date.today().isoformat()


def should_run_today(db=None):
    db = db or _db()
    try:
        return db.get_config(LAST_DATE_KEY) != _today()
    except Exception as e:
        log.debug(f"[BRIEFING] Data do último briefing indisponível: {e}")
        return True


def mark_ran(db=None):
    (db or _db()).save_config(LAST_DATE_KEY, _today())


def _db():
    from core.database import db
    return db


# ------------------------------------------------------------------ fontes
def _user_name():
    try:
        from core.obsidian import obsidian
        return obsidian.get_memory("apelido") or obsidian.get_memory("nome") or "Senhor"
    except Exception:
        return "Senhor"


def format_rate(bps):
    """Bytes/s → '1.2 MB/s' (base 1024, como o /status)."""
    value = max(0.0, float(bps or 0))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}/s" if unit == "B" else f"{value:.1f} {unit}/s"
        value /= 1024
    return f"{value:.1f} GB/s"


def _net_rate(sample_s=NET_SAMPLE_S):
    """Taxa de rede própria (não mexe nos contadores do SystemInfo)."""
    import psutil
    first = psutil.net_io_counters()
    time.sleep(sample_s)
    second = psutil.net_io_counters()
    down = (second.bytes_recv - first.bytes_recv) / sample_s
    up = (second.bytes_sent - first.bytes_sent) / sample_s
    return f"↓ {format_rate(down)} · ↑ {format_rate(up)}"


def _computer():
    """{'cpu', 'ram', 'gpu', 'net', 'battery'} — item ausente = None."""
    import core.state as state
    monitor = state.sys_monitor
    info = {"cpu": f"{monitor.get_cpu_usage()}%", "ram": f"{monitor.get_ram_usage()['percent']}%",
            "gpu": None, "net": None, "battery": None}
    try:
        gpu = monitor.get_gpu_info()
        if gpu.get("name") and "N/A" not in gpu["name"]:
            info["gpu"] = f"{gpu.get('load', 0)}%" + (f" · {gpu['temp']}°C" if gpu.get("temp") else "")
    except Exception as e:
        log.debug(f"[BRIEFING] GPU indisponível: {e}")
    try:
        info["net"] = _net_rate()
    except Exception as e:
        log.debug(f"[BRIEFING] Rede indisponível: {e}")
    batt = monitor.get_battery_status()
    if batt and batt.get("percent") is not None and batt.get("time_left") != "Desktop":
        info["battery"] = f"{batt['percent']}%" + (" (na tomada)" if batt.get("plugged") else "")
    return info


def _news():
    """[(fonte, manchete)] — a mais relevante de cada fonte de /config → SISTEMA."""
    from core import news
    return news.headlines()


def collect(include_news=False, now=None):
    """Dados do briefing. Chave ausente/None = fonte indisponível."""
    from core import github_client, google_calendar, traffic
    from core.weather import get_time_greeting, get_weather_context

    now = now or datetime.datetime.now()
    sources = {
        "greeting": lambda: get_time_greeting(_user_name(), now),
        "weather": get_weather_context,
        "computer": _computer,
        "github": github_client.summary,
        "agenda": lambda: google_calendar.summary(now.date()),
    }
    if now.weekday() < 5:
        sources["traffic"] = lambda: traffic.commute_line(now)
    if include_news:
        sources["news"] = _news
    data = {"date": now.strftime("%d/%m/%Y"), "weekday": _WEEKDAYS[now.weekday()]}
    for key, fn in sources.items():
        try:
            data[key] = fn()
        except Exception as e:
            log.warning(f"[BRIEFING] Fonte '{key}' falhou: {e}")
            data[key] = None
    return data


_WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


# ------------------------------------------------------------------ texto
def _section(title, lines):
    lines = [line for line in lines if line]
    return f"**{title}:**{BR}" + BR.join(lines) if lines else None


def _computer_lines(info):
    if not info:
        return []
    labels = (("cpu", "CPU"), ("ram", "RAM"), ("gpu", "GPU"), ("net", "INTERNET"), ("battery", "BATERIA"))
    return [f"{label} → {info[key]}" for key, label in labels if info.get(key)]


def to_markdown(data):
    """Briefing em seções fixas: saudação, Clima, Computador, GitHub, Agenda,
    Trânsito e Manchetes — um tema por bloco, cada item na sua linha."""
    head = f"**{data.get('greeting') or 'Bom dia.'}** {data['weekday'].capitalize()}, {data['date']}."
    news_lines = [f"- **{source}:** {title}" for source, title in (data.get("news") or [])]
    blocks = [
        head,
        _section("Clima", [data.get("weather")]),
        _section("Computador", _computer_lines(data.get("computer"))),
        _section("GitHub", [data.get("github")]),
        _section("Agenda", [data.get("agenda")]),
        _section("Trânsito", [data.get("traffic")]),
        "**Manchetes e últimas notícias:**\n\n" +"\n".join(news_lines) if news_lines else None,
    ]
    return "\n\n".join(b for b in blocks if b)


def build(data):
    """Corpo fixo + frase de fecho do LLM (sem LLM, só o corpo)."""
    facts = to_markdown(data)
    try:
        from core.llm import query_ollama
        prompt = load_prompt("briefing.md", facts=facts)
        closing = query_ollama([{"role": "user", "content": prompt}], temperature=0.5)
    except Exception as e:
        log.warning(f"[BRIEFING] Fecho do LLM indisponível: {e}")
        closing = None
    closing = " ".join((closing or "").split())
    return f"{facts}\n\n{closing}" if closing else facts


def generate(include_news=False):
    return build(collect(include_news=include_news))
