"""Dados reais injetados no prompt do chat quando a pergunta precisa deles.

Rede de segurança do Chat: quando o classificador não roteia para a skill
CALENDAR (cai em CHAT), "o que tenho amanhã?" iria direto ao LLM, que inventava
compromissos. Aqui detectamos (sem LLM,
por palavras-chave) que a mensagem é sobre a agenda, buscamos os eventos de
verdade no Google Agenda e montamos um bloco de sistema com a instrução de
responder SÓ com eles — ou de dizer que a agenda não está conectada.

Funções puras + uma chamada ao `core.google_calendar`. Nunca levanta.
"""
import datetime
import re
import unicodedata

from core.logger import log
from core.prompts import load_prompt

# Palavras que indicam pergunta sobre compromissos (comparadas sem acento)
_CALENDAR_RE = re.compile(
    r"\b(agenda|compromissos?|reunia[oõ]|reunioes|eventos?|marcad[oa]s?|agendad[oa]s?|"
    r"calendario|consulta marcada|tenho (algo|alguma coisa|hoje|amanha)|o que tenho|"
    r"estou (livre|ocupado)|to (livre|ocupado)|meu dia|horarios? livres?)\b"
)


def _plain(text):
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def is_calendar_question(text):
    return bool(_CALENDAR_RE.search(_plain(text)))


def format_events_for_llm(items):
    """Uma linha por evento: '- 09:00–10:00 Daily' / '- dia inteiro: Feriado'."""
    lines = []
    for e in items:
        if e["all_day"] or not e["start"]:
            lines.append(f"- dia inteiro: {e['title']}")
        elif e.get("end") and e["end"].date() == e["start"].date():
            lines.append(f"- {e['start']:%H:%M}–{e['end']:%H:%M} {e['title']}")
        else:
            lines.append(f"- {e['start']:%H:%M} {e['title']}")
    return "\n".join(lines) or "(nenhum evento)"


def calendar_context(text, today=None, calendar=None):
    """Bloco de sistema com a agenda real, ou '' se a mensagem não é sobre agenda."""
    if not is_calendar_question(text):
        return ""
    if calendar is None:
        from core import google_calendar as calendar
    today = today or datetime.date.today()
    day, label = calendar.resolve_day(text, today)
    if day == "next":
        day, label = today, "hoje"
    date_txt = f"{label} ({day:%d/%m/%Y}, {calendar.WEEKDAYS[day.weekday()]})"

    if not (calendar.is_configured() and calendar.is_connected()):
        status, events = "NÃO CONECTADA", "(sem acesso à agenda)"
    else:
        try:
            status, events = "CONECTADA", format_events_for_llm(calendar.events(day))
        except Exception as e:
            log.warning(f"[CONTEXTO] Agenda indisponível: {e}")
            status, events = "INDISPONÍVEL AGORA", f"(erro ao consultar: {e})"
    log.info(f"[CONTEXTO] Agenda {status} para {date_txt} injetada no prompt.")
    return load_prompt("calendar_context.md", status=status, day=date_txt, events=events)


def build(text):
    """Todos os blocos de contexto ao vivo para a mensagem (hoje: só a agenda)."""
    try:
        return calendar_context(text)
    except Exception as e:
        log.warning(f"[CONTEXTO] Falhou ao montar contexto ao vivo: {e}")
        return ""
