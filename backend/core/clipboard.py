"""Clipboard inteligente: leitura, classificação, monitor em background e ações.

- `read()`: texto do clipboard via PowerShell `Get-Clipboard` (sem dependência nova).
- `classify(text)`: "url" | "code" | "english" | None — heurísticas puras.
- `ClipboardMonitor`: thread daemon que observa o clipboard e chama
  `on_suggest(kind, text)` para conteúdo novo e relevante. Só sugere — o LLM
  roda apenas quando o usuário pede (`act`, via /clip ou skill CLIPBOARD).
- Privacidade: o conteúdo copiado nunca vai para o log (só tipo e tamanho).
"""
import hashlib
import re
import subprocess
import threading
from collections import deque

from core.logger import log
from core.prompts import load_prompt

MIN_CHARS = 20
MAX_CHARS = 20_000
POLL_INTERVAL = 1.5  # s
HISTORY_SIZE = 20

KINDS = ("code", "english", "url")
# Ação padrão por tipo e os verbos aceitos em /clip <ação>
DEFAULT_ACTION = {"code": "explain", "english": "translate", "url": "summarize"}
ACTION_ALIASES = {
    "explicar": "explain", "explica": "explain", "explain": "explain",
    "traduzir": "translate", "traduz": "translate", "translate": "translate",
    "resumir": "summarize", "resume": "summarize", "summarize": "summarize",
}
SUGGESTION = {
    "code": "Copiou código — `/clip` para eu explicar.",
    "english": "Copiou texto em inglês — `/clip` para traduzir.",
    "url": "Copiou um link — `/clip` para eu resumir a página.",
}

_URL_RE = re.compile(r"^https?://\S+$", re.I)
_CODE_KEYWORDS = re.compile(
    r"^\s*(def |class |import |from \S+ import|function |const |let |var |public |private |"
    r"#include|using |package |return\b|if\s*\(|for\s*\(|while\s*\(|SELECT |CREATE |<\w+[ >])",
    re.M,
)
_EN_WORDS = {"the", "and", "is", "are", "of", "to", "in", "that", "it", "with", "for", "this",
             "you", "was", "be", "have", "not", "on", "as", "by", "from", "or", "can", "will"}
_PT_WORDS = {"o", "a", "os", "as", "de", "do", "da", "que", "e", "é", "em", "um", "uma", "para",
             "com", "não", "por", "se", "mais", "como", "mas", "na", "no", "dos", "das"}


def read():
    """Texto atual do clipboard ('' se vazio/erro)."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return (result.stdout or "").strip()
    except Exception as e:
        log.debug(f"[CLIPBOARD] Leitura falhou: {e}")
        return ""


def classify(text):
    """Tipo do conteúdo copiado, ou None se não vale sugerir nada."""
    text = (text or "").strip()
    if _URL_RE.match(text):
        return "url"
    if not (MIN_CHARS <= len(text) <= MAX_CHARS):
        return None
    lines = text.splitlines()
    symbols = sum(text.count(c) for c in "{};()=<>[]")
    indented = sum(1 for ln in lines if ln.startswith(("    ", "\t")))
    if _CODE_KEYWORDS.search(text) and (symbols >= 3 or indented):
        return "code"
    if len(lines) > 1 and symbols / max(len(text), 1) > 0.05:
        return "code"
    words = re.findall(r"[a-zà-ú']+", text.lower())
    if len(words) >= 5:
        en = sum(w in _EN_WORDS for w in words)
        pt = sum(w in _PT_WORDS for w in words)
        if en >= 2 and en > pt * 1.5:
            return "english"
    return None


def resolve_action(kind, requested=""):
    """Ação pedida (/clip traduzir) ou a padrão do tipo detectado."""
    requested = (requested or "").strip().lower()
    if requested:
        return ACTION_ALIASES.get(requested)
    return DEFAULT_ACTION.get(kind, "explain")


def act(action, text):
    """Executa a ação sobre o texto copiado e devolve Markdown."""
    text = (text or "").strip()
    if not text:
        return "O clipboard está vazio, Senhor. Copie algo primeiro."
    if action == "summarize" and _URL_RE.match(text):
        from core import web
        page = web.fetch_text(text)
        if not page:
            return f"Não consegui ler a página {text}, Senhor."
        return web.summarize(f"Resuma esta página: {text}", [{"title": text, "url": text, "text": page}])
    prompts = {"explain": "clipboard_explain.md", "translate": "clipboard_translate.md",
               "summarize": "clipboard_summarize.md"}
    if action not in prompts:
        return "Ação desconhecida. Use: explicar, traduzir ou resumir."
    from core.llm import query_ollama
    prompt = load_prompt(prompts[action], text=text[:MAX_CHARS])
    answer = query_ollama([{"role": "user", "content": prompt}], temperature=0.3)
    return answer.strip() if answer else "O modelo não respondeu agora, Senhor."


def _digest(text):
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()


class ClipboardMonitor:
    """Observa o clipboard numa thread daemon e sugere ações para conteúdo novo."""

    def __init__(self, on_suggest, read_fn=read, interval=POLL_INTERVAL):
        self.on_suggest = on_suggest
        self.read_fn = read_fn
        self.interval = interval
        self.history = deque(maxlen=HISTORY_SIZE)  # [(kind, text)] mais novo à direita
        self._last = None
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        with self._lock:
            if self.running:
                return
            self._stop.clear()
            # O que já estava copiado antes de ligar não gera sugestão
            current = self.read_fn()
            self._last = _digest(current) if current else None
            self._thread = threading.Thread(target=self._loop, name="jarvis-clipboard", daemon=True)
            self._thread.start()
        log.info("[CLIPBOARD] Monitor ligado.")

    def stop(self):
        with self._lock:
            self._stop.set()
            thread, self._thread = self._thread, None
        if thread and thread is not threading.current_thread():
            thread.join(timeout=self.interval + 1)
        if thread:
            log.info("[CLIPBOARD] Monitor desligado.")

    def check_once(self):
        """Uma leitura; devolve o tipo sugerido (ou None). Usado pelo loop e nos testes."""
        text = self.read_fn()
        if not text:
            return None
        digest = _digest(text)
        if digest == self._last:
            return None
        self._last = digest
        kind = classify(text)
        if not kind:
            return None
        self.history.append((kind, text))
        log.debug(f"[CLIPBOARD] Novo conteúdo: {kind}, {len(text)} caracteres")
        try:
            self.on_suggest(kind, text)
        except Exception as e:
            log.warning(f"[CLIPBOARD] Callback de sugestão falhou: {e}")
        return kind

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                self.check_once()
            except Exception as e:
                log.debug(f"[CLIPBOARD] Erro no monitor: {e}")
