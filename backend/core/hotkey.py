"""Atalho global do Windows (RegisterHotKey) — usado pelo agente residente.

`parse_hotkey("win+j")` é pura (testada). `GlobalHotkey` registra o atalho numa
thread daemon com laço de mensagens próprio: o RegisterHotKey entrega WM_HOTKEY
na fila da thread que registrou, então registro, laço e cancelamento vivem
todos nela.
"""
import ctypes
import threading
from ctypes import wintypes

from .logger import log

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

_MODS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "shift": MOD_SHIFT,
         "win": MOD_WIN, "super": MOD_WIN, "meta": MOD_WIN}


def _vk(key):
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())  # VK_A..VK_Z = 'A'..'Z', VK_0..VK_9 = '0'..'9'
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return 0x70 + int(key[1:]) - 1  # VK_F1 = 0x70
    if key == "space":
        return 0x20
    raise ValueError(f"tecla não suportada: {key!r}")


def parse_hotkey(spec):
    """'win+j' -> (MOD_WIN, ord('J')). Exige ao menos um modificador e uma tecla."""
    parts = [p.strip().lower() for p in (spec or "").split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError(f"atalho inválido: {spec!r} (use algo como win+j)")
    mods = 0
    for part in parts[:-1]:
        if part not in _MODS:
            raise ValueError(f"modificador desconhecido: {part!r}")
        mods |= _MODS[part]
    return mods, _vk(parts[-1])


class GlobalHotkey:
    """Chama `callback()` (na thread do laço) a cada pressionamento do atalho."""

    HOTKEY_ID = 0x4A41  # 'JA'

    def __init__(self, spec, callback):
        self.spec = spec
        self.mods, self.vk = parse_hotkey(spec)
        self._callback = callback
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self.registered = False

    def start(self, timeout=2.0):
        """Registra e começa a ouvir. Retorna False se o atalho já estiver em uso."""
        self._thread = threading.Thread(target=self._loop, daemon=True, name="jarvis-hotkey")
        self._thread.start()
        self._ready.wait(timeout)
        return self.registered

    def stop(self):
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _loop(self):
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self.registered = bool(user32.RegisterHotKey(None, self.HOTKEY_ID, self.mods | MOD_NOREPEAT, self.vk))
        self._ready.set()
        if not self.registered:
            log.warning(f"Atalho global '{self.spec}' já está em uso no Windows. "
                        "Troque GLOBAL_HOTKEY no .env (ex: ctrl+alt+j).")
            return
        log.info(f"⌨️ Atalho global {self.spec} registrado.")
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                    try:
                        self._callback()
                    except Exception as e:
                        log.error(f"Atalho global: callback falhou: {e}")
        finally:
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
