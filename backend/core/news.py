"""Manchetes do briefing a partir das fontes escolhidas pelo usuário.

As fontes são um texto livre separado por vírgula (/config → SISTEMA), guardado
na chave `news_sources` da tabela `config`. Cada nome vira uma fonte:
- nome conhecido (G1, BBC, CNN, NYT, WSJ, SciELO, Google Acadêmico) → `site:<domínio>`;
- algo com cara de domínio (`exemplo.com`) → `site:` direto;
- "DOI" / "artigos com DOI" → artigos recentes com DOI registrado no Crossref;
- qualquer outro nome → busca "<nome> notícias hoje".

`headlines()` traz UMA notícia por fonte — a mais relevante entre as últimas
(morte, bolsa em queda, guerra, desastre… pesam mais; empate → a mais nova).
Fontes conhecidas com RSS (`FEEDS`) leem o feed; as demais usam a busca e
descartam títulos de página inicial ("g1 - O portal de notícias da Globo").
As fontes rodam em paralelo. Nunca levanta.
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
# RSS oficial por domínio: dá a manchete do dia em vez do título da página inicial.
FEEDS = {
    "g1.globo.com": "https://g1.globo.com/rss/g1/",
    "bbc.com": "https://feeds.bbci.co.uk/news/rss.xml",
    "cnnbrasil.com.br": "https://www.cnnbrasil.com.br/feed/",
    "nytimes.com": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "wsj.com": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
}
MAX_AGE_H = 48     # notícia mais velha que isso não entra (feed parado cai na busca)
FEED_WINDOW = 15   # só as N primeiras do feed (as mais novas) disputam a relevância

# Assuntos que pesam (palavras sem acento, minúsculas): (peso, {palavras}).
_RELEVANT = (
    (3, {"morre", "morreu", "morte", "mortos", "morto", "mortes", "falece", "faleceu", "luto", "assassinado",
         "dies", "died", "dead", "death", "killed", "deaths"}),
    (3, {"guerra", "ataque", "atentado", "bombardeio", "invasao", "terremoto", "tsunami", "furacao",
         "explosao", "tiroteio", "tragedia", "enchente", "war", "attack", "strike", "invasion", "earthquake",
         "hurricane", "explosion", "shooting", "flood"}),
    (2, {"bolsa", "ibovespa", "acoes", "dolar", "juros", "selic", "inflacao", "recessao", "stocks", "shares",
         "market", "markets", "dow", "nasdaq", "inflation", "recession", "rates", "fed", "tarifa", "tariffs"}),
    (2, {"queda", "despenca", "desaba", "dispara", "recorde", "crise", "colapso", "plunge", "plunges",
         "tumble", "soar", "surge", "record", "crisis", "collapse", "crash"}),
    (1, {"presidente", "eleicao", "eleicoes", "stf", "congresso", "governo", "urgente", "president",
         "election", "congress", "government", "breaking"}),
)
_PORTAL_WORDS = {"portal", "noticias", "news", "home", "homepage", "inicial", "ultimas", "headlines",
                 "latest", "breaking", "videos", "jornal", "journal", "online", "library",
                 "biblioteca", "scholar", "academico"}
_DOMAIN_NOISE = {"www", "com", "br", "org", "net", "co", "uk", "gov"}
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




# ------------------------------------------------------------ RSS e relevância
def fetch_feed(url, get=None):
    """[(título, datetime|None)] de um RSS/Atom, na ordem do feed. Falha → []."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    try:
        if get is None:
            import requests
            get = requests.get
        res = get(url, timeout=settings.TIMEOUT_API, headers={"User-Agent": "JARVIS/1.0"})
        if res.status_code != 200:
            return []
        root = ET.fromstring(res.content)
    except Exception as e:
        log.warning(f"[NEWS] Feed {url} falhou: {e}")
        return []
    out = []
    for item in root.iter():
        tag = item.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        title, when = "", None
        for child in item:
            ctag = child.tag.rsplit("}", 1)[-1]
            text = (child.text or "").strip()
            if ctag == "title":
                title = " ".join(text.split())
            elif ctag in ("pubDate", "published", "updated") and text and when is None:
                try:
                    when = parsedate_to_datetime(text)
                except (TypeError, ValueError):
                    try:
                        when = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
                    except ValueError:
                        when = None
        if title:
            out.append((title, when))
    return out


def relevance(title):
    """Peso do assunto: morte, mercado em queda/alta, guerra, desastre, eleição…"""
    words = set(re.findall(r"\w+", _plain(title)))
    return sum(weight for weight, keys in _RELEVANT if words & keys)


def _is_portal_title(title, name, domain=None):
    """Título de página inicial ('g1 - O portal de notícias da Globo', 'U.S. News - WSJ.com')."""
    head = re.split(r"\s+[-|–—·:]\s+", _plain(title))[0]
    words = head.split()
    if len(words) < 3:
        return True
    brands = {_plain(name)}
    if domain:
        brands |= {p for p in domain.split(".") if p not in _DOMAIN_NOISE}
    return words[0] in brands or head in brands or any(w in words for w in _PORTAL_WORDS)


def pick_relevant(titles, now=None, max_age_h=MAX_AGE_H):
    """Manchete mais relevante entre as recentes; empate → a mais nova (1ª do feed).
    `titles`: [(título, datetime|None)]. Itens sem data contam como recentes."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    fresh = []
    for title, when in titles[:FEED_WINDOW]:
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=datetime.timezone.utc)
            if (now - when).total_seconds() > max_age_h * 3600:
                continue
        fresh.append(title)
    if not fresh:
        return None
    return max(enumerate(fresh), key=lambda it: (relevance(it[1]), -it[0]))[1]


def _top_for(name, search, get=None):
    """A notícia mais relevante de uma fonte, ou None."""
    kind, value = resolve(name)
    if kind == "doi":
        articles = doi_articles(limit=1)
        return articles[0] if articles else None
    feed = FEEDS.get(value) if kind == "site" else None
    if feed:  # item de feed sem data não prova que é de hoje → fica de fora
        best = pick_relevant([it for it in fetch_feed(feed, get=get) if it[1] is not None])
        if best:
            return clean_title(best, name, value)
    query = f"notícias hoje site:{value}" if kind == "site" else value
    domain = value if kind == "site" else None
    titles = [r["title"] for r in search(query, max_results=5)
              if r.get("title") and not _is_portal_title(r["title"], name, domain)]
    best = pick_relevant([(t, None) for t in titles])
    return clean_title(best, name, domain) if best else None


def clean_title(title, name, domain=None):
    """Tira o sufixo do portal: 'Algo aconteceu - WSJ' → 'Algo aconteceu'."""
    parts = re.split(r"\s+[-|–—]\s+", title.strip())
    if len(parts) > 1:
        brands = {_plain(name)} | ({domain} if domain else set())
        if domain:
            brands |= {p for p in domain.split(".") if p not in _DOMAIN_NOISE}
        last = _plain(parts[-1])
        if last in brands or any(b and b in last.split(".") for b in brands):
            return " - ".join(parts[:-1])
    return title.strip()


def headlines(sources=None, search=None, get=None):
    """[(fonte, manchete)] — a última notícia mais relevante de cada fonte, na
    ordem configurada. As fontes rodam em paralelo; a que falha é pulada."""
    from concurrent.futures import ThreadPoolExecutor
    if search is None:
        from core.web import search
    sources = parse_sources(get_sources()) if sources is None else list(sources)
    if not sources:
        return []

    def one(name):
        try:
            return _top_for(name, search, get=get)
        except Exception as e:
            log.warning(f"[NEWS] Fonte '{name}' falhou: {e}")
            return None

    with ThreadPoolExecutor(max_workers=min(6, len(sources))) as pool:
        results = list(pool.map(one, sources))
    return [(name, title) for name, title in zip(sources, results) if title]
