"""Texto selecionado em qualquer app — usado pelo atalho de tradução do agente.

`copy_selection()` espera o usuário soltar o atalho, manda Ctrl+C para a janela
em foco e lê o clipboard pela API Win32 (CF_UNICODETEXT, sem PowerShell: rápido
e sem problema de acento). `write_clipboard()` devolve o resultado ao clipboard.

Só ctypes + logger: o agente residente importa isto sem carregar o pacote `core`.
Conteúdo copiado nunca vai para o log (só o tamanho).
"""
import ctypes
import time

from core.logger import log

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL, VK_C = 0x11, 0x43
_MODIFIERS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # shift, ctrl, alt, win esquerda/direita
RELEASE_TIMEOUT = 1.5   # s esperando o usuário soltar o atalho
COPY_TIMEOUT = 0.8      # s esperando o app colocar a seleção no clipboard
MAX_CHARS = 5000


def _win():
    """(user32, kernel32) com assinaturas de 64 bits (handles não cabem em int)."""
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
    return user32, kernel32


def _open_clipboard(user32, attempts=10):
    for _ in range(attempts):  # outro app pode estar com o clipboard aberto
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.03)
    return False


def read_clipboard():
    """Texto do clipboard ('' se vazio, não-texto ou ocupado)."""
    user32, kernel32 = _win()
    if not _open_clipboard(user32):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def write_clipboard(text):
    """Põe `text` no clipboard. True se conseguiu."""
    user32, kernel32 = _win()
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    if not _open_clipboard(user32):
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        ptr = kernel32.GlobalLock(handle) if handle else None
        if not ptr:
            return False
        ctypes.memmove(ptr, data, size)
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True  # o clipboard agora é dono do handle
    finally:
        user32.CloseClipboard()


def wait_modifiers_released(is_down, timeout=RELEASE_TIMEOUT, sleep=time.sleep, clock=time.monotonic):
    """Espera ctrl/alt/shift/win subirem — senão o Ctrl+C sai como Ctrl+Alt+C."""
    deadline = clock() + timeout
    while clock() < deadline:
        if not any(is_down(vk) for vk in _MODIFIERS):
            return True
        sleep(0.02)
    return False


def copy_selection(send_copy=None, sequence=None, read=read_clipboard, is_down=None,
                   sleep=time.sleep, clock=time.monotonic):
    """Copia a seleção da janela em foco e devolve o texto — None se nada foi copiado.
    Dependências injetáveis para teste (sem Win32)."""
    user32 = None
    if send_copy is None or sequence is None or is_down is None:
        user32 = ctypes.windll.user32
    is_down = is_down or (lambda vk: bool(user32.GetAsyncKeyState(vk) & 0x8000))
    sequence = sequence or user32.GetClipboardSequenceNumber
    send_copy = send_copy or (lambda: _send_ctrl_c(user32))

    wait_modifiers_released(is_down, sleep=sleep, clock=clock)
    before = sequence()
    send_copy()
    deadline = clock() + COPY_TIMEOUT
    while clock() < deadline:
        if sequence() != before:
            sleep(0.05)  # alguns apps escrevem em 2 etapas
            text = (read() or "").strip()
            log.debug(f"Seleção copiada: {len(text)} caracteres.")
            return text[:MAX_CHARS] or None
        sleep(0.02)
    log.info("Atalho de tradução: nada selecionado (clipboard não mudou).")
    return None


def _send_ctrl_c(user32):
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
