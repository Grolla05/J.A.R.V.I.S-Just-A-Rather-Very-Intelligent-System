# ⚠️ ACESSO SENSÍVEL: altera a caixa do Gmail (arquiva, marca como lido, aplica marcadores);
# só depois de confirmação explícita. Nunca apaga mensagens.
"""Skill EMAIL_ORGANIZE — organiza a caixa de entrada do Gmail com confirmação (services.email_organize)."""
from core.prompts import load_prompt
from services import email_organize, mailbox

INTENT = "EMAIL_ORGANIZE"
PROMPT_TEXT = load_prompt("skills/email_organize.md")
KEYWORDS = ("organiz*", "arrum*", "limp*", "email*", "e-mail*", "caixa de entrada", "inbox")


def execute(entity, command):
    problem = mailbox.ready()
    if problem:
        return problem
    return email_organize.organize()
