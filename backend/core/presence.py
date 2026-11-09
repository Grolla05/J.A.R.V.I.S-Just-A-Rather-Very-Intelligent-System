"""Ponte TUI ⇄ agente residente (agent.py): arquivo de presença + eventos nomeados.

A TUI grava `tui.json` ({pid, hwnd}) em settings.DIR_DATA ao subir e apaga ao
sair; o agente lê para saber se ela está aberta e qual janela focar. Para
mandar a TUI ao Copilot (ou de volta ao Chat) o agente dispara um evento
nomeado do Windows, que uma thread daemon da TUI espera. Sem socket, sem HTTP.
"""
import ctypes
import json
import os
import threading

from .config import settings
from .logger import log

SUMMON = "SUMMON"    # ir ao Copilot
TO_CHAT = "TO_CHAT"  # voltar ao Chat
EVENTS = {SUMMON: "Local\\JARVIS_SUMMON", TO_CHAT: "Local\\JARVIS_TO_CHAT"}

EVENT_MODIFY_STATE, SYNCHRONIZE = 0x0002, 0x00100000
WAIT_TIMEOUT = 0x102
POLL_MS = 500


def presence_path():
    return settings.DIR_DATA / "tui.json"


def _pid_alive(pid):
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        return False


def register_tui(hwnd, pid=None):
    """Anuncia a TUI aberta (chamado no on_mount com serviços ligados)."""
    data = {"pid": pid or os.getpid(), "hwnd": int(hwnd or 0)}
    try:
        presence_path().write_text(json.dumps(data), encoding="utf-8")
    except OSError as e:
        log.warning(f"Presença da TUI não gravada: {e}")
    return data


def unregister_tui(pid=None):
    """Apaga o arquivo se ele ainda for desta TUI."""
    path = presence_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if int(data.get("pid", 0)) == (pid or os.getpid()):
            path.unlink()
    except (OSError, ValueError):
        pass


def read_tui():
    """{pid, hwnd} da TUI aberta, ou None (arquivo órfão de TUI morta é apagado)."""
    path = presence_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not _pid_alive(data.get("pid", 0)):
        try:
            path.unlink()
        except OSError:
            pass
        return None
    return {"pid": int(data["pid"]), "hwnd": int(data.get("hwnd") or 0)}


def signal(name):
    """Dispara o evento nomeado (agente -> TUI). False se a TUI não o criou."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, EVENTS[name])
    if not handle:
        return False
    try:
        return bool(kernel32.SetEvent(handle))
    finally:
        kernel32.CloseHandle(handle)


def wait_signals(callback, stop_event):
    """Thread daemon da TUI: cria os eventos e chama callback(nome) a cada sinal."""
    kernel32 = ctypes.windll.kernel32
    names = list(EVENTS)
    handles = [kernel32.CreateEventW(None, False, False, EVENTS[n]) for n in names]  # auto-reset
    if not all(handles):
        log.warning("Eventos de invocação (Win+J) indisponíveis.")
        return None
    array = (ctypes.c_void_p * len(handles))(*handles)

    def loop():
        try:
            while not stop_event.is_set():
                result = kernel32.WaitForMultipleObjects(len(handles), array, False, POLL_MS)
                if result == WAIT_TIMEOUT:
                    continue
                if 0 <= result < len(handles):
                    try:
                        callback(names[result])
                    except Exception as e:
                        log.debug(f"Sinal {names[result]} falhou: {e}")
                else:
                    break  # WAIT_FAILED
        finally:
            for handle in handles:
                kernel32.CloseHandle(handle)

    thread = threading.Thread(target=loop, daemon=True, name="jarvis-presence")
    thread.start()
    return thread
