"""YouTube sem API key: achar o vídeo de uma busca e limpar títulos de aba.

`find_video(query)` lê a página de resultados do próprio YouTube e pega o 1º
`videoId` (`parse_results_html`). Se ela falhar, tenta a busca de vídeos do
DuckDuckGo (`ddgs`, já usado pela WEB_SEARCH, instável: DNSError intermitente).
Sem vídeo ou sem rede → abre a página de resultados. Nunca levanta.
"""
import json
import re
import time
from urllib.parse import quote_plus

from core.logger import log
from core.utils import TTLCache

HOME_URL = "https://www.youtube.com"
RESULTS_URL = "https://www.youtube.com/results?search_query="
MAX_RESULTS = 8
_VIDEO_RE = re.compile(r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?|shorts/)|youtu\.be/)", re.I)
_SUFFIX_RE = re.compile(r"\s+[-–—]\s+YouTube\b.*$", re.I)
_COUNT_RE = re.compile(r"^\(\d+\+?\)\s*")  # "(3) Título" = notificações
# 1º vídeo da página de resultados (o JSON ytInitialData vem embutido no HTML)
_RENDERER_RE = re.compile(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":("(?:[^"\\]|\\.)*")',
                          re.S)
WATCH_URL = "https://www.youtube.com/watch?v="
# Cliente genérico (sem dado do usuário), como o core/web.py
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JARVIS/1.0", "Accept-Language": "pt-BR"}

_cache = TTLCache(maxsize=32, ttl=600)


def results_url(query):
    return RESULTS_URL + quote_plus((query or "").strip())


def is_video_url(url):
    return bool(_VIDEO_RE.match(url or ""))


def pick_video(results):
    """1º resultado que é vídeo do YouTube → (url, título) ou None."""
    for item in results or []:
        url = item.get("content") or item.get("url") or item.get("href") or ""
        if is_video_url(url):
            return url, (item.get("title") or "").strip()
    return None


def parse_results_html(html):
    """HTML de youtube.com/results → (url do 1º vídeo, título) ou None."""
    m = _RENDERER_RE.search(html or "")
    if not m:
        return None
    try:
        title = json.loads(m.group(2))
    except ValueError:
        title = ""
    return WATCH_URL + m.group(1), title.strip()


def _from_results_page(query):
    try:
        import requests

        from core.config import settings
        res = requests.get(results_url(query), headers=_HEADERS, timeout=settings.TIMEOUT_API)
        return parse_results_html(res.text) if res.status_code == 200 else None
    except Exception as e:
        log.warning(f"[YOUTUBE] Página de resultados indisponível: {e}")
        return None


def _from_ddgs(query):
    # Mesmo contorno do core/web.search: o ddgs falha ~1 em 3 com DNSError intermitente.
    from core.web import SEARCH_BACKENDS, SEARCH_RETRY_PAUSE_S
    for attempt, backend in enumerate(SEARCH_BACKENDS):
        if attempt:
            time.sleep(SEARCH_RETRY_PAUSE_S)
        try:
            from ddgs import DDGS  # import tardio
            found = pick_video(DDGS().videos(f"{query} youtube", region="br-pt", max_results=MAX_RESULTS,
                                             backend=backend))
        except Exception as e:
            log.warning(f"[YOUTUBE] Busca de vídeo falhou ({backend}): {e}")
            found = None
        if found:
            return found
    return None


def find_video(query):
    """(url, título | None): o vídeo achado ou, sem vídeo, a página de resultados."""
    query = (query or "").strip()
    if not query:
        return HOME_URL, None
    cached = _cache.get(query.lower())
    if cached:
        return cached
    found = _from_results_page(query) or _from_ddgs(query)
    result = found or (results_url(query), None)
    if found:
        _cache.set(query.lower(), result)
    return result


def clean_title(title):
    """'(2) Lo-fi beats - YouTube - Opera' → 'Lo-fi beats'."""
    title = _COUNT_RE.sub("", (title or "").strip())
    return _SUFFIX_RE.sub("", title).strip()


def is_youtube_title(title):
    return bool(_SUFFIX_RE.search(title or "")) or (title or "").strip().lower() == "youtube"
