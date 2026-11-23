"""Captura de tela para a skill SCREEN_READ (Win32 + Pillow, sem LLM).

A imagem fica só em memória: nunca vai para o disco nem para o SQLite.

Janela-alvo: a janela em foco. Se ela for o próprio terminal do JARVIS (caso
comum no Chat, onde o usuário acabou de digitar), desce na ordem Z até a
primeira janela "de verdade" — visível, não minimizada, não oculta pelo DWM,
com título, fora do shell e sem ser janela de ferramenta. A escolha em si é
`pick_target()`, lógica pura testada sem Win32.
"""
import ctypes

from core.logger import log
from core.window_utils import _SHELL_CLASSES, RECT, get_monitors

GW_HWNDNEXT = 2
GA_ROOT = 2
GA_ROOTOWNER = 3
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
MIN_SIDE = 50        # janela menor que isso (px) não é alvo
MAX_Z_WALK = 200     # teto de janelas percorridas na ordem Z

_dpi_ready = False


def _ensure_dpi_aware():
    """Retângulos e captura na mesma escala (per-monitor DPI). Idempotente."""
    global _dpi_ready
    if _dpi_ready:
        return
    _dpi_ready = True
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception as e:
            log.debug(f"[SCREEN_CAPTURE] DPI awareness indisponível: {e}")


# ------------------------------------------------------------ lógica pura
def is_candidate(win, self_hwnds=()):
    """Janela serve de alvo? `win`: dict com hwnd, title, visible, iconic,
    cloaked, cls, tool, width, height."""
    return (win.get("hwnd") not in self_hwnds
            and win.get("visible") and not win.get("iconic") and not win.get("cloaked")
            and not win.get("tool") and bool((win.get("title") or "").strip())
            and win.get("cls") not in _SHELL_CLASSES
            and win.get("width", 0) >= MIN_SIDE and win.get("height", 0) >= MIN_SIDE)


def pick_target(candidates, self_hwnds=()):
    """1ª janela da lista (ordem Z, de cima para baixo) que serve de alvo, ou None."""
    for win in candidates:
        if is_candidate(win, self_hwnds):
            return win
    return None


def monitor_for(rect, monitors):
    """Monitor que contém o centro de `rect` (left, top, right, bottom); senão o 1º."""
    if not monitors:
        return None
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    for m in monitors:
        if m["x"] <= cx < m["x"] + m["width"] and m["y"] <= cy < m["y"] + m["height"]:
            return m
    return monitors[0]


def monitor_bbox(m):
    return (m["x"], m["y"], m["x"] + m["width"], m["y"] + m["height"])


# ------------------------------------------------------------------ Win32
def _user32():
    return ctypes.windll.user32


def window_rect(hwnd):
    """(left, top, right, bottom) sem a sombra (DWM); fallback GetWindowRect."""
    rect = RECT()
    try:
        ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)) == 0
    except Exception:
        ok = False
    if not ok:
        _user32().GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def _describe(hwnd):
    """Dict de `is_candidate` para um HWND real."""
    user32 = _user32()
    length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, length + 1)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    cloaked = ctypes.c_int(0)
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked),
                                                   ctypes.sizeof(cloaked))
    except Exception:
        pass
    left, top, right, bottom = window_rect(hwnd)
    return {
        "hwnd": hwnd, "title": title.value, "cls": cls.value,
        "visible": bool(user32.IsWindowVisible(hwnd)), "iconic": bool(user32.IsIconic(hwnd)),
        "cloaked": bool(cloaked.value),
        "tool": bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW),
        "width": right - left, "height": bottom - top,
    }


def _registered_hwnd():
    """HWND gravado pela própria TUI no boot (`presence.register_tui`), ou 0."""
    try:
        import os

        from core import presence
        data = presence.read_tui()
        return data["hwnd"] if data and data["pid"] == os.getpid() else 0
    except Exception as e:
        log.debug(f"[SCREEN_CAPTURE] tui.json indisponível: {e}")
        return 0


def _self_hwnds():
    """HWNDs do próprio JARVIS: o gravado no boot (com o terminal em foco) e o
    terminal achado pelo console. Sem o fallback de `find_terminal_window` para
    a janela em foco — no Copilot ela é o app do usuário, não o JARVIS."""
    user32 = _user32()
    hwnds = {_registered_hwnd()}
    try:
        console = ctypes.windll.kernel32.GetConsoleWindow()
        for hwnd in (console, user32.GetAncestor(console, GA_ROOTOWNER) if console else 0):
            if hwnd and user32.IsWindowVisible(hwnd):
                hwnds |= {hwnd, user32.GetAncestor(hwnd, GA_ROOT)}
    except Exception as e:
        log.debug(f"[SCREEN_CAPTURE] Terminal não identificado: {e}")
    return hwnds - {0, None}


def _z_order_from(hwnd):
    """Janelas a partir de `hwnd`, descendo na ordem Z."""
    user32 = _user32()
    out = []
    while hwnd and len(out) < MAX_Z_WALK:
        out.append(hwnd)
        hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
    return out


def target_window():
    """Dict da janela-alvo (ver `is_candidate`) ou None."""
    _ensure_dpi_aware()
    user32 = _user32()
    start = user32.GetForegroundWindow() or user32.GetTopWindow(None)
    mine = _self_hwnds()
    return pick_target((_describe(h) for h in _z_order_from(start)), mine)


def capture(scope="window", monitor_idx=None, grab=None):
    """(PIL.Image, rótulo) da janela-alvo ou de um monitor; (None, "") se falhar.

    scope="window": só a janela-alvo. scope="monitor": o monitor `monitor_idx`
    (1 = o mais à esquerda) ou, sem índice, o monitor da janela-alvo."""
    try:
        _ensure_dpi_aware()
        if grab is None:
            from PIL import ImageGrab
            grab = ImageGrab.grab
        win = target_window()
        if scope == "monitor":
            monitors = get_monitors()
            if monitor_idx and 1 <= monitor_idx <= len(monitors):
                mon = monitors[monitor_idx - 1]
            else:
                mon = monitor_for(window_rect(win["hwnd"]), monitors) if win else (monitors or [None])[0]
            if not mon:
                return None, ""
            idx = monitors.index(mon) + 1
            return grab(bbox=monitor_bbox(mon), all_screens=True), f"monitor {idx}"
        if not win:
            return None, ""
        return grab(bbox=window_rect(win["hwnd"]), all_screens=True), win["title"]
    except Exception as e:
        log.warning(f"[SCREEN_CAPTURE] Captura falhou: {e}")
        return None, ""
