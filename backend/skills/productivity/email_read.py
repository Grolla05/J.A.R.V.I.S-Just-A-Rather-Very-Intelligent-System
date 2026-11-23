"""Skill EMAIL_READ — e-mails por prioridade e resumo de um e-mail (services.mailbox).

"quais são meus e-mails mais urgentes?" → lista numerada (ALTA primeiro).
"leia o e-mail 2" → resumo do corpo pelo modelo (conteúdo tratado como dado).
"""
import re

from core.prompts import load_prompt
from services import mailbox

INTENT = "EMAIL_READ"
PROMPT_TEXT = load_prompt("skills/email_read.md")
KEYWORDS = ("email*", "e-mail*", "inbox", "caixa de entrada", "mensage*", "gmail")

_READ_RE = re.compile(r"\b(le|leia|ler|abre|abra|abrir|resum\w*|mostra|o que diz)\b", re.I)


def execute(entity, command):
    text = f"{entity or ''} {command or ''}"
    n = mailbox.number_in(text)
    plain = text.lower().replace("ê", "e").replace("é", "e")
    if n and _READ_RE.search(plain):
        return mailbox.read_text(n)
    return mailbox.priority_text()
