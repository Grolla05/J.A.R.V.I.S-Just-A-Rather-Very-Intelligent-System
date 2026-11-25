"""Skill HEADLESS_TASK — "entra no site da kabum e vê o preço da rtx 5060".

O modelo planeja passos tipados, o Edge roda sem janela (core/headless.py) e o
resultado chega por aviso. Passo que envia algo pede confirmação antes
(services/headless_tasks.py).
"""
from core.prompts import load_prompt

INTENT = "HEADLESS_TASK"
PROMPT_TEXT = load_prompt("skills/headless_task.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("site", "sites", "segundo plano", "headless", "naveg*", "entra no", "entra na", "acess*", "pagina")


def execute(entity, command):
    from services import headless_tasks
    return headless_tasks.request(command or entity or "")
