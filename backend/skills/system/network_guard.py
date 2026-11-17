"""Skill NETWORK_SCAN — "tem alguém na minha rede?": varredura sob demanda.

Só leitura: aparelhos na rede local, portas expostas e programas falando com a
internet, comparados com a linha de base do vigia (`services.net_guard`). As ações
(encerrar processo, bloquear IP) ficam com o vigia e com `/rede`, sempre com confirmação.
"""
from core.prompts import load_prompt

INTENT = "NETWORK_SCAN"
PROMPT_TEXT = load_prompt("skills/network_guard.md")


def execute(entity, command):
    from services import net_guard
    try:
        return net_guard.scan_text(short=True)
    except Exception as e:
        return f"Não consegui varrer a rede agora, Senhor: {e}"
