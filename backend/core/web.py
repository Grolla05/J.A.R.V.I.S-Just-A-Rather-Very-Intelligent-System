"""Pesquisa web com sumarização local (DuckDuckGo + Ollama), sem abrir browser.

Fluxo de `research(query)`:
    search (ddgs) → fetch_text das primeiras páginas em paralelo → summarize (LLM)

Tudo aqui é chamado de threads (worker da TUI ou skill no Copilot): nada toca
em widget. Erros de rede viram listas/strings vazias + log, nunca exceção.
"""
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

from core.config import settings
from core.logger import log
from core.prompts import load_prompt
from core.utils import TTLCache

MAX_RESULTS = 5
PAGES_TO_READ = 3
PAGE_CHARS = 6000
CACHE_TTL = 600  # s — repetir a mesma pergunta em 10 min não refaz a busca
# Cliente genérico (sem dados do usuário): alguns sites recusam requests sem UA.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JARVIS/1.0"

_cache = TTLCache(maxsize=32, ttl=CACHE_TTL)

# Tags cujo conteúdo é ruído (menus, scripts, rodapé)
_SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "template"}
# Tags que carregam texto útil
_TEXT_TAGS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "pre", "td", "dd"}


class _TextExtractor(HTMLParser):
    """Extrai o texto de parágrafos/títulos/listas, descartando o ruído."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._capture = 0
        self._buf = []
        self.blocks = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _TEXT_TAGS:
            self._capture += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag in _TEXT_TAGS and self._capture:
            self._capture -= 1
            if not self._capture:
                self._flush()
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()
        if self._skip or not self._capture:
            return
        self._buf.append(data)

    def _flush(self):
        text = " ".join("".join(self._buf).split())
        self._buf = []
        if len(text) >= 25:  # descarta migalhas ("Compartilhar", "Menu"…)
            self.blocks.append(text)


def extract_text(html, max_chars=PAGE_CHARS):
    """HTML → texto corrido dos blocos úteis, cortado em `max_chars`."""
    if not html:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception as e:  # HTML quebrado: fica com o que deu para ler
        log.debug(f"[WEB] HTML malformado: {e}")
    return "\n".join(parser.blocks)[:max_chars]


def search(query, max_results=MAX_RESULTS):
    """Resultados do DuckDuckGo: [{'title', 'url', 'snippet'}]. Falha → []."""
    query = (query or "").strip()
    if not query:
        return []
    try:
        from ddgs import DDGS  # import tardio: só quem pesquisa paga o custo
        raw = DDGS().text(query, region="br-pt", max_results=max_results) or []
    except Exception as e:
        log.warning(f"[WEB] Busca falhou: {e}")
        return []
    results = []
    for item in raw:
        url = item.get("href") or item.get("url") or ""
        if url:
            results.append({"title": item.get("title", ""), "url": url, "snippet": item.get("body", "")})
    return results


def fetch_text(url, max_chars=PAGE_CHARS):
    """Baixa a página e devolve o texto útil. Falha / não-HTML → ''."""
    try:
        import requests
        res = requests.get(url, timeout=settings.TIMEOUT_API, headers={"User-Agent": USER_AGENT})
        if res.status_code != 200:
            log.debug(f"[WEB] {url} → HTTP {res.status_code}")
            return ""
        if "html" not in str(res.headers.get("Content-Type", "html")).lower():
            return ""
        return extract_text(res.text, max_chars)
    except Exception as e:
        log.debug(f"[WEB] Falha ao ler {url}: {e}")
        return ""


def _format_sources(sources):
    parts = []
    for i, src in enumerate(sources, 1):
        body = src.get("text") or src.get("snippet") or ""
        parts.append(f"[{i}] {src.get('title', '')} — {src['url']}\n{body}")
    return "\n\n".join(parts)


def sources_markdown(sources):
    return "\n".join(f"{i}. [{s.get('title') or s['url']}]({s['url']})" for i, s in enumerate(sources, 1))


def summarize(query, sources):
    """Resumo em Markdown com citações [n]. Sem LLM → lista dos trechos."""
    from core.llm import query_ollama
    prompt = load_prompt("web_summarize.md", query=query, sources=_format_sources(sources))
    answer = query_ollama([{"role": "user", "content": prompt}], temperature=0.3)
    if not answer:
        snippets = "\n".join(f"- {s.get('snippet') or s.get('title')}" for s in sources)
        answer = f"Não consegui sumarizar agora, Senhor. Os trechos encontrados:\n\n{snippets}"
    return f"{answer.strip()}\n\n**Fontes**\n{sources_markdown(sources)}"


def research(query):
    """Pesquisa completa: busca, lê as primeiras páginas e sumariza."""
    query = (query or "").strip()
    if not query:
        return "Pesquisar o quê, exatamente, Senhor?"
    cached = _cache.get(query.lower())
    if cached:
        return cached
    results = search(query)
    if not results:
        return "A busca não retornou nada — ou a internet resolveu tirar folga, Senhor."
    top = results[:PAGES_TO_READ]
    with ThreadPoolExecutor(max_workers=PAGES_TO_READ, thread_name_prefix="jarvis-web") as pool:
        texts = list(pool.map(fetch_text, [r["url"] for r in top]))
    sources = [dict(r, text=t) for r, t in zip(top, texts)]
    answer = summarize(query, sources)
    _cache.set(query.lower(), answer)
    return answer
