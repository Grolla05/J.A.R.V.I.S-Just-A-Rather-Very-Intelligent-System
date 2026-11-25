"""Navegação headless: Playwright dirigindo o Edge do Windows (channel="msedge"), sem janela.

Sem `playwright install`: usa o Edge que já vem no Windows. Perfil próprio em
`settings.DIR_DATA / headless_profile` — nunca o perfil do usuário, nunca login.

Passos tipados e limitados (o LLM só escolhe entre eles; nada de JavaScript vindo dele):
    goto(url) · click(text) · fill(label, value) · press(key) · wait(seconds) · extract

Segurança:
- toda navegação da página principal passa por `browser.is_fetch_safe`; recursos
  (imagens, scripts, XHR) só para hosts públicos — rede local/localhost é abortada
- download desligado (`accept_downloads=False`), service workers bloqueados
- campo de senha/cartão/CPF nunca é preenchido (rótulo, `type=password`, `autocomplete=cc-*`
  e valor com cara de CPF/cartão)
- passo que envia algo (clicar "Comprar", "Enviar", Enter depois de preencher um campo
  que não é busca) é marcado por `risky_steps`; quem chama confirma antes (core/pending.py)

Uma tarefa por vez (o perfil persistente não aceita dois Edge). Tudo roda em thread
(skill, worker da TUI ou Web Watch); nada aqui levanta para fora.
"""
import importlib.util
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from core.browser import is_fetch_safe
from core.config import settings
from core.logger import log

MAX_STEPS = 8
STEP_TYPES = ("goto", "click", "fill", "press", "wait", "extract")
ALLOWED_KEYS = {"enter": "Enter", "tab": "Tab", "escape": "Escape", "esc": "Escape",
                "pagedown": "PageDown", "arrowdown": "ArrowDown"}
MAX_WAIT_S = 5
TEXT_MAX = 200             # texto de clique, rótulo e valor
ACTION_TIMEOUT_MS = 10_000
SETTLE_TIMEOUT_MS = 5_000  # espera curta pela rede depois de cada passo
PAGE_CHARS = 8000          # texto devolvido por extract
MAX_HTML = 2_000_000
PROFILE_DIR = settings.DIR_DATA / "headless_profile"

_EDGE_PATHS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

_SEND_RE = re.compile(
    r"\b(envi\w*|send|submit|compr\w*|buy|checkout|finaliz\w*|fechar\s+pedido|pagar|pague|pagamento|pay|"
    r"assin\w*|subscrib\w*|confirm\w*|cadastr\w*|registr\w*|inscrev\w*|sign\s*(?:in|up)|log\s*in|login|"
    r"entrar|logar|publicar|publish|postar|post|exclu\w*|apag\w*|delet\w*|remov\w*|cancel\w*|contrat\w*|"
    r"carrinho|cart|reserv\w*|agend\w*|doar|doe)\b", re.I)
_SEARCH_RE = re.compile(r"\b(busc\w*|pesquis\w*|procur\w*|search|find|q|query|termo|filtr\w*)\b", re.I)
_SENSITIVE_FIELD_RE = re.compile(
    r"senha|password|passwd|\bpin\b|\bcpf\b|\bcnpj\b|\brg\b|passaporte|passport|cart[aã]o|\bcard\b|"
    r"\bcvv\b|\bcvc\b|c[oó]digo\s+de\s+seguran|validade|expira|ag[eê]ncia|conta\s+banc|\biban\b|"
    r"\bpix\b|token|\b2fa\b|\botp\b", re.I)
_SENSITIVE_VALUE_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b(?:\d[ .-]?){13,19}\b")
_SENSITIVE_AUTOCOMPLETE = ("cc-", "current-password", "new-password", "one-time-code")

_lock = threading.Lock()


class StepError(Exception):
    """Passo que não deu para executar (mensagem já em português, para o usuário)."""


# ------------------------------------------------------------------ disponibilidade
def edge_path():
    return next((p for p in _EDGE_PATHS if p.exists()), None)


def available():
    """(ok, motivo). Precisa do pacote playwright e do Edge instalado."""
    if importlib.util.find_spec("playwright") is None:
        return False, "o pacote playwright não está instalado"
    if edge_path() is None:
        return False, "o Microsoft Edge não foi encontrado"
    return True, ""


def busy():
    return _lock.locked()


# ------------------------------------------------------------------ validação
def _text(value):
    return " ".join(str(value or "").split())[:TEXT_MAX]


def is_sensitive_field(label):
    return bool(_SENSITIVE_FIELD_RE.search(label or ""))


def is_sensitive_value(value):
    return bool(_SENSITIVE_VALUE_RE.search(value or ""))


def validate_steps(raw):
    """Lista do LLM → (passos normalizados, None) ou (None, motivo)."""
    if not isinstance(raw, list) or not raw:
        return None, "nenhum passo"
    if len(raw) > MAX_STEPS:
        return None, f"passos demais (máximo {MAX_STEPS})"
    steps = []
    for item in raw:
        if not isinstance(item, dict):
            return None, "passo inválido"
        kind = str(item.get("type") or "").strip().lower()
        if kind not in STEP_TYPES:
            return None, f"tipo de passo desconhecido: {kind or '(vazio)'}"
        if kind == "goto":
            url = str(item.get("url") or "").strip()
            if not is_fetch_safe(url):
                return None, f"endereço não permitido: {url or '(vazio)'}"
            steps.append({"type": kind, "url": url})
        elif kind == "click":
            text = _text(item.get("text"))
            if not text:
                return None, "clique sem texto"
            steps.append({"type": kind, "text": text})
        elif kind == "fill":
            label, value = _text(item.get("label")), _text(item.get("value"))
            if not label:
                return None, "campo sem rótulo"
            if is_sensitive_field(label) or is_sensitive_value(value):
                return None, f"não preencho dado sensível (senha, cartão, CPF…): {label}"
            steps.append({"type": kind, "label": label, "value": value})
        elif kind == "press":
            key = ALLOWED_KEYS.get(str(item.get("key") or "").strip().lower())
            if not key:
                return None, f"tecla não permitida: {item.get('key')}"
            steps.append({"type": kind, "key": key})
        elif kind == "wait":
            try:
                seconds = float(item.get("seconds") or 1)
            except (TypeError, ValueError):
                seconds = 1.0
            steps.append({"type": kind, "seconds": min(max(seconds, 0.5), MAX_WAIT_S)})
        else:
            steps.append({"type": kind})
    if steps[0]["type"] != "goto":
        return None, "o primeiro passo precisa abrir um endereço"
    return steps, None


def risky_steps(steps):
    """Índices (0-based) dos passos que enviam algo: pedem confirmação antes."""
    risky, last_fill = [], None
    for i, step in enumerate(steps):
        kind = step["type"]
        if kind == "fill":
            last_fill = step
        elif kind == "click":
            text = step["text"]
            if _SEND_RE.search(text) and not _SEARCH_RE.search(text):
                risky.append(i)
        elif kind == "press" and step["key"] == "Enter" and last_fill is not None:
            if not _SEARCH_RE.search(last_fill["label"]):
                risky.append(i)
        elif kind == "goto":
            last_fill = None
    return risky


def describe(step):
    kind = step["type"]
    if kind == "goto":
        return f"abrir {urlsplit(step['url']).hostname}"
    if kind == "click":
        return f"clicar em “{step['text']}”"
    if kind == "fill":
        return f"preencher “{step['label']}” com “{step['value']}”"
    if kind == "press":
        return f"teclar {step['key']}"
    if kind == "wait":
        return f"esperar {step['seconds']:g} s"
    return "copiar o texto da página"


# ------------------------------------------------------------------ navegador
def _public_resource(url):
    parts = urlsplit(url)
    if parts.scheme in ("data", "blob", "about"):
        return True
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    return is_fetch_safe(f"{parts.scheme}://{parts.hostname}/")


def _guard(route):
    """Navegação principal: is_fetch_safe completo. Recurso: só host público."""
    req = route.request
    try:
        main_nav = req.is_navigation_request() and req.frame.parent_frame is None
    except Exception:
        main_nav = req.is_navigation_request()
    ok = is_fetch_safe(req.url) if main_nav else _public_resource(req.url)
    if ok:
        route.continue_()
    else:
        log.debug(f"[HEADLESS] Bloqueado: {req.url[:120]}")
        route.abort()


@contextmanager
def _edge(visible=None):
    """Página do Edge (perfil próprio, rotas vigiadas). Fecha tudo no fim."""
    from playwright.sync_api import sync_playwright  # import tardio: só quem navega paga o custo
    visible = settings.HEADLESS_VISIBLE if visible is None else visible
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), channel="msedge", headless=not visible, accept_downloads=False,
            service_workers="block", locale="pt-BR", viewport={"width": 1366, "height": 900})
        try:
            ctx.route("**/*", _guard)
            ctx.set_default_timeout(ACTION_TIMEOUT_MS)
            ctx.set_default_navigation_timeout(settings.HEADLESS_TIMEOUT * 1000)
            yield ctx.pages[0] if ctx.pages else ctx.new_page()
        finally:
            ctx.close()


def _settle(page):
    try:
        page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
    except Exception:
        pass  # página com rede sempre ativa (chat, anúncio): segue com o que tem


def _first(*locators):
    for loc in locators:
        try:
            if loc.count():
                return loc.first
        except Exception:
            continue
    return None


_CURRENCY_ALONE = re.compile(r"^(R\$|US\$|\$|€|£)$")


def _visible_text(raw, max_chars):
    """Linhas não vazias; símbolo de moeda sozinho na linha junta com o valor ("R$" + "4.199,99")."""
    out = []
    for line in (" ".join(raw_line.split()) for raw_line in (raw or "").splitlines()):
        if not line:
            continue
        if out and _CURRENCY_ALONE.match(out[-1]):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return "\n".join(out)[:max_chars]


def _page_text(page, max_chars=PAGE_CHARS):
    """Texto visível do <main> (ou do <body>): pega preço em <span>, que o extract_text
    (só parágrafos longos) descarta. Último recurso: extract_text do HTML."""
    for selector, timeout in (("main", 1000), ("body", ACTION_TIMEOUT_MS)):
        try:
            text = _visible_text(page.inner_text(selector, timeout=timeout), max_chars)
        except Exception:
            continue
        if text:
            return text
    from core.web import extract_text
    return extract_text(page.content(), max_chars=max_chars)


def _do_step(page, step, texts):
    kind = step["type"]
    if kind == "goto":
        page.goto(step["url"], wait_until="domcontentloaded")
        _settle(page)
    elif kind == "click":
        text = step["text"]
        loc = _first(page.get_by_role("button", name=text), page.get_by_role("link", name=text),
                     page.get_by_text(text))
        if loc is None:
            raise StepError(f"não achei “{text}” na página")
        loc.click()
        _settle(page)
    elif kind == "fill":
        label = step["label"]
        loc = _first(page.get_by_label(label), page.get_by_placeholder(label),
                     page.get_by_role("searchbox", name=label), page.get_by_role("textbox", name=label))
        if loc is None:
            raise StepError(f"não achei o campo “{label}”")
        kind_attr = (loc.get_attribute("type") or "").lower()
        auto = (loc.get_attribute("autocomplete") or "").lower()
        if kind_attr == "password" or auto.startswith(_SENSITIVE_AUTOCOMPLETE):
            raise StepError(f"o campo “{label}” pede dado sensível — não preencho")
        loc.fill(step["value"])
    elif kind == "press":
        page.keyboard.press(step["key"])
        _settle(page)
    elif kind == "wait":
        page.wait_for_timeout(int(step["seconds"] * 1000))
    else:
        texts.append(_page_text(page))


def _friendly(error):
    msg = str(error)
    if isinstance(error, StepError):
        return msg
    if "Timeout" in type(error).__name__ or "Timeout" in msg:
        return "o site demorou demais para responder"
    if "msedge" in msg.lower() or "executable" in msg.lower():
        return "não consegui abrir o Microsoft Edge"
    if "ERR_BLOCKED" in msg or "net::ERR_FAILED" in msg or "ERR_ABORTED" in msg:
        return "o site tentou ir para um endereço não permitido"
    if "net::" in msg:
        return "o site está fora do ar ou sem internet"
    return "a página não se comportou como esperado"


def run_task(steps, opener=None):
    """Executa passos já validados → {'ok', 'url', 'title', 'text', 'done', 'error'}."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "done": 0, "error": "já há uma tarefa em segundo plano"}
    done = 0
    try:
        with (opener or _edge)() as page:
            texts = []
            for step in steps:
                _do_step(page, step, texts)
                if page.url != "about:blank" and not is_fetch_safe(page.url):
                    raise StepError("o site redirecionou para um endereço não permitido")
                done += 1
            if not any(s["type"] == "extract" for s in steps):
                texts.append(_page_text(page))
            return {"ok": True, "url": page.url, "title": page.title(), "done": done,
                    "text": "\n\n".join(t for t in texts if t)[:PAGE_CHARS * 2], "error": None}
    except Exception as e:
        log.warning(f"[HEADLESS] Passo {done + 1} falhou: {e}")
        return {"ok": False, "done": done, "error": _friendly(e)}
    finally:
        _lock.release()


def _render(url, opener, read):
    """Abre a página (só URL pública), espera o JavaScript e devolve read(page). '' se não der."""
    if not is_fetch_safe(url) or (opener is None and not available()[0]):
        return ""
    if not _lock.acquire(blocking=False):
        return ""
    try:
        with (opener or _edge)() as page:
            page.goto(url, wait_until="domcontentloaded")
            _settle(page)
            return read(page) if is_fetch_safe(page.url) else ""
    except Exception as e:
        log.debug(f"[HEADLESS] Render de {url} falhou: {e}")
        return ""
    finally:
        _lock.release()


def render_html(url, opener=None):
    """HTML depois do JavaScript (Web Watch: preço que só aparece renderizado). '' se não der."""
    return _render(url, opener, lambda page: page.content()[:MAX_HTML])


def fetch_rendered(url, max_chars=PAGE_CHARS, opener=None):
    """Texto visível da página renderizada. '' se não der."""
    return _render(url, opener, lambda page: _page_text(page, max_chars))
