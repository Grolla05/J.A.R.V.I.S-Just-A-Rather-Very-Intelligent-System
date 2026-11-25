"""Fact-Checking: verificação cruzada de uma afirmação em fontes independentes.

Fluxo de `check(texto)`:
    afirmação (limpa o pedido; texto longo → modelo extrai) → 2 buscas (a afirmação e
    "é verdade ou fake") → fontes de domínios diferentes (até MAX_SOURCES) → lê as
    primeiras páginas → veredito do modelo em JSON → regras duras → Markdown

Regras que não dependem do modelo (gemma2:2b erra):
- menos de MIN_DOMAINS domínios diferentes → INCONCLUSIVO sem perguntar ao modelo
- CONFIRMADO/FALSO só com MIN_DOMAINS fontes citadas do mesmo lado; senão o veredito cai
  para IMPRECISO (se citou alguma) ou INCONCLUSIVO
- JSON inválido / veredito desconhecido / modelo fora → INCONCLUSIVO

Roda em thread (skill ou worker da TUI); nada levanta.
"""
import json
import re
from urllib.parse import urlsplit

from core import web
from core.browser import is_fetch_safe
from core.config import settings
from core.logger import log
from core.prompts import load_prompt
from core.utils import TTLCache

CLAIM_MAX = 2000          # caracteres aceitos (afirmação colada ou copiada)
SHORT_CLAIM = 280         # até aqui a frase já é a afirmação; acima o modelo extrai
MAX_SOURCES = 5
MIN_DOMAINS = 2
SOURCE_CHARS = 1500       # texto de cada fonte enviado ao modelo
CACHE_TTL = 600

CONFIRMED, FALSE, INACCURATE, INCONCLUSIVE = "CONFIRMADO", "FALSO", "IMPRECISO", "INCONCLUSIVO"
VERDICTS = (CONFIRMED, FALSE, INACCURATE, INCONCLUSIVE)
BADGE = {CONFIRMED: "✅ CONFIRMADO", FALSE: "❌ FALSO", INACCURATE: "⚠️ IMPRECISO", INCONCLUSIVE: "❔ INCONCLUSIVO"}

_cache = TTLCache(maxsize=32, ttl=CACHE_TTL)
# Título (da busca) que desmente a afirmação: fonte citada "a favor" com ele vai para "contra"
_DEBUNK_RE = re.compile(
    r"\b(mito|desmentid\w*|desmente|boato|hoax|myth|debunk\w*)\b"
    r"|\b[eé]\s+(?:fake|falso|falsa|mentira)\b"
    r"|\bn[aã]o\s+[eé]\s+(?:verdade|real|poss[ií]vel|vis[ií]vel)\b|\bpor\s+que\s+n[aã]o\b", re.I)

_REQUEST_RE = re.compile(
    r"^\s*(?:(?:jarvis|javis|jarbas)[\s,]+)?"
    r"(?:(?:isso|isto|essa|esta)\s+(?:informa[cç][aã]o\s+|not[ií]cia\s+)?[eé]\s+(?:verdade|fake|mentira|real)\s*[:?,-]?\s*"
    r"|(?:[eé]\s+)?(?:verdade|fake|mentira)\s+que\s+"
    r"|(?:checa|cheque|checar|confere|confira|conferir|verifica|verifique|verificar)"
    r"(?:\s+(?:pra\s+mim|para\s+mim))?(?:\s+(?:se|que|isso|isto|essa\s+not[ií]cia|essa\s+informa[cç][aã]o))?\s*[:,-]?\s*"
    r"|fact[\s-]?check\s*[:,-]?\s*)",
    re.I)


# ------------------------------------------------------------------ afirmação
def clean_claim(text):
    """Tira o pedido ("isso é verdade:", "checa se", "é fake que") e deixa a afirmação."""
    text = " ".join((text or "").split())
    return _REQUEST_RE.sub("", text, count=1).strip(" ?!.:;,-\"'“”")


def extract_claim(text, ask_llm=None):
    """Afirmação a checar. Texto longo (colado/copiado) → modelo resume na afirmação central."""
    claim = clean_claim(text)[:CLAIM_MAX]
    if len(claim) <= SHORT_CLAIM or not ask_llm:
        return claim
    extracted = ask_llm(claim)
    return extracted or claim[:SHORT_CLAIM]


def ask_claim_llm(text):
    try:
        from core.llm import query_ollama
        raw = query_ollama([{"role": "system", "content": load_prompt("factcheck_claim.md")},
                            {"role": "user", "content": text}],
                           format="json", temperature=0, timeout=settings.TIMEOUT_LLM)
        data = json.loads(raw or "{}")
    except Exception as e:
        log.debug(f"[FACTCHECK] Modelo não extraiu a afirmação: {e}")
        return None
    claim = data.get("claim") if isinstance(data, dict) else None
    return " ".join(str(claim).split())[:SHORT_CLAIM] if claim else None


# ------------------------------------------------------------------ fontes
def domain(url):
    host = (urlsplit(url or "").hostname or "").lower()
    return host.removeprefix("www.").removeprefix("m.")


def gather_sources(claim, search=web.search):
    """Resultados das 2 buscas, 1 por domínio, só URLs públicas: até MAX_SOURCES."""
    seen, out = set(), []
    for query in (claim, f"{claim} é verdade ou fake"):
        for item in search(query):
            dom = domain(item.get("url"))
            if not dom or dom in seen or not is_fetch_safe(item.get("url")):
                continue
            seen.add(dom)
            out.append(item)
            if len(out) >= MAX_SOURCES:
                return out
    return out


def _format_sources(sources):
    parts = []
    for i, src in enumerate(sources, 1):
        body = (src.get("text") or src.get("snippet") or "")[:SOURCE_CHARS]
        parts.append(f"[{i}] {src.get('title', '')} — {domain(src['url'])}\n{body}")
    return "\n\n".join(parts)


# ------------------------------------------------------------------ veredito
def _indices(value, n):
    out = []
    for item in value if isinstance(value, list) else []:
        try:
            idx = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= idx <= n and idx not in out:
            out.append(idx)
    return out


def parse_verdict(raw, n_sources, titles=None):
    """JSON do modelo → {'verdict', 'summary', 'pro', 'con', 'model'} já com as regras duras.

    `titles` (da busca, não do modelo): fonte citada "a favor" cujo título desmente a
    afirmação ("Mito: …", "Desmentido: …", "Por que NÃO é possível…") passa para "contra".
    CONFIRMADO exige ≥ MIN_DOMAINS a favor e NENHUMA contra; se as fontes desmentem, vira
    FALSO (≥ MIN_DOMAINS contra e nenhuma a favor) ou IMPRECISO (divergem). O inverso não
    existe: FALSO do modelo nunca vira CONFIRMADO — na dúvida, o lado cético."""
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    verdict = model = str(data.get("veredito") or "").strip().upper()
    summary = " ".join(str(data.get("resumo") or "").split())
    pro = _indices(data.get("fontes_a_favor"), n_sources)
    con = _indices(data.get("fontes_contra"), n_sources)
    if titles:
        debunk = [i for i in pro if i <= len(titles) and _DEBUNK_RE.search(titles[i - 1] or "")]
        pro = [i for i in pro if i not in debunk]
        con = sorted(set(con) | set(debunk))
    result = {"summary": summary, "pro": pro, "con": con, "model": model}
    if verdict not in VERDICTS or not summary:
        return dict(result, verdict=INCONCLUSIVE)
    if verdict == CONFIRMED and (len(pro) < MIN_DOMAINS or con):
        verdict = FALSE if (len(con) >= MIN_DOMAINS and not pro) else INACCURATE if (pro or con) else INCONCLUSIVE
    elif verdict == FALSE and (len(con) < MIN_DOMAINS or len(pro) >= MIN_DOMAINS):
        verdict = INACCURATE if (pro or con) else INCONCLUSIVE
    return dict(result, verdict=verdict)


def ask_verdict(claim, sources):
    from core.llm import query_ollama
    prompt = load_prompt("factcheck_verdict.md", claim=claim, sources=_format_sources(sources))
    try:
        return query_ollama([{"role": "user", "content": prompt}], format="json", temperature=0,
                            timeout=max(settings.TIMEOUT_LLM, 60))
    except Exception as e:
        log.warning(f"[FACTCHECK] Modelo não respondeu: {e}")
        return None


def render(claim, result, sources):
    lines = [f"**Veredito: {BADGE[result['verdict']]}**", "", f"> {claim}", ""]
    if result["summary"]:
        lines += [result["summary"], ""]
    if result.get("model") in VERDICTS and result["model"] != result["verdict"]:
        lines += [f"_O modelo disse {result['model']}, mas as fontes citadas não sustentam isso — "
                  "veredito ajustado pelas regras._", ""]
    cites = []
    if result["pro"]:
        cites.append("**A favor:** " + ", ".join(f"[{i}]" for i in result["pro"]))
    if result["con"]:
        cites.append("**Contra:** " + ", ".join(f"[{i}]" for i in result["con"]))
    if cites:
        lines += [" · ".join(cites), ""]
    lines += ["**Fontes**", web.sources_markdown(sources)]
    return "\n".join(lines)


def check(text, search=web.search, read=web.read_pages, verdict_fn=ask_verdict, claim_llm=ask_claim_llm):
    """Checa a afirmação e devolve Markdown com veredito e fontes. Nunca levanta."""
    try:
        claim = extract_claim(text, claim_llm)
        if len(claim) < 8:
            return "Checar o quê, Senhor? Diga a afirmação: `/checar a Muralha da China é visível do espaço`."
        cached = _cache.get(claim.lower())
        if cached:
            return cached
        sources = gather_sources(claim, search)
        if len({domain(s["url"]) for s in sources}) < MIN_DOMAINS:
            return (f"**Veredito: {BADGE[INCONCLUSIVE]}**\n\n> {claim}\n\n"
                    f"Não achei ao menos {MIN_DOMAINS} fontes independentes sobre isso, Senhor — "
                    "sem cruzar informação, não dou veredito.")
        sources = read(sources[:web.PAGES_TO_READ]) + sources[web.PAGES_TO_READ:]
        result = parse_verdict(verdict_fn(claim, sources), len(sources), [s.get("title") or "" for s in sources])
        answer = render(claim, result, sources)
        _cache.set(claim.lower(), answer)
        return answer
    except Exception as e:
        log.error(f"[FACTCHECK] Falha: {e}")
        return "Não consegui checar agora, Senhor. A busca ou o modelo não colaboraram."
