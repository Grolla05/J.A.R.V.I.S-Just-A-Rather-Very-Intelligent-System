# ⚠️ ACESSO SENSÍVEL: foca a janela do navegador e manda atalhos de teclado (pyautogui);
# lê títulos das abas pela UI Automation do Windows. Fechar várias abas pede confirmação.
# Ver SECURITY.md.
"""Skill BROWSER_TABS — abas do navegador Chromium por voz (Copilot).

Roteamento em dois estágios, como o Spotify: `parse()` resolve quase tudo por
regex (sem Ollama); só a frase que sobrar vai ao LLM, que devolve {action, target}.
As ações saem de uma tabela fixa — texto do LLM nunca vira atalho.
"""
import json
import re
import unicodedata
from urllib.parse import quote_plus

from core import browser, log, pending
from core.config import settings
from core.prompts import load_prompt

INTENT = "BROWSER_TABS"
PROMPT_TEXT = load_prompt("skills/browser_tabs.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("aba", "abas", "guia", "guias", "navegador", "recarreg*", "anonim*", "reabr*")

DECISION_PROMPT = load_prompt("skills/browser_tabs_decision.md")

ACTIONS = {"NEW_TAB", "CLOSE_TAB", "CLOSE_OTHERS", "CLOSE_ALL", "GOTO_TAB", "NEXT_TAB", "PREV_TAB",
           "REOPEN", "LIST_TABS", "RELOAD", "BACK", "FORWARD", "DUPLICATE", "INCOGNITO"}

# Atalhos de ação sem alvo (Chromium)
HOTKEYS = {
    "NEXT_TAB": ("ctrl", "tab"), "PREV_TAB": ("ctrl", "shift", "tab"),
    "REOPEN": ("ctrl", "shift", "t"), "RELOAD": ("f5",), "BACK": ("alt", "left"),
    "FORWARD": ("alt", "right"), "INCOGNITO": ("ctrl", "shift", "n"),
}
REPLIES = {
    "NEXT_TAB": "Próxima aba.", "PREV_TAB": "Aba anterior.", "REOPEN": "Aba reaberta.",
    "RELOAD": "Recarregando.", "BACK": "Voltando uma página.", "FORWARD": "Avançando uma página.",
    "INCOGNITO": "Janela anônima aberta. Não vi nada, Senhor.",
}

# Sites comuns falados pelo nome ("abre uma aba no github")
SITES = {
    "youtube": "https://www.youtube.com", "github": "https://github.com", "gmail": "https://mail.google.com",
    "google": "https://www.google.com", "whatsapp": "https://web.whatsapp.com", "netflix": "https://www.netflix.com",
    "twitch": "https://www.twitch.tv", "linkedin": "https://www.linkedin.com", "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai", "spotify": "https://open.spotify.com", "agenda": "https://calendar.google.com",
    "drive": "https://drive.google.com", "notion": "https://www.notion.so", "reddit": "https://www.reddit.com",
    "wikipedia": "https://pt.wikipedia.org", "instagram": "https://www.instagram.com", "x": "https://x.com",
    "twitter": "https://x.com", "maps": "https://maps.google.com", "mapas": "https://maps.google.com",
}
SEARCH_URL = "https://www.google.com/search?q="

NO_BROWSER = "Nenhum navegador Chromium aberto, Senhor. Opera GX, Chrome, Edge ou Brave."
NO_FOCUS = "O navegador não aceitou o foco, Senhor. Clique nele uma vez e repita."
NO_TABS = "Não consegui ler as abas desse navegador, Senhor."

ORDINALS = {"primeira": 1, "segunda": 2, "terceira": 3, "quarta": 4, "quinta": 5, "sexta": 6,
            "setima": 7, "oitava": 8, "nona": 9, "decima": 10, "ultima": -1}
_NUM = r"(\d+|primeira|segunda|terceira|quarta|quinta|sexta|setima|oitava|nona|decima|ultima)"
_ART = r"(?:a |essa |esta |uma )?"
_PREP = r"(?:(?:do|da|de|dos|das|no|na|com o|com a|com|sobre|numero|n)\s+)?"

# (ação, regex) — a 1ª que casar vence; grupo "t" = alvo
PATTERNS = (
    ("CLOSE_OTHERS", re.compile(r"\bfech\w* (?:todas )?(?:as )?(?:outras|demais) abas\b")),
    ("CLOSE_ALL", re.compile(r"\bfech\w* todas (?:as )?abas\b")),
    ("REOPEN", re.compile(r"\b(?:reabr\w*|recuper\w*|desfaz\w*) " + _ART + r"(?:ultima )?aba(?: fechada)?\b")),
    ("LIST_TABS", re.compile(r"\b(?:lista\w*|quais|mostra\w*|quantas)\b.*\babas\b")),
    ("INCOGNITO", re.compile(r"\b(?:aba|janela|guia) anonima\b|\bmodo anonimo\b")),
    ("DUPLICATE", re.compile(r"\bduplic\w* " + _ART + r"(?:aba|guia)\b")),
    ("RELOAD", re.compile(r"\b(?:recarreg\w*|atualiz\w*) " + _ART + r"(?:aba|guia|pagina)\b|\bf5\b")),
    ("BACK", re.compile(r"\b(?:volt\w* " + _ART + r"pagina|pagina anterior)\b")),
    ("FORWARD", re.compile(r"\b(?:avanc\w* " + _ART + r"pagina|proxima pagina)\b")),
    ("NEXT_TAB", re.compile(r"\bproxima (?:aba|guia)\b")),
    ("PREV_TAB", re.compile(r"\b(?:aba|guia) anterior\b")),
    ("CLOSE_TAB", re.compile(r"\bfech\w* " + _ART + r"(?:aba|guia)\b\s*" + _PREP + r"(?P<t>.*)$")),
    # "nova aba", "abre uma (nova) aba", "abre aba nova", "abre aba" — "abre A aba do X" é GOTO
    ("NEW_TAB", re.compile(r"\b(?:nova (?:aba|guia)|abr\w* uma (?:nova )?(?:aba|guia)(?: nova)?|abr\w* (?:aba|guia) nova|"
                           r"abr\w* (?:aba|guia)$)"
                           r"\s*(?:(?:e |para |pra )?(?:pesquis\w*|busc\w*|procur\w*)\s+(?P<q>.+)|"
                           + _PREP + r"(?P<t>.*))$")),
    ("GOTO_TAB", re.compile(r"\b(?:(?:vai|va|ir|vamos|muda|mude|mudar|troca|troque|trocar|abr\w*|foc\w*|"
                            r"mostra|seleciona\w*|passa)\s+)?(?:para |pra )?" + _ART + r"(?:aba|guia)\s+"
                            + _PREP + r"(?P<t>.+)$")),
    ("GOTO_TAB", re.compile(r"\b" + _NUM + r" (?:aba|guia)\b")),
)


# ------------------------------------------------------------ lógica pura
def normalize(text):
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[?!.,;:]", " ", text)
    text = re.sub(r"^\s*jarvis\b", " ", text)
    return " ".join(text.split())


def tab_ref(target):
    """'3' / 'terceira' / 'ultima' → índice (-1 = última); senão None."""
    t = normalize(target)
    t = re.sub(r"^(?:aba|guia)\s+", "", t)
    if t.isdigit():
        return int(t)
    return ORDINALS.get(t)


def parse(command):
    """(ação, alvo | None, busca | None) por regex; None se precisa do LLM."""
    text = normalize(command)
    if not text:
        return None
    for action, rx in PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        groups = m.groupdict()
        target = (groups.get("t") or "").strip() or None
        query = (groups.get("q") or "").strip() or None
        if action == "GOTO_TAB" and target is None and m.groups():
            target = m.group(1)  # "terceira aba"
        return action, target, query
    return None


def resolve_site(target):
    """Alvo de nova aba → URL: URL/domínio digitado, site conhecido ou busca."""
    t = (target or "").strip()
    if not t:
        return None
    url = browser.normalize_url(t.replace(" ponto ", "."))  # STT: "github ponto com"
    if url:
        return url
    key = normalize(t)
    if key in SITES:
        return SITES[key]
    return SEARCH_URL + quote_plus(t)


def _ask_llm(command):
    from core.llm import query_ollama
    raw = query_ollama([{"role": "system", "content": DECISION_PROMPT}, {"role": "user", "content": command}],
                       format="json", temperature=0.1, timeout=settings.TIMEOUT_API)
    try:
        data = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("action") not in ACTIONS:
        return None
    target = data.get("target")
    return data["action"], (str(target).strip() or None) if target else None, None


# ------------------------------------------------------------ ações
def _format_tabs(tabs):
    lines = [f"{t['index']}. {t['title']}{'  ← ativa' if t['selected'] else ''}" for t in tabs]
    return f"{len(tabs)} aba(s) abertas, Senhor:\n" + "\n".join(lines)


def _find(win, target):
    """Aba pelo número/ordinal ou pelo nome → dict da aba ou None."""
    tabs = browser.list_tabs(win)
    ref = tab_ref(target)
    if ref is not None:
        if ref == -1 and tabs:
            return tabs[-1]
        return next((t for t in tabs if t["index"] == ref), None) if tabs else {"index": ref, "title": f"aba {ref}"}
    return browser.match_tab(tabs, target)


def _new_tab(win, target, query):
    if query:
        url = SEARCH_URL + quote_plus(query)
    else:
        url = resolve_site(target)
    if url:
        return f"Abrindo {target or query} numa aba nova." if browser.open_url(url) else "O navegador recusou a URL, Senhor."
    if not win:
        return NO_BROWSER
    return "Aba nova aberta." if browser.send_hotkey(win, "ctrl", "t") else NO_FOCUS


def _close_tab(win, target):
    if not target:
        return "Aba fechada." if browser.send_hotkey(win, "ctrl", "w") else NO_FOCUS
    tab = _find(win, target)
    if not tab:
        return f"Não achei nenhuma aba parecida com '{target}', Senhor."
    return f"Fechei a aba {tab['title']}." if browser.close_tab(win, tab["index"]) else NO_FOCUS


def _goto_tab(win, target):
    tab = _find(win, target)
    if tab:
        if browser.select_tab(win, tab["index"]) and browser.focus(win):
            return f"Na aba {tab['title']}."
        return NO_FOCUS
    if tab_ref(target) is None:
        url = resolve_site(target)
        if url and not url.startswith(SEARCH_URL):
            browser.open_url(url)
            return f"Não havia aba de {target} aberta; abri uma nova."
    return f"Não achei a aba '{target}', Senhor."


def _close_many(win, keep_active):
    """Fecha outras abas (keep_active) ou todas — sempre com confirmação."""
    tabs = browser.list_tabs(win)
    if not tabs:
        return NO_TABS
    victims = [t for t in tabs if not (keep_active and t["selected"])]
    if not victims:
        return "Só existe esta aba, Senhor. Nada a fechar."
    titles = ", ".join(t["title"] for t in victims[:5]) + ("…" if len(victims) > 5 else "")
    question = f"Fechar {len(victims)} aba(s): {titles}?"

    def confirm():
        if not keep_active:
            return "Janela do navegador fechada." if browser.send_hotkey(win, "ctrl", "shift", "w") else NO_FOCUS
        # Da direita para a esquerda: fechar não desloca os índices que faltam.
        closed = sum(1 for t in sorted(victims, key=lambda t: -t["index"]) if browser.close_tab(win, t["index"]))
        return f"{closed} aba(s) fechadas. Sobrou só a que importa."

    kind = "BROWSER_CLOSE_OTHERS" if keep_active else "BROWSER_CLOSE_ALL"
    if pending.arm(kind, question, confirm, target=titles) is None:
        return pending.BUSY_REPLY
    return f"{question} Diga **sim** para confirmar."


def run(action, target, query, win):
    if action == "NEW_TAB":
        return _new_tab(win, target, query)
    if not win:
        return NO_BROWSER
    if action in HOTKEYS:
        return REPLIES[action] if browser.send_hotkey(win, *HOTKEYS[action]) else NO_FOCUS
    if action == "CLOSE_TAB":
        return _close_tab(win, target)
    if action == "GOTO_TAB":
        return _goto_tab(win, target) if target else "Para qual aba, Senhor?"
    if action == "LIST_TABS":
        tabs = browser.list_tabs(win)
        return _format_tabs(tabs) if tabs else NO_TABS
    if action == "DUPLICATE":
        ok = browser.send_hotkey(win, "ctrl", "l") and browser.send_hotkey(win, "alt", "enter")
        return "Aba duplicada." if ok else NO_FOCUS
    if action == "CLOSE_OTHERS":
        return _close_many(win, keep_active=True)
    if action == "CLOSE_ALL":
        return _close_many(win, keep_active=False)
    return "Esse comando de aba não consta nos meus protocolos, Senhor."


def execute(entity, command=""):
    text = command or entity or ""
    decision = parse(text) or _ask_llm(text)
    if not decision:
        return "Não entendi o que fazer com as abas, Senhor."
    action, target, query = decision
    log.info(f"🌐 [BROWSER_TABS] {action} | alvo={target!r} busca={query!r}")
    try:
        return run(action, target, query, browser.find_browser_window())
    except Exception as e:
        log.error(f"[BROWSER_TABS] Falha: {e}")
        return "O navegador não colaborou dessa vez, Senhor."
