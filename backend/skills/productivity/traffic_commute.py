"""Skill TRAFFIC — tempo casa ⇄ trabalho agora (core.traffic). Sem LLM."""
from core import traffic
from core.prompts import load_prompt

INTENT = "TRAFFIC"
PROMPT_TEXT = load_prompt("skills/traffic.md")


def execute(entity, command):
    return traffic.commute_text()
