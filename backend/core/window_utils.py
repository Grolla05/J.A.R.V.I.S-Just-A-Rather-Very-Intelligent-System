"""Helpers Win32 compartilhados para foco/posicionamento de janelas.

Centraliza o que antes estava duplicado (e quebrado) em screen_control.py
e app_control.py: enumerar monitores, achar HWND por título/PID e forçar
foreground respeitando a restrição de foreground-lock do Windows.
"""
import ctypes

from core.logger import log

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]


def get_monitors():
    """Enumera monitores via EnumDisplayMonitors, ordenados da esquerda para a direita."""
    monitors = []

    def _cb(hMonitor, hdcMonitor, lprcMonitor, dwData):
        r = lprcMonitor.contents
        monitors.append({"handle": hMonitor, "x": r.left, "y": r.top, "width": r.right - r.left, "height": r.bottom - r.top})
        return True

    user32.EnumDisplayMonitors(None, None, ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(RECT), ctypes.c_double)(_cb), 0)
    monitors.sort(key=lambda m: m["x"])
    return monitors


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]


MONITOR_DEFAULTTONEAREST = 2
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd"}


WS_CAPTION = 0x00C00000
GWL_STYLE = -16


def covers_monitor(window, monitor):
    """Retângulo da janela cobre o monitor inteiro? (lógica pura)"""
    return (window[0] <= monitor[0] and window[1] <= monitor[1]
            and window[2] >= monitor[2] and window[3] >= monitor[3])


def looks_fullscreen(window, monitor, zoomed, caption):
    """Tela cheia de verdade (jogo, F11, vídeo, apresentação) — não uma janela comum
    maximizada num monitor sem barra de tarefas, que também cobre o monitor."""
    return covers_monitor(window, monitor) and not (zoomed and caption)


def is_foreground_fullscreen():
    """App em tela cheia em foco (jogo, vídeo, apresentação)? Desktop e barra de tarefas não contam."""
    from ctypes import wintypes
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
    hwnd = user32.GetForegroundWindow()
    if not hwnd or hwnd == user32.GetShellWindow():
        return False
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, 64)
    if cls.value in _SHELL_CLASSES:
        return False
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    m = info.rcMonitor
    caption = bool(user32.GetWindowLongW(hwnd, GWL_STYLE) & WS_CAPTION)
    return looks_fullscreen((rect.left, rect.top, rect.right, rect.bottom), (m.left, m.top, m.right, m.bottom),
                            bool(user32.IsZoomed(hwnd)), caption)


# Processos que, em tela cheia, contam como apresentação (slides e leitores de PDF)
PRESENTATION_APPS = {"powerpnt.exe", "canva.exe", "acrord32.exe", "acrobat.exe", "sumatrapdf.exe",
                     "foxitpdfreader.exe", "foxitreader.exe"}
# Navegadores: em tela cheia só contam quando o título da aba é de um editor de slides
BROWSER_APPS = {"chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe", "vivaldi.exe"}
SLIDE_TITLE_HINTS = ("canva", "google slides", "apresentações google", "powerpoint")
# Pref `presentation_open`: o PowerPoint em foco conta mesmo sem tela cheia (.pptx aberto)
OPEN_APPS = {"powerpnt.exe"}


def looks_presenting(process_name, fullscreen, title="", app_open=False):
    """Apresentação = app de slides/PDF em tela cheia, navegador em tela cheia
    numa aba de slides (Canva, Google Slides, PowerPoint Online) ou — com
    `app_open` — o PowerPoint em foco mesmo em janela. Lógica pura (testável)."""
    name = (process_name or "").lower()
    if app_open and name in OPEN_APPS:
        return True
    if not fullscreen:
        return False
    if name in PRESENTATION_APPS:
        return True
    text = (title or "").lower()
    return name in BROWSER_APPS and any(hint in text for hint in SLIDE_TITLE_HINTS)


def foreground_process_name():
    """Nome do executável da janela em foco ('' se não der para descobrir)."""
    from ctypes import wintypes
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        import psutil
        return psutil.Process(pid.value).name()
    except Exception:
        return ""


def foreground_window_title():
    """Título da janela em foco ('' se não houver) — no navegador, o da aba."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value


def is_presenting(app_open=False):
    """Slides/PDF em tela cheia em foco (PowerPoint F5, Canva, Google Slides…)?
    `app_open=True` também conta o PowerPoint em foco sem tela cheia."""
    fullscreen = is_foreground_fullscreen()
    if not (fullscreen or app_open):
        return False
    return looks_presenting(foreground_process_name(), fullscreen,
                            foreground_window_title() if fullscreen else "", app_open)


def get_active_window_handle():
    return user32.GetForegroundWindow()


def find_window_by_title(partial_title):
    """Busca HWND de uma janela pelo título parcial (ex: 'Spotify')."""
    found_hwnd = None
    target = partial_title.lower()

    def _enum_cb(hwnd, lParam):
        nonlocal found_hwnd
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.lower()

            if target in title and user32.IsWindowVisible(hwnd):
                found_hwnd = hwnd
                return False
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong, ctypes.c_long)(_enum_cb), 0)
    return found_hwnd


def find_window_by_pid(pid):
    """Busca o primeiro HWND visível com título pertencente a um processo (por PID)."""
    found_hwnd = None

    def _enum_cb(hwnd, lParam):
        nonlocal found_hwnd
        if not user32.IsWindowVisible(hwnd):
            return True
        owner_pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value == pid and user32.GetWindowTextLengthW(hwnd) > 0:
            found_hwnd = hwnd
            return False
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong, ctypes.c_long)(_enum_cb), 0)
    return found_hwnd


def get_window_placement(hwnd):
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect


def force_foreground(hwnd):
    """Traz uma janela pro primeiro plano contornando a restrição de foreground-lock do Windows.

    SetForegroundWindow sozinho é ignorado pelo Windows na maioria dos casos em que o processo
    chamador não é o dono do foco atual. O contorno documentado é anexar a thread atual à thread
    da janela em foco via AttachThreadInput antes de chamar SetForegroundWindow.
    """
    if not hwnd:
        return False

    fg_hwnd = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)

    attached = []
    for t in (fg_thread, target_thread):
        if t and t != current_thread and user32.AttachThreadInput(current_thread, t, True):
            attached.append(t)

    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE

        user32.BringWindowToTop(hwnd)
        result = bool(user32.SetForegroundWindow(hwnd))
    finally:
        for t in attached:
            user32.AttachThreadInput(current_thread, t, False)

    if not result:
        log.warning(f"⚠️ [WINDOW_UTILS] SetForegroundWindow recusado pelo Windows para hwnd={hwnd} (foreground-lock).")

    return result


GA_ROOTOWNER = 3


def find_terminal_window(fallback=None):
    """HWND da janela do terminal que hospeda este processo.

    No conhost é o próprio GetConsoleWindow(). No Windows Terminal ele devolve
    uma pseudo-janela oculta cujo dono-raiz é a janela do WT (versões novas);
    quando nem isso é visível, usa `fallback` (o GetForegroundWindow() lido no
    boot, quando o terminal recém-aberto está em foco)."""
    console = kernel32.GetConsoleWindow()
    for hwnd in (console, user32.GetAncestor(console, GA_ROOTOWNER) if console else 0):
        if hwnd and user32.IsWindowVisible(hwnd):
            return hwnd
    return fallback or user32.GetForegroundWindow() or 0
