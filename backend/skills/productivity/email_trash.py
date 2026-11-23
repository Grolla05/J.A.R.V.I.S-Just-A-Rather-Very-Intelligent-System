# ⚠️ ACESSO SENSÍVEL: move e-mails do Gmail para a Lixeira (recuperáveis por 30 dias);
# só depois de confirmação explícita, com a lista dos e-mails à vista. Nunca exclui de vez.
"""Skill EMAIL_TRASH — "apaga o e-mail 3", "apaga as promoções" → Lixeira do Gmail (services.email_trash)."""
from core.prompts import load_prompt
from services import email_trash

INTENT = "EMAIL_TRASH"
PROMPT_TEXT = load_prompt("skills/email_trash.md")
KEYWORDS = ("apag*", "exclu*", "delet*", "lixeira", "joga fora", "remov*", "email*", "e-mail*")


def execute(entity, command):
    return email_trash.request(f"{entity or ''} {command or ''}".strip())
