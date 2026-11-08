"""Skill DAILY_BRIEFING — briefing do dia sob pedido (core.briefing)."""
from core import briefing
from core.prompts import load_prompt

INTENT = "DAILY_BRIEFING"
PROMPT_TEXT = load_prompt("skills/daily_briefing.md")


def execute(entity, command):
    from services import user_prefs
    text = briefing.generate(include_news=user_prefs.get("briefing_news"))
    briefing.mark_ran()  # pedido manual conta como o briefing do dia
    return text
