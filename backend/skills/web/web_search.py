"""Skill WEB_SEARCH — pesquisa na web e resume com fontes (core.web)."""
from core import web
from core.prompts import load_prompt

INTENT = "WEB_SEARCH"
PROMPT_TEXT = load_prompt("skills/web_search.md")


def execute(entity, command):
    return web.research(entity or command)
