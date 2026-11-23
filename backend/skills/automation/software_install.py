"""Skill SOFTWARE_INSTALL — busca e instala/baixa software pelo winget, sempre com confirmação.

Categoria automation: só no Copilot/voz (nunca pelo Chat nem pela ponte Telegram/Discord).
"""
from core.prompts import load_prompt
from services import software

INTENT = "SOFTWARE_INSTALL"
PROMPT_TEXT = load_prompt("skills/software_install.md")
KEYWORDS = ("instal*", "baix*", "download*", "winget", "instalador")


def execute(entity, command):
    action, name = software.parse_command(command)
    return software.request((entity or "").strip() or name, action=action)
