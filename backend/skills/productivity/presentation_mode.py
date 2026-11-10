"""Skill PRESENTATION_MODE — liga/desliga o Modo Apresentação (services.presentation). Sem LLM."""
from core.prompts import load_prompt
from services import presentation

INTENT = "PRESENTATION_MODE"
PROMPT_TEXT = load_prompt("skills/presentation_mode.md")

_OFF_WORDS = ("desliga", "desativa", "sai do", "saia do", "encerra", "termina", "acabou", "pode voltar",
              "pode falar", "fim da apresenta", "volta a falar", "volte a falar")
_STATUS_WORDS = ("está ligado", "esta ligado", "está ativo", "esta ativo", "status")


def decide(entity, command):
    """'on' | 'off' | 'status' a partir da frase (e da entity do classificador)."""
    low = f"{entity or ''} {command or ''}".lower()
    if any(w in low for w in _STATUS_WORDS):
        return "status"
    if any(w in low for w in _OFF_WORDS) or (entity or "").strip().lower() in ("off", "desligar"):
        return "off"
    return "on"


def execute(entity, command):
    action = decide(entity, command)
    if action == "status":
        return presentation.status()
    return presentation.set_manual(action == "on")
