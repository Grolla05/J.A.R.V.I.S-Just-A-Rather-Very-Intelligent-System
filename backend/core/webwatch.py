"""Web Watch: checa uma página, um preço ou um repositório e diz o que mudou.

Lógica pura (preço no HTML, impressão digital do texto, linhas novas) + I/O fino
(requests, GitHub). Quem guarda o estado e decide quando checar é o
`services/web_watch.py`. Tudo roda em thread (worker da TUI ou skill): nada toca
em widget e nada levanta — falha vira `{"error": ...}`.

Toda URL passa por `browser.is_fetch_safe` (só http(s) público, sem credencial na
URL), inclusive a URL final depois de redirecionamentos.
"""
import hashlib
import json
import re

from core.browser import is_fetch_safe
from core.config import settings
from core.logger import log
from core.web import USER_AGENT, extract_text

PAGE_KEEP_CHARS = 4000   # texto guardado da página (para mostrar o que entrou de novo)
MAX_HTML_BYTES = 3_000_000
NEW_LINES_SHOWN = 3

PAGE, PRICE, REPO = "page", "price", "repo"

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GITHUB_URL_RE = re.compile(r"^https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:[/?#].*)?$", re.I)
_LD_JSON_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
_META_PRICE_RE = re.compile(
    r'<meta[^>]+(?:property|name|itemprop)=["\'](?:product:price:amount|og:price:amount|price)["\'][^>]*>', re.I)
_CONTENT_RE = re.compile(r'content=["\']([^"\']+)["\']', re.I)
_BRL_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)")
# Trechos que mudam sozinhos (relógio, data, contadores) e não contam como "a página mudou"
_VOLATILE_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?|\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{4}-\d{2}-\d{2}")


# ------------------------------------------------------------------ alvo
def github_repo(target):
    """'dono/repo' ou URL do GitHub → 'dono/repo'; senão None."""
    target = (target or "").strip()
    match = _GITHUB_URL_RE.match(target)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return target if _REPO_RE.match(target) and "." not in target.split("/")[0] else None


# ------------------------------------------------------------------ preço
def parse_number(raw):
    """'1.234,56' / '1234.56' / 1234.5 → 1234.56; inválido → None."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    text = str(raw or "").strip().replace("R$", "").replace(" ", "")
    if not text:
        return None
    if "," in text:                       # formato brasileiro: ponto = milhar, vírgula = decimal
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1 or re.search(r"\.\d{3}$", text):
        text = text.replace(".", "")      # 1.234 (milhar sem centavos)
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value > 0 else None


def _ld_prices(node):
    """Preços em `offers` de qualquer objeto JSON-LD (Product, ItemList, @graph…)."""
    if isinstance(node, list):
        for item in node:
            yield from _ld_prices(item)
    elif isinstance(node, dict):
        offers = node.get("offers")
        for offer in (offers if isinstance(offers, list) else [offers]):
            if isinstance(offer, dict):
                for key in ("price", "lowPrice"):
                    value = parse_number(offer.get(key))
                    if value:
                        yield value
        for key, value in node.items():
            if key != "offers" and isinstance(value, (dict, list)):
                yield from _ld_prices(value)


def parse_price(html):
    """Preço do produto na página: JSON-LD → meta de preço → 1º 'R$ …' no texto. None se não achar."""
    html = html or ""
    for block in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for value in _ld_prices(data):
            return value
    for tag in _META_PRICE_RE.findall(html):
        content = _CONTENT_RE.search(tag)
        value = parse_number(content.group(1)) if content else None
        if value:
            return value
    match = _BRL_RE.search(extract_text(html, max_chars=20000))
    return parse_number(match.group(1)) if match else None


def format_brl(value):
    """1234.5 → 'R$ 1.234,50'."""
    whole, cents = f"{value:,.2f}".split(".")
    return f"R$ {whole.replace(',', '.')},{cents}"


# ------------------------------------------------------------------ página
def fingerprint(text):
    """Hash do texto sem espaços extras nem trechos que mudam sozinhos (hora, data)."""
    norm = " ".join(_VOLATILE_RE.sub("", text or "").split()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def new_lines(old_text, new_text, limit=NEW_LINES_SHOWN):
    """Linhas que apareceram no texto novo (até `limit`), na ordem da página."""
    old = {line.strip() for line in (old_text or "").splitlines() if line.strip()}
    added = []
    for line in (new_text or "").splitlines():
        line = line.strip()
        if line and line not in old and line not in added:
            added.append(line)
        if len(added) >= limit:
            break
    return added


# ------------------------------------------------------------------ I/O
def fetch_html(url):
    """(html, erro). Recusa URL insegura antes e depois dos redirecionamentos."""
    if not is_fetch_safe(url):
        return "", "endereço não permitido (só páginas públicas http/https, sem credencial na URL)"
    try:
        import requests
        res = requests.get(url, timeout=settings.TIMEOUT_API, headers={"User-Agent": USER_AGENT})
    except Exception as e:
        log.debug(f"[WEBWATCH] Falha ao baixar {url}: {e}")
        return "", "site fora do ar ou sem resposta"
    if not is_fetch_safe(res.url or url):
        return "", "o site redirecionou para um endereço não permitido"
    if res.status_code != 200:
        return "", f"o site respondeu HTTP {res.status_code}"
    if "html" not in str(res.headers.get("Content-Type", "html")).lower():
        return "", "não é uma página HTML"
    return res.text[:MAX_HTML_BYTES], None


def check_page(url, fetch=fetch_html):
    """{'hash', 'text'} ou {'error'}."""
    html, error = fetch(url)
    if error:
        return {"error": error}
    text = extract_text(html, max_chars=PAGE_KEEP_CHARS)
    if not text:
        return {"error": "não achei texto legível na página"}
    return {"hash": fingerprint(text), "text": text}


def check_price(url, fetch=fetch_html, ask_llm=None, rendered=None):
    """{'price'} ou {'error'}. Sem preço no HTML cru: `rendered(url) -> html` (página
    depois do JavaScript, core/headless) e, por último, `ask_llm(texto) -> float|None`."""
    html, error = fetch(url)
    if error:
        return {"error": error}
    price = parse_price(html)
    if price is None and rendered:
        html = rendered(url) or html
        price = parse_price(html)
    if price is None and ask_llm:
        price = ask_llm(extract_text(html, max_chars=3000))
    if price is None:
        return {"error": "não achei o preço nessa página"}
    return {"price": price}


def check_repo(repo, snapshot=None):
    """{'release', 'commit', 'repo', 'branch'} ou {'error'}."""
    from core import github_client
    try:
        if snapshot is None:
            if not github_client.is_configured():
                return {"error": "GITHUB_TOKEN não configurado"}
            snapshot = github_client.repo_snapshot
        return snapshot(repo)
    except Exception as e:
        log.debug(f"[WEBWATCH] Repositório {repo}: {e}")
        status = getattr(e, "status", None)
        if status == 404:
            return {"error": "repositório não encontrado (ou sem acesso)"}
        return {"error": str(e) or "o GitHub não respondeu"}


def ask_price_llm(text):
    """Preço pelo modelo quando o HTML não traz marcação (JSON {'price': número|null})."""
    if not text:
        return None
    try:
        from core.llm import query_ollama
        from core.prompts import load_prompt
        raw = query_ollama([{"role": "system", "content": load_prompt("webwatch_price.md")},
                            {"role": "user", "content": text}],
                           format="json", temperature=0, timeout=settings.TIMEOUT_LLM)
        data = json.loads(raw or "{}")
    except Exception as e:
        log.debug(f"[WEBWATCH] Modelo não achou o preço: {e}")
        return None
    return parse_number(data.get("price")) if isinstance(data, dict) else None
