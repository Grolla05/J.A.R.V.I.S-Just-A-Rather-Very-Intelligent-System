# ⚠️ ACESSO SENSÍVEL: captura a tela (janela em foco ou monitor) e lê o texto por OCR.
# A imagem fica só em memória, segredos viram [oculto] e o texto vai só ao Ollama local.
# Ver SECURITY.md.
"""Skill SCREEN_READ — "explica o erro na minha tela", "resolve a questão aberta".

Pipeline sem modelo de visão (decisão: o modelo de texto faz tudo o que puder):
captura da janela-alvo ou do monitor (`core.screen_capture`, só em memória) →
OCR nativo do Windows (`core.ocr`, 0 VRAM) → segredos mascarados → o tipo do
texto (`core.clipboard.classify`) escolhe o prompt: erro → explain_error.md,
código → explain_code.md, resto → screen_read.md (com o pedido do usuário) →
resposta em stream do OLLAMA_MODEL.

Navegador (Chromium) em foco: antes do OCR, pega a URL da aba pela UI Automation
(`core.browser`) e baixa a página inteira (`core.web.fetch_text`) — lê também o que
está fora da área visível. Só para URL pública e sem parâmetro com cara de
credencial (`browser.is_fetch_safe`); página logada, vazia ou SPA cai no OCR.

Tela sem texto legível: avisa e sugere o /attach — interpretar imagem ainda não
é suportado (fica para a Thinking Layer).
"""
import re

from core import browser, ocr, screen_capture, web
from core.config import settings
from core.logger import log
from core.prompts import load_prompt

INTENT = "SCREEN_READ"
PROMPT_TEXT = load_prompt("skills/screen_read.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("tela", "telas", "janela*", "monitor*", "print", "printscreen", "aberto", "aberta",
            "questao", "questoes", "exercicio*", "pagina", "paginas", "artigo*", "site")

MIN_OCR_CHARS = 20
MIN_PAGE_CHARS = 400   # menos que isso = página de login, SPA ou bloqueio → OCR
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
target = screen_capture.target_window
page_url = browser.active_url
fetch = web.fetch_text


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


def read_page(win):
    """(url, texto) da aba ativa do navegador-alvo, ou None (vai para o OCR)."""
    if not browser.is_browser(win):
        return None
    url = page_url(win)
    if not url:
        return None
    if not browser.is_fetch_safe(url):
        log.info("👁️ [SCREEN_READ] URL da aba não é pública/segura para baixar de novo; usando OCR")
        return None
    text = ocr.mask_secrets(fetch(url, max_chars=settings.SCREEN_TEXT_MAX) or "")
    if len(text.strip()) < MIN_PAGE_CHARS:
        log.info(f"👁️ [SCREEN_READ] Página com pouco texto ({len(text)} caracteres); usando OCR")
        return None
    return url, text


def build_page_prompt(url, text, command, window):
    return load_prompt("page_read.md", url=url, text=text, window=window or "desconhecida",
                       question=command or "resuma o conteúdo desta página")


def _window_with_process(win):
    if win and "process" not in win:
        win = dict(win, process=browser._process_name(win["hwnd"]))
    return win


def execute(entity, command=""):
    scope, monitor_idx = scope_for(entity, command)
    if scope == "window":
        try:
            win = _window_with_process(target())
            page = read_page(win)
        except Exception as e:
            log.warning(f"[SCREEN_READ] Leitura da página falhou, usando OCR: {e}")
            win, page = None, None
        if page:
            url, text = page
            log.info(f"👁️ [SCREEN_READ] página {url}: {len(text)} caracteres baixados")
            return ask([{"role": "user", "content": build_page_prompt(url, text, command, win.get("title"))}])
    image, window = capture(scope=scope, monitor_idx=monitor_idx)
    if image is None:
        return NO_CAPTURE_REPLY
    text = ocr.mask_secrets(recognize(image))
    log.info(f"👁️ [SCREEN_READ] {scope} '{window}': {len(text)} caracteres lidos")
    if len(text.strip()) < MIN_OCR_CHARS:
        return NO_TEXT_REPLY
    prompt = build_prompt(clip_text(text), command, window)
    return ask([{"role": "user", "content": prompt}])
