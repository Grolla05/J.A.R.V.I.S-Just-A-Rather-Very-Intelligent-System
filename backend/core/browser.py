"""Navegador Chromium (Opera GX, Chrome, Edge, Brave, Vivaldi) sem extensão nem CDP.

Duas ferramentas, nenhuma exige configurar o navegador:
- **atalhos de teclado** (pyautogui) na janela do navegador, que é focada antes —
  se o foco não vier, nenhuma tecla é enviada (cairia em outra janela);
- **UI Automation do Windows** (comtypes, import tardio) para ler a URL da aba
  ativa e a lista de abas, selecionar e fechar uma aba pelo botão "x".

Sem `--remote-debugging-port` de propósito: com ele qualquer processo local
dirigiria o navegador logado do usuário. Firefox fica de fora (árvore UIA própria).

Tudo aqui é chamado de threads (skills): nada toca em widget e nada levanta —
falha vira `None`/`False`/`[]` + log. A lógica de escolha e de texto
(`pick_browsers`, `normalize_url`, `match_tab`, `is_fetch_safe`) é pura e testada.
"""
import difflib
import ipaddress
import re
import time
import unicodedata
from urllib.parse import parse_qsl, urlsplit

from core.logger import log
from core.window_utils import CHROMIUM_APPS

# --- UI Automation (UIAutomationClient.h) ---
_TREE_CHILDREN = 2
_TREE_DESCENDANTS = 4
_PROP_CONTROL_TYPE = 30003
_CT_BUTTON = 50000
_CT_EDIT = 50004
_CT_TAB = 50018
_CT_TAB_ITEM = 50019
_PAT_INVOKE = 10000
_PAT_VALUE = 10002
_PAT_SELECTION_ITEM = 10010

FOCUS_SETTLE_S = 0.15   # o Windows leva um instante para entregar o foco
MAX_TABS = 200          # teto de abas lidas de uma janela

# Parâmetros de URL que denunciam link de uso único / credencial: a página
# nunca é baixada de novo (consumiria o link de reset de senha, o código OAuth…).
_SENSITIVE_PARAMS = ("token", "code", "key", "sig", "auth", "session", "sess", "password", "passwd",
                     "pass", "secret", "otp", "ticket", "state", "nonce", "jwt", "credential")
_LOCAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".test")
_DOMAIN_RE = re.compile(r"^[\w-]+(\.[\w-]+)+(:\d+)?(/\S*)?$")
# Estados que o Chromium pendura no nome da aba (UIA): "Título - Memory usage - 86.0 MB"
_TAB_STATUS_RE = re.compile(
    r"\s+-\s+(?:memory usage|uso de mem[oó]ria|audio playing|reproduzindo [aá]udio|tab muted|"
    r"[aá]udio (?:desativado|silenciado)|network error|erro de rede|pinned|fixad[ao]|"
    r"(?:this tab is )?using your (?:camera|microphone)|usando (?:a )?(?:c[aâ]mera|microfone)).*$",
    re.IGNORECASE)


# ------------------------------------------------------------ lógica pura
def _fold(text):
    """Minúsculas, sem acento, espaços colapsados."""
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.split())


def clean_tab_title(name):
    """Nome da aba sem os estados do Chromium (memória, áudio, fixada…) e sem
    caracteres invisíveis."""
    name = (name or "").replace("​", "").replace("‎", "").strip()
    return _TAB_STATUS_RE.sub("", name).strip()


def is_browser(win):
    return bool(win) and (win.get("process") or "").lower() in CHROMIUM_APPS


def pick_browsers(candidates, self_hwnds=()):
    """Janelas de navegador Chromium úteis, na ordem recebida (ordem Z).
    Minimizada vale (o foco a restaura); oculta, de ferramenta ou sem título, não."""
    out = []
    for win in candidates:
        if (win.get("hwnd") not in self_hwnds and win.get("visible") and not win.get("cloaked")
                and not win.get("tool") and (win.get("title") or "").strip() and is_browser(win)):
            out.append(win)
    return out


def normalize_url(value):
    """Texto do campo de endereço → URL http(s) ou ''. O Chromium esconde o
    'https://' fora de foco ("github.com/x" vira "https://github.com/x");
    texto de busca, chrome://, about: e afins → ''."""
    value = (value or "").strip()
    if not value or " " in value:
        return ""
    low = value.lower()
    if low.startswith(("http://", "https://")):
        return value
    if "://" in low or low.startswith(("about:", "data:", "javascript:", "file:", "view-source:")):
        return ""
    return f"https://{value}" if _DOMAIN_RE.match(value) else ""


def is_fetch_safe(url):
    """A página da aba pode ser baixada de novo pelo JARVIS? Só http(s) público,
    sem usuário/senha na URL e sem parâmetro com cara de credencial."""
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return False
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES) or "." not in host.strip("[]"):
        return False
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        if not ip.is_global:
            return False
    except ValueError:
        pass  # nome de domínio
    params = parse_qsl(parts.query, keep_blank_values=True) + parse_qsl(parts.fragment, keep_blank_values=True)
    for name, _ in params:
        low = name.lower()
        if any(s in low for s in _SENSITIVE_PARAMS):
            return False
    return True


def match_tab(tabs, term):
    """Aba cujo título casa com o termo falado: igual → contém → parecido
    (difflib 0.6, mesmo corte do Spotify/APP_CONTROL). None se nada servir."""
    alvo = _fold(term)
    if not alvo or not tabs:
        return None
    titled = [(t, _fold(t.get("title"))) for t in tabs if (t.get("title") or "").strip()]
    for tab, title in titled:
        if title == alvo:
            return tab
    contains = [(tab, title) for tab, title in titled if alvo in title]
    if contains:
        return min(contains, key=lambda pair: len(pair[1]))[0]
    names = [title for _, title in titled]
    best = difflib.get_close_matches(alvo, names, n=1, cutoff=0.6)
    if best:
        return next(tab for tab, title in titled if title == best[0])
    # Palavra a palavra: "aba do github" acha "Pull requests · Grolla05/J.A.R.V.I.S · GitHub"
    for tab, title in titled:
        words = re.findall(r"\w+", title)
        if difflib.get_close_matches(alvo, words, n=1, cutoff=0.8):
            return tab
    return None


# ------------------------------------------------------------ janelas (Win32)
def _process_name(hwnd):
    import ctypes
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        import psutil
        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""


def find_browser_windows():
    """Janelas de navegador Chromium, da mais recente para a mais antiga (ordem Z).
    Pula o terminal do JARVIS, como a leitura de tela."""
    try:
        from core import screen_capture as sc
        sc._ensure_dpi_aware()
        user32 = sc._user32()
        start = user32.GetForegroundWindow() or user32.GetTopWindow(None)
        wins = []
        for hwnd in sc._z_order_from(start):
            info = sc._describe(hwnd)
            if info.get("visible") and (info.get("title") or "").strip():
                info["process"] = _process_name(hwnd)
                wins.append(info)
        return pick_browsers(wins, sc._self_hwnds())
    except Exception as e:
        log.warning(f"[BROWSER] Não consegui listar as janelas: {e}")
        return []


def find_browser_window():
    """A janela de navegador mais recente, ou None."""
    wins = find_browser_windows()
    return wins[0] if wins else None


def foreground():
    import ctypes
    return ctypes.windll.user32.GetForegroundWindow()


def _tap_alt():
    import ctypes
    vk_menu, keyup = 0x12, 0x0002
    ctypes.windll.user32.keybd_event(vk_menu, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk_menu, 0, keyup, 0)


def focus(win):
    """Traz o navegador para a frente. True só se o Windows entregou o foco."""
    if not win:
        return False
    try:
        from core.window_utils import force_foreground
        force_foreground(win["hwnd"])
        time.sleep(FOCUS_SETTLE_S)
        if foreground() == win["hwnd"]:
            return True
        # Foreground-lock: o Windows só cede o foco a quem gerou a última entrada.
        # Um toque sintético de Alt conta como entrada nossa e destrava o pedido.
        _tap_alt()
        force_foreground(win["hwnd"])
        time.sleep(FOCUS_SETTLE_S)
        return foreground() == win["hwnd"]
    except Exception as e:
        log.warning(f"[BROWSER] Foco falhou: {e}")
        return False


def restore_focus(hwnd):
    """Devolve o foco para a janela em que o usuário estava (best effort)."""
    if not hwnd:
        return
    try:
        from core.window_utils import force_foreground
        force_foreground(hwnd)
    except Exception as e:
        log.debug(f"[BROWSER] Não devolvi o foco: {e}")


def send_hotkey(win, *keys, presses=1):
    """Foca o navegador e manda o atalho. Sem foco, não manda nada."""
    if not focus(win):
        log.warning(f"[BROWSER] Atalho {keys} não enviado: o navegador não recebeu o foco.")
        return False
    import pyautogui  # import tardio: nada de automação no import do módulo
    for _ in range(max(1, presses)):
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
    return True


def open_url(url):
    """Abre a URL numa aba nova do navegador padrão. Só http(s)."""
    if not (url or "").lower().startswith(("http://", "https://")):
        return False
    try:
        import webbrowser
        return bool(webbrowser.open(url, new=2))
    except Exception as e:
        log.warning(f"[BROWSER] Falha ao abrir {url}: {e}")
        return False


# ------------------------------------------------------------ UI Automation
def _uia():
    """(IUIAutomation, módulo gerado) ou (None, None). Inicializa o COM na thread."""
    try:
        import comtypes
        import comtypes.client
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)
        except OSError:
            pass  # thread já inicializada (outro modelo de apartment) — segue
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as mod
        return comtypes.client.CreateObject(mod.CUIAutomation, interface=mod.IUIAutomation), mod
    except Exception as e:
        log.warning(f"[BROWSER] UI Automation indisponível: {e}")
        return None, None


def _root(uia, win):
    return uia.ElementFromHandle(win["hwnd"])


def _cond(uia, control_type):
    return uia.CreatePropertyCondition(_PROP_CONTROL_TYPE, control_type)


def _elements(array):
    if not array:
        return []
    return [array.GetElement(i) for i in range(min(array.Length, MAX_TABS))]


def _tab_items(uia, win):
    """Elementos TabItem da faixa de abas (procura a faixa primeiro: é rápido e
    não desce no conteúdo da página)."""
    root = _root(uia, win)
    strip = root.FindFirst(_TREE_DESCENDANTS, _cond(uia, _CT_TAB))
    scope = strip if strip else root
    items = _elements(scope.FindAll(_TREE_DESCENDANTS, _cond(uia, _CT_TAB_ITEM)))
    return [el for el in items if (el.CurrentName or "").strip()]


def _is_selected(el, mod):
    try:
        pattern = el.GetCurrentPattern(_PAT_SELECTION_ITEM)
        return bool(pattern and pattern.QueryInterface(mod.IUIAutomationSelectionItemPattern).CurrentIsSelected)
    except Exception:
        return False


def active_url(win):
    """URL da aba ativa (campo de endereço), ou ''."""
    if not is_browser(win):
        return ""
    uia, mod = _uia()
    if not uia:
        return ""
    try:
        edit = _root(uia, win).FindFirst(_TREE_DESCENDANTS, _cond(uia, _CT_EDIT))
        if not edit:
            return ""
        pattern = edit.GetCurrentPattern(_PAT_VALUE)
        value = pattern.QueryInterface(mod.IUIAutomationValuePattern).CurrentValue if pattern else ""
        return normalize_url(value)
    except Exception as e:
        log.debug(f"[BROWSER] URL da aba indisponível: {e}")
        return ""


def list_tabs(win):
    """[{'index': 1.., 'title', 'selected'}] da janela; [] se não der para ler."""
    if not is_browser(win):
        return []
    uia, mod = _uia()
    if not uia:
        return []
    try:
        return [{"index": i, "title": clean_tab_title(el.CurrentName), "selected": _is_selected(el, mod)}
                for i, el in enumerate(_tab_items(uia, win), 1)]
    except Exception as e:
        log.debug(f"[BROWSER] Abas indisponíveis: {e}")
        return []


def _tab_element(win, index):
    uia, mod = _uia()
    if not uia:
        return None, None
    try:
        items = _tab_items(uia, win)
    except Exception as e:
        log.debug(f"[BROWSER] Abas indisponíveis: {e}")
        return None, None
    if index == -1:
        index = len(items)
    if not 1 <= index <= len(items):
        return None, None
    return items[index - 1], (uia, mod)


def select_tab(win, index):
    """Ativa a aba `index` (1..n; -1 = última). UIA primeiro; atalho Ctrl+1..9 de reserva."""
    el, ctx = _tab_element(win, index)
    if el is not None:
        try:
            pattern = el.GetCurrentPattern(_PAT_SELECTION_ITEM)
            pattern.QueryInterface(ctx[1].IUIAutomationSelectionItemPattern).Select()
            return True
        except Exception as e:
            log.debug(f"[BROWSER] Select da aba falhou, indo de atalho: {e}")
    if index == -1:
        return send_hotkey(win, "ctrl", "9")
    if 1 <= index <= 8:
        return send_hotkey(win, "ctrl", str(index))
    return False


def close_tab(win, index):
    """Fecha a aba `index` pelo botão "x" (sem trocar de aba); de reserva,
    seleciona e manda Ctrl+W."""
    el, ctx = _tab_element(win, index)
    if el is not None:
        try:
            button = el.FindFirst(_TREE_DESCENDANTS, _cond(ctx[0], _CT_BUTTON))
            if button:
                pattern = button.GetCurrentPattern(_PAT_INVOKE)
                pattern.QueryInterface(ctx[1].IUIAutomationInvokePattern).Invoke()
                return True
        except Exception as e:
            log.debug(f"[BROWSER] Botão de fechar falhou, indo de atalho: {e}")
    return select_tab(win, index) and send_hotkey(win, "ctrl", "w")
