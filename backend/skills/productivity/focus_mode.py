"""Skill FOCUS_MODE — Pomodoro e Não Perturbe por voz (services.focus).

Frases óbvias são entendidas sem LLM (`parse_fast`); o resto vai ao Ollama com
`skills/focus_mode_decision.md` (JSON). Os anúncios de fase saem do próprio
FocusManager; aqui só volta a confirmação curta da ação.
"""
import json
import re

from core.llm import query_ollama
from core.logger import log
from core.prompts import load_prompt

INTENT = "FOCUS_MODE"
PROMPT_TEXT = load_prompt("skills/focus_mode.md")

ACTIONS = {"start", "stop", "skip", "status", "dnd_on", "dnd_off"}

_NUMBER_WORDS = {"meia hora": 30, "uma hora": 60, "1 hora": 60, "duas horas": 120, "2 horas": 120}
_MINUTES_RE = re.compile(r"(\d{1,3})\s*(min|minuto|minutos|m\b)", re.I)
_HOURS_RE = re.compile(r"(\d{1,2})\s*(h\b|hora|horas)", re.I)


def parse_minutes(text):
    """'foco de 50 minutos' -> 50; 'por 1 hora' -> 60; 'meia hora' -> 30; nada -> None."""
    low = (text or "").lower()
    for words, minutes in _NUMBER_WORDS.items():
        if words in low:
            return minutes
    match = _MINUTES_RE.search(low)
    if match:
        return int(match.group(1))
    match = _HOURS_RE.search(low)
    if match:
        return int(match.group(1)) * 60
    return None


def parse_fast(command):
    """Decisão sem LLM para as frases óbvias. None = deixa para o modelo."""
    low = (command or "").lower()
    minutes = parse_minutes(low)
    dnd = "perturbe" in low or "notifica" in low
    if any(w in low for w in ("quanto falta", "quanto tempo falta", "como está o foco")):
        return {"action": "status", "minutes": None}
    if any(w in low for w in ("pula", "pular", "próxima fase", "proxima fase")):
        return {"action": "skip", "minutes": None}
    if any(w in low for w in ("desliga", "desativa", "encerra", "para o", "pare o", "termina", "cancela")):
        return {"action": "dnd_off" if dnd and "foco" not in low and "pomodoro" not in low else "stop",
                "minutes": None}
    if "pomodoro" in low or "foco" in low:
        return {"action": "start", "minutes": minutes}
    if dnd:
        return {"action": "dnd_on", "minutes": minutes}
    return None


def _ask_llm(command):
    raw = query_ollama([{"role": "system", "content": load_prompt("skills/focus_mode_decision.md")},
                        {"role": "user", "content": command}], format="json", temperature=0)
    try:
        decision = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return None
    if decision.get("action") not in ACTIONS:
        return None
    minutes = decision.get("minutes")
    decision["minutes"] = int(minutes) if isinstance(minutes, (int, float)) and minutes > 0 else None
    return decision


def decide(command):
    decision = parse_fast(command)
    if decision is None:
        try:
            decision = _ask_llm(command)
        except Exception as e:
            log.error(f"FOCUS_MODE: falha ao consultar o modelo: {e}")
            decision = None
    return decision


def run(decision, manager=None):
    """Executa a decisão no FocusManager e devolve o texto da resposta."""
    if manager is None:
        from services.focus import focus as manager
    return manager.apply(decision["action"], decision.get("minutes"))


def execute(entity, command):
    decision = decide(command or entity)
    if decision is None:
        return "Não entendi o pedido de foco, Senhor. Tente 'inicia um pomodoro' ou 'não perturbe por 1 hora'."
    if not decision.get("minutes"):
        decision["minutes"] = parse_minutes(entity) if entity else None
    return run(decision)
