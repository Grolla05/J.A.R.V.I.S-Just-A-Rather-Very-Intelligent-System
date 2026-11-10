"""Manchetes do briefing a partir das fontes escolhidas pelo usuário.

As fontes são um texto livre separado por vírgula (/config → SISTEMA), guardado
na chave `news_sources` da tabela `config`. Cada nome vira uma busca:
- nome conhecido (G1, BBC, CNN, NYT, WSJ, SciELO, Google Acadêmico) → `site:<domínio>`;
- algo com cara de domínio (`exemplo.com`) → `site:` direto;
- "DOI" / "artigos com DOI" → artigos recentes com DOI registrado no Crossref;
- qualquer outro nome → busca "<nome> notícias hoje".

`headlines()` pega uma manchete por fonte até o limite; a fonte inicial gira a
cada dia, para todas aparecerem mesmo com mais fontes que manchetes. Nunca levanta.
"""
import datetime
import re
import unicodedata

from core.config import settings
from core.logger import log

CONFIG_KEY = "news_sources"
DEFAULT_SOURCES = "G1, BBC, CNN, New York Times, Wall Street Journal, SciELO, Google Acadêmico, DOI"
MAX_SOURCES = 12
CROSSREF_URL = "https://api.crossref.org/works"

KNOWN = {
    "g1": "g1.globo.com",
    "bbc": "bbc.com",
    "cnn": "cnn.com",
    "cnn brasil": "cnnbrasil.com.br",
    "new york times": "nytimes.com",
    "the new york times": "nytimes.com",
    "nyt": "nytimes.com",
    "wall street journal": "wsj.com",
    "the wall street journal": "wsj.com",
    "wsj": "wsj.com",
    "scielo": "scielo.org",
    "google academico": "scholar.google.com",
    "google academy": "scholar.google.com",
    "google scholar": "scholar.google.com",
}
_DOI_NAMES = {"doi", "artigos com doi", "artigo com doi", "artigos doi", "crossref"}
_DOMAIN_RE = re.compile(r"^(?:https?://)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)/?$", re.I)


def _plain(text):
    text = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def parse_sources(text):
    """'G1, BBC ,, g1' → ['G1', 'BBC'] (sem vazios nem repetidos, no máx. MAX_SOURCES)."""
    seen, out = set(), []
    for part in (text or "").split(","):
        name = " ".join(part.split())
        key = _plain(name)
        if name and key not in seen:
            seen.add(key)
            out.append(name)
    return out[:MAX_SOURCES]


def normalize(text):
    """Texto limpo para gravar/mostrar ('G1, BBC'); vazio → padrão."""
    return ", ".join(parse_sources(text)) or DEFAULT_SOURCES


def resolve(name):
    """('doi', None) | ('site', domínio) | ('query', texto) para uma fonte."""
    key = _plain(name)
    if key in _DOI_NAMES:
        return "doi", None
    if key in KNOWN:
        return "site", KNOWN[key]
    match = _DOMAIN_RE.match(name.strip())
    if match:
        return "site", match.group(1).lower()
    return "query", f"{name} notícias hoje"


# ------------------------------------------------------------- persistência
def _db():
    from core.database import db
    return db


def get_sources(db=None):
    try:
        raw = (db or _db()).get_config(CONFIG_KEY)
    except Exception as e:
        log.debug(f"[NEWS] Fontes indisponíveis no banco: {e}")
        raw = None
    return normalize(raw if isinstance(raw, str) else "")


def save_sources(text, db=None):
    """Grava as fontes normalizadas e devolve o texto gravado."""
    value = normalize(text)
    (db or _db()).save_config(CONFIG_KEY, value)
    return value


# ------------------------------------------------------------------ busca
def doi_articles(limit=2, today=None, get=None):
    """Artigos de periódico publicados desde ontem com DOI (Crossref). Falha → []."""
    since = ((today or datetime.date.today()) - datetime.timedelta(days=1)).isoformat()
    params = {"sort": "published", "order": "desc", "rows": limit,
              "filter": f"from-pub-date:{since},type:journal-article", "select": "DOI,title"}
    try:
        if get is None:
            import requests
            get = requests.get
        res = get(CROSSREF_URL, params=params, timeout=settings.TIMEOUT_API)
        items = res.json().get("message", {}).get("items", []) if res.status_code == 200 else []
    except Exception as e:
        log.warning(f"[NEWS] Crossref falhou: {e}")
        return []
    out = []
    for item in items:
        doi = item.get("DOI")
        title = " ".join((item.get("title") or [""])[0].split())
        if doi and title:
            out.append(f"{title} (doi.org/{doi})")
    return out


def _search(name, search):
    kind, value = resolve(name)
    if kind == "doi":
        return doi_articles()
    query = f"notícias hoje site:{value}" if kind == "site" else value
    return [r["title"] for r in search(query, max_results=2) if r.get("title")]


def headlines(sources=None, limit=4, search=None, today=None):
    """Uma manchete por fonte até `limit` (completa com a 2ª de cada se faltar).
    A ordem começa numa fonte diferente a cada dia. Fonte que falha é pulada."""
    if search is None:
        from core.web import search
    sources = parse_sources(get_sources()) if sources is None else list(sources)
    if sources:
        start = (today or datetime.date.today()).toordinal() % len(sources)
        sources = sources[start:] + sources[:start]
    pools = []
    for name in sources:
        if len(pools) >= limit:
            break
        try:
            titles = _search(name, search)
        except Exception as e:
            log.warning(f"[NEWS] Fonte '{name}' falhou: {e}")
            titles = []
        if titles:
            pools.append(list(titles))
    out = []
    while len(out) < limit and any(pools):
        for pool in pools:
            if pool and len(out) < limit:
                out.append(pool.pop(0))
    return out
