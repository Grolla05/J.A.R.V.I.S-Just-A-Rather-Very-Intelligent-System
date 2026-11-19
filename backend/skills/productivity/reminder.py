"""Skill REMINDER — "me lembra em 30 min de…", "quais lembretes tenho", "cancela o lembrete 2".

Criar/listar/remover é do `services.reminders` (tabela `reminders`); quem dispara
na hora é o tick de lembretes da TUI. Horário simples é entendido por regex; o
resto vai ao modelo (`skills/reminder_parse.md`).
"""
import re

from core.prompts import load_prompt

INTENT = "REMINDER"
PROMPT_TEXT = load_prompt("skills/reminder.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("lembr*", "avis*")

_LIST_RE = re.compile(r"\b(quais|que|meus|lista|listar|mostra|mostrar|tenho|ver)\b.*\blembretes?\b", re.I)
_REMOVE_RE = re.compile(r"\b(cancel[ae]r?|remov[ae]r?|apag[ae]r?|exclu[ia]r?|delet[ae]r?)\b.*?\blembretes?\b\D*(\d+)?", re.I)


def execute(entity, command):
    from services import reminders
    text = (command or entity or "").strip()
    match = _REMOVE_RE.search(text)
    if match:
        if not match.group(2):
            return "Qual lembrete, Senhor? Diga o número — 'quais lembretes eu tenho' lista todos."
        return reminders.remove_text(int(match.group(2)))
    if _LIST_RE.search(text):
        return reminders.list_text()
    return reminders.create_from_text(text)
