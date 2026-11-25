# ⚠️ ACESSO SENSÍVEL: abre o Edge e preenche formulários com dados pessoais do perfil
# (Obsidian, conta Google, /rota). Envio só com "sim"; senha, cartão e CPF nunca.
# Ver SECURITY.md.
"""Skill FORM_FILL — "preenche esse formulário".

Abre o formulário (link da frase ou aba aberta) numa janela do Edge, preenche com o
perfil (Obsidian, conta Google, /rota) e para antes do envio: só envia com "sim"
(services/form_fill.py). Senha, cartão, CPF e afins nunca são preenchidos.
"""
from core.prompts import load_prompt

INTENT = "FORM_FILL"
PROMPT_TEXT = load_prompt("skills/form_fill.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("formulario*", "preench*", "cadastro", "inscricao", "inscricoes", "form", "forms", "complet*")


def execute(entity, command):
    from services import form_fill
    text = command or ""
    if entity and entity not in text:
        text = f"{text} {entity}"
    return form_fill.request(text)
