"""Skill FACT_CHECK — "isso é verdade: …", "checa se …", "é fake que …".

Cruza a afirmação em fontes de domínios diferentes e dá um veredito
(CONFIRMADO / FALSO / IMPRECISO / INCONCLUSIVO) com as fontes. Lógica em `core.factcheck`.
"""
from core.prompts import load_prompt

INTENT = "FACT_CHECK"
PROMPT_TEXT = load_prompt("skills/fact_check.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("verdade", "fake", "mentira", "boato*", "checa*", "cheque", "confer*", "verific*", "fato*")


def execute(entity, command):
    from core import factcheck
    return factcheck.check(command or entity or "")
