"""Skill INSIGHT_SAVE — "anota essa ideia: …" grava no caderno de ideias do vault.

A ideia é o que vem depois do pedido (`strip_request`, sem LLM); o modelo só dá o
título curto (`insights.extract`) e o texto fica nas palavras do usuário. O registro é
do `services.insights` (nota mensal em 🧠 Brainstorms, fila se o Obsidian estiver fora).
"""
import re

from core.prompts import load_prompt

INTENT = "INSIGHT_SAVE"
PROMPT_TEXT = load_prompt("skills/insight_note.md")

_REQUEST_RE = re.compile(
    r"^\s*(jarvis[,!.]?\s+)?"
    r"((tive|tenho)\s+uma\s+ideia[,.:;]?\s*(e\s+)?)?"
    r"((por favor[,]?\s+)?(anot[ae]|registr[ae]|salv[ae]|guard[ae]|grav[ae])\b[\s:,\-–—]*)?"
    r"(a[íi]\b[\s:,]*)?"
    # o artigo só sai junto com o substantivo: "anota um app…" mantém "um app…"
    r"(((ess[ae]|est[ae]|a|o|um|uma|minha|meu)\s+)?(ideia|insight|brainstorm|nota|pensamento|sacada)\b\s*)?"
    r"(de\s+que\s+|que\s+|sobre\s+)?[:,\-–—]?\s*",
    re.I,
)


def strip_request(command):
    """'anota essa ideia: um app de X' -> 'um app de X'."""
    text = (command or "").strip()
    return _REQUEST_RE.sub("", text, count=1).strip() if text else ""


def execute(entity, command):
    from services import insights
    idea = strip_request(command)
    if len(idea) < 10:
        idea = (entity or "").strip() if len((entity or "").strip()) >= 10 else ""
    if not idea:
        return "Qual é a ideia, Senhor? Diga, por exemplo: 'anota essa ideia: um painel para a casa'."
    idea = idea[0].upper() + idea[1:]
    # Título curto pelo modelo ("Modo viagem"), conteúdo nas palavras do próprio usuário.
    # Sem resposta do modelo, a 1ª frase vira o título — o pedido foi explícito, grava de qualquer jeito.
    found = insights.extract(idea)
    if found:
        try:
            return insights.reply_for(insights.save(found["title"], idea, "pedido direto"), found["title"])
        except ValueError:
            pass
    return insights.save_text(idea, origin="pedido direto")
