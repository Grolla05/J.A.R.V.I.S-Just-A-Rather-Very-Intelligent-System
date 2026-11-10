"""Skill CALENDAR — compromissos do Google Agenda (core.google_calendar).

O dia sai de `google_calendar.resolve_day` (hoje, amanhã, depois de amanhã, dia
da semana, "próxima reunião" — regras simples, sem LLM). Só leitura.
"""
from core import google_calendar
from core.prompts import load_prompt

INTENT = "CALENDAR"
PROMPT_TEXT = load_prompt("skills/calendar.md")


def execute(entity, command):
    if not google_calendar.is_configured():
        return google_calendar.NOT_CONFIGURED
    if not google_calendar.is_connected():
        return google_calendar.NOT_CONNECTED
    day, label = google_calendar.resolve_day(f"{entity or ''} {command or ''}")
    try:
        if day == "next":
            event = google_calendar.next_event()
            if not event:
                return "Nenhum compromisso pela frente hoje, Senhor."
            return f"Próximo compromisso: **{event['title']}** às {event['start']:%H:%M}."
        return google_calendar.format_events(google_calendar.events(day), label)
    except google_calendar.CalendarError as e:
        return str(e)
