"""Skill WEB_WATCH — "vigia o preço desse link", "me avisa quando sair release do dono/repo",
"o que você está vigiando", "para de vigiar o 2".

Quem guarda e checa é o `services.web_watch` (tabela `web_watches`); o aviso sai
pelo tick da TUI. Sem link na frase, usa a URL da aba aberta no navegador.
"""
import re

from core.prompts import load_prompt

INTENT = "WEB_WATCH"
PROMPT_TEXT = load_prompt("skills/web_watch.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("vigi*", "monitor*", "acompanh*", "preco*", "release*", "repositorio*", "repo", "avis*")

_LIST_RE = re.compile(r"\b(quais|que|o que|lista|listar|mostra|mostrar|tenho|ver)\b.*\b(vigi\w*|monitor\w*|acompanh\w*)",
                      re.I)
_REMOVE_RE = re.compile(r"\b(para\s+de|pare\s+de|parar\s+de|cancel\w*|remov\w*|apag\w*|exclu\w*|deix\w*\s+de)\b"
                        r".*?\b(vigi\w*|monitor\w*|acompanh\w*)\b\D*(\d+)?", re.I)


def _active_url():
    """URL da aba ativa do navegador (topo da ordem Z), ou '' sem navegador aberto."""
    from core import browser
    win = browser.find_browser_window()
    return browser.active_url(win) if win else ""


def execute(entity, command):
    from services import web_watch
    text = (command or entity or "").strip()
    match = _REMOVE_RE.search(text)
    if match:
        if not match.group(3):
            return "Qual item, Senhor? Diga o número — 'o que você está vigiando' lista todos."
        return web_watch.remove_text(int(match.group(3)))
    if _LIST_RE.search(text) and "http" not in text:
        return web_watch.list_text()
    return web_watch.create_from_text(text, url_fallback=_active_url)
