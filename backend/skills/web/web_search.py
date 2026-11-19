"""Skill WEB_SEARCH — pesquisa na web e resume com fontes (core.web)."""
from core import web
from core.prompts import load_prompt

INTENT = "WEB_SEARCH"
PROMPT_TEXT = load_prompt("skills/web_search.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("pesquis*", "busc*", "procur*", "google", "internet", "noticia*", "preco*", "versao", "versoes", "resultado*", "o que dizem", "atual*")


def execute(entity, command):
    return web.research(entity or command)
