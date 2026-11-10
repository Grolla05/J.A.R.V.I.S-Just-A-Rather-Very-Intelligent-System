"""Briefing diário: saudação, clima, agenda, trânsito, máquina, arquivos recentes, GitHub e notícias.

`collect()` junta as fontes — cada uma isolada em try, uma falha não derruba o
resto. `build()` pede ao Ollama um texto curto no tom do JARVIS; sem LLM, monta
uma lista em Markdown. `should_run_today()/mark_ran()` controlam o automático
(1º boot do dia) pela chave `briefing_last_date` da tabela `config`.
"""
import datetime
import os
from pathlib import Path

from core.config import settings
from core.logger import log
from core.prompts import load_prompt

LAST_DATE_KEY = "briefing_last_date"
RECENT_HOURS = 24
RECENT_LIMIT = 5
SCAN_DEPTH = 2         # pastas abaixo de cada raiz
SCAN_MAX_ENTRIES = 4000  # teto de itens visitados (briefing não pode travar o boot)
_SKIP_DIRS = {"node_modules", "__pycache__", "venv", ".venv", "site-packages", "AppData", "$RECYCLE.BIN"}


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
def briefing_dirs():
    raw = settings.BRIEFING_DIRS
    if raw:
        return [Path(p.strip()).expanduser() for p in raw.split(";") if p.strip()]
    home = Path.home()
    return [home / "Desktop", home / "Documents", home / "Downloads"]


def recent_files(dirs=None, hours=RECENT_HOURS, limit=RECENT_LIMIT, now=None):
    """Arquivos modificados nas últimas `hours` horas, mais novos primeiro."""
    cutoff = (now or datetime.datetime.now()).timestamp() - hours * 3600
    found, visited = [], 0
    stack = [(Path(d), 0) for d in (dirs if dirs is not None else briefing_dirs())]
    while stack and visited < SCAN_MAX_ENTRIES:
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            visited += 1
            name = entry.name
            if name.startswith((".", "~$")) or name in _SKIP_DIRS:
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth < SCAN_DEPTH:
                        stack.append((Path(entry.path), depth + 1))
                elif entry.is_file(follow_symlinks=False):
                    mtime = entry.stat().st_mtime
                    if mtime >= cutoff:
                        found.append((mtime, entry.path))
            except OSError:
                continue
    found.sort(reverse=True)
    return [Path(p) for _, p in found[:limit]]


def _user_name():
    try:
        from core.obsidian import obsidian
        return obsidian.get_memory("apelido") or obsidian.get_memory("nome") or "Senhor"
    except Exception:
        return "Senhor"


def _system_line():
    import core.state as state
    monitor = state.sys_monitor
    cpu = monitor.get_cpu_usage()
    ram = monitor.get_ram_usage()
    batt = monitor.get_battery_status()
    line = f"CPU {cpu}%, RAM {ram['percent']}%"
    if batt and batt.get("percent") is not None and batt.get("time_left") != "Desktop":
        line += f", bateria {batt['percent']}%" + (" (na tomada)" if batt.get("plugged") else "")
    return line


def _news(limit=4):
    from core import web
    return [r["title"] for r in web.search("principais notícias do Brasil hoje", max_results=limit) if r["title"]]


def collect(include_news=False, now=None):
    """Dados do briefing. Chave ausente/None = fonte indisponível."""
    from core import github_client, google_calendar, traffic
    from core.weather import get_time_greeting, get_weather_context

    now = now or datetime.datetime.now()
    sources = {
        "greeting": lambda: get_time_greeting(_user_name(), now),
        "weather": get_weather_context,
        "agenda": lambda: google_calendar.summary(now.date()),
        "system": _system_line,
        "files": lambda: [p.name for p in recent_files(now=now)],
        "github": github_client.summary,
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
def to_markdown(data):
    """Briefing montado sem LLM (também é o insumo do prompt)."""
    lines = [f"**{data.get('greeting') or 'Bom dia.'}** {data['weekday'].capitalize()}, {data['date']}.", ""]
    if data.get("weather"):
        lines.append(f"- **Clima:** {data['weather']}")
    if data.get("agenda"):
        lines.append(f"- **Agenda:** {data['agenda']}")
    if data.get("traffic"):
        lines.append(f"- **Trânsito:** {data['traffic']}")
    if data.get("system"):
        lines.append(f"- **Sistema:** {data['system']}")
    if data.get("github"):
        lines.append(f"- **GitHub:** {data['github']}")
    files = data.get("files")
    if files:
        lines.append(f"- **Arquivos mexidos nas últimas 24 h:** {', '.join(files)}")
    elif files is not None:
        lines.append("- **Arquivos:** nada modificado nas últimas 24 h.")
    if data.get("news"):
        lines.append("- **Manchetes:** " + " · ".join(data["news"]))
    return "\n".join(lines)


def build(data):
    from core.llm import query_ollama
    facts = to_markdown(data)
    prompt = load_prompt("briefing.md", facts=facts)
    answer = query_ollama([{"role": "user", "content": prompt}], temperature=0.5)
    return answer.strip() if answer else facts


def generate(include_news=False):
    return build(collect(include_news=include_news))
