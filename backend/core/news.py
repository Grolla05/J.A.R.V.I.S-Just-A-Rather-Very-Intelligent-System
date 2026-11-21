"""Manchetes do briefing a partir das fontes escolhidas pelo usuário.

As fontes são um texto livre separado por vírgula (/config → SISTEMA), guardado
na chave `news_sources` da tabela `config`. Cada nome vira uma fonte:
- nome conhecido (G1, BBC, CNN Brasil, NYT, WSJ, SciELO, Google Acadêmico) → `site:<domínio>`;
- algo com cara de domínio (`exemplo.com`) → `site:` direto;
- "DOI" / "artigos com DOI" → artigos recentes com DOI registrado no Crossref;
- qualquer outro nome → busca "<nome> notícias hoje".

`headlines()` traz UMA notícia por fonte — a mais relevante entre as últimas
(morte, bolsa em queda, guerra, desastre… pesam mais; empate → a mais nova).
A nota casa radicais (`morr*` pega "morreram") e ignora contexto enganoso
("bolsa de estudos" não é mercado). Com a pref `news_ai`, os até 3 melhores
títulos de cada fonte vão numa ÚNICA chamada ao Ollama, que escolhe o mais
importante; sem resposta, fica a nota de palavras.
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
DEFAULT_SOURCES = "G1, BBC, CNN Brasil, New York Times, Wall Street Journal, SciELO, Google Acadêmico, DOI"
MAX_SOURCES = 12
CROSSREF_URL = "https://api.crossref.org/works"

KNOWN = {
    "g1": "g1.globo.com",
    "bbc": "bbc.com",
    "cnn": "cnn.com",  # CNN internacional não tem RSS vivo (parado desde 2023): vai pela busca
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

RERANK_TOP = 3     # títulos por fonte que o Ollama compara no desempate

# Assuntos que pesam (sem acento, minúsculas): (peso, termos). `*` no fim = prefixo
# ("morr*" casa morre/morreu/morreram); sem `*` só a palavra inteira. Curtas ou
# ambíguas ficam exatas: "bolsa*" casaria "bolsonaro", "crise*" casaria "crisemar".
_RELEVANT = (
    (3, ("morr*", "mort*", "falec*", "luto", "assassin*", "obito*",
         "dies", "died", "dead", "death", "deaths", "killed", "killing*")),
    (3, ("guerra", "guerras", "ataq*", "atentad*", "bombarde*", "invas*", "invad*", "terremot*", "tsunami*",
         "furac*", "explos*", "tirote*", "tragedi*", "enchent*", "desastre*",
         "war", "wars", "attack*", "strike", "strikes", "invasion*", "earthquake*", "hurricane*",
         "explosion*", "shooting*", "flood*")),
    (2, ("bolsa", "bolsas", "ibovespa", "acoes", "dolar", "juro", "juros", "selic", "inflac*", "recess*",
         "stocks", "shares", "market", "markets", "dow", "nasdaq", "inflation", "recession*", "rates", "fed",
         "tarifa*", "tariff*")),
    (2, ("queda", "quedas", "despenc*", "desab*", "dispar*", "recorde*", "crise", "crises", "colaps*",
         "plung*", "tumbl*", "soar*", "surge", "surges", "record", "records", "crisis", "collaps*", "crash*")),
    (1, ("presidente*", "eleic*", "stf", "congresso", "governo", "urgente", "president*",
         "election*", "congress", "government", "breaking")),
)
# Frases que anulam o peso ("bolsa de estudos" não é mercado). `*` no fim = prefixo.
_FALSE_CONTEXT = (
    "bolsa de estud*", "bolsas de estud*", "bolsa famil*", "bolsa auxil*", "queda de cabel*",
    "morr* de rir", "morr* de medo", "ataque de ris*", "guerra de travesseir*", "mercado de trabalh*",
)


def _compile(terms):
    """('morr*', 'luto') → ({'luto'}, ('morr',)): palavras exatas e prefixos."""
    exact = {t for t in terms if not t.endswith("*")}
    prefixes = tuple(t[:-1] for t in terms if t.endswith("*"))
    return exact, prefixes


def _context_re(phrases):
    """Regex única que casa qualquer frase de `phrases` (palavra inteira; `*` = prefixo)."""
    parts = []
    for phrase in phrases:
        words = [re.escape(w[:-1]) + r"\w*" if w.endswith("*") else re.escape(w) for w in phrase.split()]
        parts.append(r"\b" + r"\s+".join(words) + r"\b")
    return re.compile("|".join(parts))


_RELEVANT_C = tuple((weight, _compile(terms)) for weight, terms in _RELEVANT)
_FALSE_CONTEXT_RE = _context_re(_FALSE_CONTEXT)
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
    """Peso do assunto: morte, mercado em queda/alta, guerra, desastre, eleição…
    Cada grupo soma uma vez; frases de `_FALSE_CONTEXT` saem antes da contagem."""
    words = set(re.findall(r"\w+", _FALSE_CONTEXT_RE.sub(" ", _plain(title))))
    return sum(weight for weight, (exact, prefixes) in _RELEVANT_C
               if words & exact or any(w.startswith(prefixes) for w in words))


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


def _fresh(titles, now=None, max_age_h=MAX_AGE_H):
    """Títulos recentes entre os FEED_WINDOW primeiros (sem data conta como recente)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    fresh = []
    for title, when in titles[:FEED_WINDOW]:
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=datetime.timezone.utc)
            if (now - when).total_seconds() > max_age_h * 3600:
                continue
        fresh.append(title)
    return fresh


def top_candidates(titles, n=RERANK_TOP, now=None, max_age_h=MAX_AGE_H):
    """Até `n` manchetes recentes, da mais relevante à menos; empate → a mais nova.
    `titles`: [(título, datetime|None)]."""
    ranked = sorted(enumerate(_fresh(titles, now, max_age_h)), key=lambda it: (-relevance(it[1]), it[0]))
    return [title for _, title in ranked[:n]]


def pick_relevant(titles, now=None, max_age_h=MAX_AGE_H):
    """Manchete mais relevante entre as recentes; empate → a mais nova (1ª do feed).
    `titles`: [(título, datetime|None)]. Itens sem data contam como recentes."""
    best = top_candidates(titles, n=1, now=now, max_age_h=max_age_h)
    return best[0] if best else None


def _candidates_for(name, search, get=None):
    """Até RERANK_TOP manchetes limpas de uma fonte, da mais relevante à menos."""
    kind, value = resolve(name)
    if kind == "doi":
        return doi_articles(limit=1)
    feed = FEEDS.get(value) if kind == "site" else None
    if feed:  # item de feed sem data não prova que é de hoje → fica de fora
        best = top_candidates([it for it in fetch_feed(feed, get=get) if it[1] is not None])
        if best:
            return [clean_title(t, name, value) for t in best]
    query = f"notícias hoje site:{value}" if kind == "site" else value
    domain = value if kind == "site" else None
    titles = [r["title"] for r in search(query, max_results=5)
              if r.get("title") and not _is_portal_title(r["title"], name, domain)]
    return [clean_title(t, name, domain) for t in top_candidates([(t, None) for t in titles])]


def rerank(candidates, ask=None):
    """{fonte: índice} escolhido pelo Ollama numa ÚNICA chamada.
    `candidates`: {fonte: [títulos]}; só fontes com 2+ opções vão ao modelo.
    Resposta inválida, índice fora da faixa ou erro → a fonte fica de fora
    (quem chama usa o índice 0, a nota de palavras). Nunca levanta."""
    import json
    multi = {name: titles for name, titles in candidates.items() if len(titles) > 1}
    if not multi:
        return {}
    try:
        if ask is None:
            from core.llm import query_ollama as ask
        from core.prompts import load_prompt
        numbered = {name: {str(i): t for i, t in enumerate(titles)} for name, titles in multi.items()}
        prompt = load_prompt("news_rank.md", candidates=json.dumps(numbered, ensure_ascii=False, indent=2))
        raw = ask([{"role": "user", "content": prompt}], format="json", temperature=0)
        data = json.loads(raw) if isinstance(raw, str) else None
    except Exception as e:
        log.warning(f"[NEWS] Desempate pela IA falhou: {e}")
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for name, titles in multi.items():
        try:
            idx = int(data.get(name))
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(titles):
            out[name] = idx
    return out


def _ai_enabled():
    """Pref `news_ai` (/config → ROTINAS); qualquer falha = desligada."""
    try:
        from services import user_prefs
        return bool(user_prefs.get("news_ai"))
    except Exception as e:
        log.debug(f"[NEWS] Pref news_ai indisponível: {e}")
        return False


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


def headlines(sources=None, search=None, get=None, ai=None, ask=None):
    """[(fonte, manchete)] — a última notícia mais relevante de cada fonte, na
    ordem configurada. As fontes rodam em paralelo; a que falha é pulada.
    `ai` (padrão: pref `news_ai`) liga o desempate pelo Ollama — uma chamada só."""
    from concurrent.futures import ThreadPoolExecutor
    if search is None:
        from core.web import search
    sources = parse_sources(get_sources()) if sources is None else list(sources)
    if not sources:
        return []

    def one(name):
        try:
            return _candidates_for(name, search, get=get)
        except Exception as e:
            log.warning(f"[NEWS] Fonte '{name}' falhou: {e}")
            return []

    with ThreadPoolExecutor(max_workers=min(6, len(sources))) as pool:
        results = dict(zip(sources, pool.map(one, sources)))
    use_ai = _ai_enabled() if ai is None else ai
    chosen = rerank(results, ask=ask) if use_ai else {}
    return [(name, results[name][chosen.get(name, 0)]) for name in sources if results[name]]
