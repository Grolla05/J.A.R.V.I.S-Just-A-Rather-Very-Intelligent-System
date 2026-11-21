"""Skill SCREEN_READ — "explica o erro na minha tela", "resolve a questão aberta".

Pipeline sem modelo de visão (decisão: o modelo de texto faz tudo o que puder):
captura da janela-alvo ou do monitor (`core.screen_capture`, só em memória) →
OCR nativo do Windows (`core.ocr`, 0 VRAM) → segredos mascarados → o tipo do
texto (`core.clipboard.classify`) escolhe o prompt: erro → explain_error.md,
código → explain_code.md, resto → screen_read.md (com o pedido do usuário) →
resposta em stream do OLLAMA_MODEL.

Tela sem texto legível: avisa e sugere o /attach — interpretar imagem ainda não
é suportado (fica para a Thinking Layer).
"""
import re

from core import ocr, screen_capture
from core.config import settings
from core.logger import log
from core.prompts import load_prompt

INTENT = "SCREEN_READ"
PROMPT_TEXT = load_prompt("skills/screen_read.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("tela", "telas", "janela*", "monitor*", "print", "printscreen", "aberto", "aberta",
            "questao", "questoes", "exercicio*")

MIN_OCR_CHARS = 20
NO_TEXT_REPLY = ("Não encontrei texto legível nessa janela, Senhor. Por enquanto eu leio só texto da tela "
                 "(código, erro, documento, questão); interpretar imagem ainda não está disponível. "
                 "Se for uma imagem, anexe com `/attach`.")
NO_CAPTURE_REPLY = "Não consegui capturar a tela, Senhor. Há alguma janela aberta além de mim?"
CUT_MARK = "\n[texto cortado]"

_MONITOR_RE = re.compile(r"\bmonitor\s*(\d)\b")
_WHOLE_RE = re.compile(r"\b(tela\s+(inteira|toda|cheia)|toda\s+a\s+tela|monitor)\b")

# Pontos de injeção para os testes.
capture = screen_capture.capture
recognize = ocr.recognize


def ask(messages):
    from core.llm import query_ollama_stream
    return query_ollama_stream(messages, temperature=0.3)


def scope_for(entity, command):
    """('window'|'monitor', índice do monitor ou None) a partir da frase."""
    text = f"{entity or ''} {command or ''}".lower()
    match = _MONITOR_RE.search(text)
    if match:
        return "monitor", int(match.group(1))
    if _WHOLE_RE.search(text):
        return "monitor", None
    return "window", None


def clip_text(text, limit=None):
    """Corta no limite (SCREEN_TEXT_MAX), no fim de uma linha, com aviso."""
    limit = limit or settings.SCREEN_TEXT_MAX
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if "\n" in cut:
        cut = cut[: cut.rfind("\n")]
    return cut + CUT_MARK


def build_prompt(text, command, window):
    """Prompt do modelo de texto conforme o tipo do que foi lido."""
    from core.clipboard import MAX_CHARS, classify
    kind = classify(text[:MAX_CHARS])
    note = "(O trecho foi lido da tela por OCR e pode ter erros de leitura.)"
    if kind in ("error", "code"):
        question = f"Pedido do usuário: {command}\n{note}" if command else note
        name = "explain_error.md" if kind == "error" else "explain_code.md"
        return load_prompt(name, snippet=text, question=question)
    return load_prompt("screen_read.md", text=text, question=command or "explique o que está na tela",
                       window=window or "desconhecida")


def execute(entity, command=""):
    scope, monitor_idx = scope_for(entity, command)
    image, window = capture(scope=scope, monitor_idx=monitor_idx)
    if image is None:
        return NO_CAPTURE_REPLY
    text = ocr.mask_secrets(recognize(image))
    log.info(f"👁️ [SCREEN_READ] {scope} '{window}': {len(text)} caracteres lidos")
    if len(text.strip()) < MIN_OCR_CHARS:
        return NO_TEXT_REPLY
    prompt = build_prompt(clip_text(text), command, window)
    return ask([{"role": "user", "content": prompt}])
