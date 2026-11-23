"""Skill CALENDAR — compromissos do Google Agenda (core.google_calendar).

O período sai de `google_calendar.resolve_period` (regras simples, sem LLM):
dia (hoje, amanhã, depois de amanhã, dia da semana), semana, fim de semana, mês,
ano — e os próximos ("semana que vem", "próximo mês") — ou "próxima reunião". Só leitura.
"""
from core import google_calendar
from core.prompts import load_prompt

INTENT = "CALENDAR"
PROMPT_TEXT = load_prompt("skills/calendar.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("agenda", "compromisso*", "reuni*", "evento*", "livre", "ocupad*", "amanha", "hoje", "semana", "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo", "calendario", "mes", "ano", "fim de semana", "marcad*")


def execute(entity, command):
    if not google_calendar.is_configured():
        return google_calendar.NOT_CONFIGURED
    if not google_calendar.is_connected():
        return google_calendar.NOT_CONNECTED
    period = google_calendar.resolve_period(f"{entity or ''} {command or ''}")
    try:
        if period["kind"] == "next":
            event = google_calendar.next_event()
            if not event:
                return "Nenhum compromisso pela frente hoje, Senhor."
            return f"Próximo compromisso: **{event['title']}** às {event['start']:%H:%M}."
        if period["kind"] == "range":
            items = google_calendar.events_range(period["start"], period["end"])
            return google_calendar.format_range(items, period["label"], period["start"], period["end"])
        return google_calendar.format_events(google_calendar.events(period["start"]), period["label"])
    except google_calendar.CalendarError as e:
        return str(e)
