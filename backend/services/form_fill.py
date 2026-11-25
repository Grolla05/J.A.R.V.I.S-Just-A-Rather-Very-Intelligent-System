"""Preenchimento de formulários com a memória do JARVIS: "preenche esse formulário".

Fluxo de `request(pedido)`:
    link (da frase ou da aba aberta) → Edge COM janela (core/headless.FormSession) →
    lê os campos → mapeia para o perfil (regras por autocomplete/tipo/nome/rótulo; o
    modelo só escolhe a CHAVE do perfil para os campos que sobraram) → preenche →
    resumo "campo → valor" + "não preenchi" → confirmação (core/pending.py):
    "sim" clica em Enviar · "não" deixa a janela aberta, preenchida · "o telefone é …"
    corrige um campo e pergunta de novo

Perfil = só o que já existe: `⚙️ Configurações/🧠 Sobre mim.md` no Obsidian (linhas
`- **Campo:** valor` e links de GitHub/LinkedIn), e-mail da conta Google conectada e o
endereço de casa do /rota. Valores saem SÓ do perfil ou da fala do usuário — nunca
inventados pelo modelo. Senha, cartão, CPF/RG, conta bancária e afins nunca entram.
"""
import json
import re
import unicodedata
from urllib.parse import urlsplit

from core import headless, pending
from core.browser import is_fetch_safe
from core.config import settings
from core.logger import log
from core.prompts import load_prompt
from core.utils import TTLCache

CONFIRM_TIMEOUT_S = 300   # tempo para conferir a janela antes de responder
OPEN_TIMEOUT_S = 60
PROFILE_TTL = 300
PROFILE_NOTE = "⚙️ Configurações/🧠 Sobre mim.md"

LABELS = {
    "name": "Nome completo", "first_name": "Nome", "last_name": "Sobrenome", "email": "E-mail",
    "phone": "Telefone", "city": "Cidade", "state": "Estado", "country": "País", "address": "Endereço",
    "linkedin": "LinkedIn", "github": "GitHub", "website": "Site", "company": "Empresa",
}

# Só estes tipos recebem dado do perfil (texto). Data, hora, número, cor… ficam com o usuário.
TEXT_TYPES = ("text", "email", "tel", "url", "search", "textarea", "select", "select-one")

_AUTOCOMPLETE = {
    "name": "name", "given-name": "first_name", "family-name": "last_name", "email": "email",
    "tel": "phone", "tel-national": "phone", "address-level2": "city", "address-level1": "state",
    "country-name": "country", "country": "country", "street-address": "address", "address-line1": "address",
    "url": "website", "organization": "company",
}
_FIELD_RULES = (  # ordem importa: "primeiro nome" antes de "nome"
    ("first_name", r"primeiro nome|first ?name|fname|given|nome proprio"),
    ("last_name", r"sobrenome|last ?name|lname|surname|family"),
    ("email", r"e-?mail"),
    ("phone", r"telefone|celular|whats ?app|\bfone\b|phone|\btel\b|mobile"),
    ("linkedin", r"linkedin"),
    ("github", r"github"),
    ("website", r"\bsite\b|website|portf[oi]+lio|\burl\b|pagina pessoal"),
    ("city", r"cidade|\bcity\b|municipio"),
    ("state", r"\bestado\b|\buf\b|\bstate\b|province"),
    ("country", r"\bpais\b|country|nacionalidade"),
    ("address", r"endereco|address|logradouro|\brua\b"),
    ("company", r"empresa|company|organiza|instituicao"),
    ("name", r"\bnome\b|\bname\b|full ?name|seu nome"),
)
_FIELD_RES = tuple((key, re.compile(rx)) for key, rx in _FIELD_RULES)
_NOTE_FIELDS = {
    "name": ("nome completo", "nome"), "email": ("e-mail", "email"),
    "phone": ("telefone", "celular", "whatsapp"), "location": ("localizacao", "cidade"),
    "company": ("empresa",), "website": ("site", "portfolio"),
}
_NOTE_LINE_RE = re.compile(r"^\s*[-*]\s*\*\*(?P<key>[^*:]+):?\*\*:?\s*(?P<value>.+?)\s*$", re.M)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
_LINKEDIN_RE = re.compile(r"https?://(?:[\w-]+\.)?linkedin\.com/in/[\w%-]+/?", re.I)
_GITHUB_RE = re.compile(r"https?://github\.com/[\w-]+/?(?=[\s)\]]|$)", re.I | re.M)
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_ADJUST_RE = re.compile(r"^\s*(?:o|a|no|na|coloca|p[oõ]e|muda|troca)?\s*(?:campo\s+)?(?P<label>[\w\s/-]{2,40}?)"
                        r"\s+(?:[eé]|=|:|para|pra|com)\s+(?P<value>.+?)\s*$", re.I)

_profile_cache = TTLCache(maxsize=1, ttl=PROFILE_TTL)


def _fold(text):
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


# ------------------------------------------------------------------ perfil
def parse_profile_note(markdown):
    """`Sobre mim.md` → {chave: valor}. Só os campos conhecidos; nada sensível."""
    out = {}
    text = markdown or ""
    for match in _NOTE_LINE_RE.finditer(text):
        key = _fold(match.group("key"))
        value = _MD_LINK_RE.sub(lambda m: m.group(2), match.group("value")).strip()
        if not value or value.startswith("←") or headless.is_sensitive_field(key):
            continue
        for field, names in _NOTE_FIELDS.items():
            if key in names and field not in out:
                out[field] = value
    location = out.pop("location", "")
    if location:
        place, country = location, ""
        split = re.split(r"\s+[—–-]\s+", location, maxsplit=1)
        if len(split) == 2:
            place, country = split
        parts = [p.strip() for p in place.split(",") if p.strip()]
        if parts:
            out["city"] = parts[0]
        if len(parts) > 1:
            out["state"] = parts[1]
        if country.strip():
            out["country"] = country.strip()
    if m := _LINKEDIN_RE.search(text):
        out["linkedin"] = m.group(0)
    if m := _GITHUB_RE.search(text):
        out["github"] = m.group(0).rstrip("/")
    if out.get("name"):
        first, _, last = out["name"].partition(" ")
        out["first_name"] = first
        if last:
            out["last_name"] = last
    return {k: v for k, v in out.items() if v and not headless.is_sensitive_value(v)}


def _note_text():
    from core.obsidian import obsidian
    return obsidian.get_file(PROFILE_NOTE, quiet=True) or ""


def _google_email():
    try:
        from core import gmail
        return gmail.account.account() or ""
    except Exception:
        return ""


def _home_address():
    try:
        from core import traffic
        place = traffic.get_place("casa")
        return (place or {}).get("label") or ""
    except Exception:
        return ""


def load_profile(note=_note_text, email=_google_email, home=_home_address, use_cache=True):
    """Perfil do usuário a partir do que o JARVIS já sabe. Nunca levanta."""
    if use_cache and (cached := _profile_cache.get("profile")) is not None:
        return dict(cached)
    profile = {}
    try:
        profile = parse_profile_note(note())
    except Exception as e:
        log.debug(f"[FORM] Perfil do Obsidian indisponível: {e}")
    for key, source in (("email", email), ("address", home)):
        if not profile.get(key):
            try:
                value = source()
            except Exception:
                value = ""
            if value:
                profile[key] = value
    _profile_cache.set("profile", profile)
    return dict(profile)


# ------------------------------------------------------------------ mapeamento
def field_label(field):
    label = field.get("label") or field.get("placeholder") or field.get("name") or field.get("id")
    return (label or f"campo {field['i'] + 1}").strip().rstrip(":*").strip()


def rule_key(field):
    """Chave do perfil para o campo pelas regras (autocomplete → tipo → nome/rótulo), ou None."""
    auto = str(field.get("autocomplete") or "").split()
    for token in reversed(auto):
        if token in _AUTOCOMPLETE:
            return _AUTOCOMPLETE[token]
    kind = str(field.get("type") or "")
    if kind == "email":
        return "email"
    if kind == "tel":
        return "phone"
    blob = _fold(" ".join(str(field.get(k) or "") for k in ("label", "name", "id", "placeholder")).replace("_", " "))
    for key, rx in _FIELD_RES:
        if rx.search(blob):
            return key
    return None


def _select_value(field, value):
    """Opção do <select> que casa com o valor (sem acento/caixa), ou None."""
    want = _fold(value)
    for option in field.get("options") or []:
        if _fold(option) == want or (want and want in _fold(option)):
            return option
    return None


def ask_map_llm(fields, keys):
    """O modelo escolhe, para cada campo que sobrou, uma CHAVE do perfil (ou null)."""
    try:
        from core.llm import query_ollama
        listing = "\n".join(f'{f["i"]}: {field_label(f)}' for f in fields)
        prompt = load_prompt("form_map.md", fields=listing, keys=", ".join(keys))
        raw = query_ollama([{"role": "user", "content": prompt}], format="json", temperature=0,
                           timeout=settings.TIMEOUT_LLM)
        data = json.loads(raw or "{}")
    except Exception as e:
        log.debug(f"[FORM] Modelo não mapeou: {e}")
        return {}
    return data if isinstance(data, dict) else {}


def map_fields(fields, profile, ask_llm=ask_map_llm):
    """→ {'fill': [(campo, valor, chave)], 'sensitive': [campo], 'unknown': [campo]}."""
    fill, sensitive, unknown, leftover, used = [], [], [], [], set()
    for field in fields:
        if headless.is_sensitive_input(field):
            sensitive.append(field)
            continue
        if field.get("filled"):
            continue      # já tem algo escrito: não sobrescreve
        if str(field.get("type") or "text").lower() not in TEXT_TYPES:
            if field.get("required"):
                unknown.append(field)   # data, hora, número…: o perfil não tem, fica com o usuário
            continue
        key = rule_key(field)
        if key is None:
            leftover.append(field)
            continue
        _add(fill, unknown, field, key, profile, used)
    keys = []
    if leftover:
        keys = [k for k in profile if k not in used]
        answer = ask_llm(leftover, keys) if (ask_llm and keys) else {}
        for field in leftover:
            key = answer.get(str(field["i"])) if isinstance(answer, dict) else None
            if isinstance(key, str) and key in keys:
                _add(fill, unknown, field, key, profile, used)
            elif field.get("required"):
                unknown.append(field)
    return {"fill": fill, "sensitive": sensitive, "unknown": unknown}


def _add(fill, unknown, field, key, profile, used):
    value = profile.get(key)
    if value and field.get("tag") == "select":
        value = _select_value(field, value)
    if value:
        fill.append((field, value, key))
        used.add(key)
    else:
        unknown.append(field)


# ------------------------------------------------------------------ fluxo
def _summary(session, plan, result):
    failed = dict(result.get("failed") or [])
    lines = [f"Formulário **{session.title or urlsplit(session.url).hostname}** preenchido na janela do Edge:", ""]
    done = [(f, v) for f, v, _ in plan["fill"] if f["i"] not in failed]
    lines += [f"- {field_label(f)} → {v}" for f, v in done] or ["- (nenhum campo que eu saiba preencher)"]
    skipped = [f"{field_label(f)} (dado sensível)" for f in plan["sensitive"]]
    skipped += [f"{field_label(f)} (não sei)" for f in plan["unknown"]]
    skipped += [f"{field_label(f)} ({why})" for f, _, _ in plan["fill"] if (why := failed.get(f["i"]))]
    if skipped:
        lines += ["", "**Não preenchi:** " + "; ".join(skipped)]
    lines += ["", "Envio? (**sim** envia · **não** deixa a janela aberta para você terminar · "
                  "ou corrija: _\"o telefone é 19 99999-0000\"_)"]
    return "\n".join(lines)


def _arm(session, plan, result, owner):
    question = _summary(session, plan, result)
    # o botão de envio é procurado no <form> deste campo
    anchor = plan["fill"][0][0]["i"] if plan["fill"] else (session.fields[0]["i"] if session.fields else 0)
    armed = pending.arm(
        "FORM_SUBMIT", question, lambda: submit(session, anchor), target=session.title or session.url,
        on_decline=lambda: "Não enviei, Senhor. A janela segue aberta e preenchida — termine por lá.",
        on_other=lambda text: adjust(session, plan, result, text, owner),
        timeout_s=CONFIRM_TIMEOUT_S, owner=owner)
    return question if armed else pending.BUSY_REPLY


def submit(session, field_index):
    res = session.call("submit", field_index)
    if not res.get("ok"):
        return f"Não enviei, Senhor: {res.get('error')}."
    where = f" Página agora: **{res['title']}**." if res.get("title") else ""
    return f"Formulário enviado, Senhor.{where}"


def adjust(session, plan, result, text, owner):
    """"o telefone é 19 9…" → corrige um campo (valor da fala do usuário) e pergunta de novo."""
    m = _ADJUST_RE.match(text or "")
    field = None
    if m:
        want = _fold(m.group("label"))
        want_key = rule_key({"label": want, "i": -1})
        for f in session.fields:
            label = _fold(field_label(f))
            if want and (want == label or want in label or (want_key and rule_key(f) == want_key)):
                field = f
                break
    if field is None:
        return "Não achei esse campo, Senhor.\n\n" + _arm(session, plan, result, owner)
    value = m.group("value").strip(" .\"'")
    if headless.is_sensitive_input(field) or headless.is_sensitive_value(value):
        return "Esse dado eu não preencho, Senhor — digite você na janela.\n\n" + _arm(session, plan, result, owner)
    res = session.call("fill", [(field, value)])
    if res.get("failed"):
        return f"Não consegui mudar {field_label(field)}: {res['failed'][0][1]}.\n\n" + _arm(session, plan, result, owner)
    plan = dict(plan, fill=[e for e in plan["fill"] if e[0]["i"] != field["i"]] + [(field, value, "fala")],
                unknown=[f for f in plan["unknown"] if f["i"] != field["i"]])
    return _arm(session, plan, result, owner)


def _active_url():
    try:
        from core import browser
        win = browser.find_browser_window()
        return browser.active_url(win) if win else ""
    except Exception:
        return ""


def find_url(text, active=_active_url):
    url = next((u.rstrip(".,;)") for u in _URL_RE.findall(text or "")), None)
    return url or (active() if active else "") or ""


def request(text, owner=None, session_factory=None, profile=None, map_llm=ask_map_llm, active=_active_url):
    """Abre, preenche e pergunta antes de enviar. Devolve o texto para o usuário. Nunca levanta."""
    try:
        url = find_url(text, active)
        if not url:
            return "Qual formulário, Senhor? Mande o link (`/formulario <link>`) ou deixe a página aberta no navegador."
        if not is_fetch_safe(url):
            return "Esse endereço eu não abro, Senhor: só páginas públicas http/https, sem credencial na URL."
        if session_factory is None:
            ok, why = headless.available()
            if not ok:
                return f"Preencher formulário precisa do Microsoft Edge e do Playwright, Senhor — {why}."
            if headless.busy():
                return "Já há uma navegação em segundo plano, Senhor. Aguarde ela terminar."
        session = (session_factory or headless.FormSession)(url).start()
        if not session.wait_ready(OPEN_TIMEOUT_S):
            return f"Não abri o formulário, Senhor: {session.error}."
        if not session.fields:
            session.call("close")
            return "Não achei campos para preencher nessa página, Senhor."
        plan = map_fields(session.fields, profile if profile is not None else load_profile(), map_llm)
        result = session.call("fill", [(f, v) for f, v, _ in plan["fill"]]) if plan["fill"] else {"ok": True}
        return _arm(session, plan, result, owner)
    except Exception as e:
        log.error(f"[FORM] Falha: {e}")
        return "Não consegui preencher esse formulário agora, Senhor."
