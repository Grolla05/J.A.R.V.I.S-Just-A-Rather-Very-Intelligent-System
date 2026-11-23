"""Controle da ponte Telegram/Discord (`messenger.py`): está rodando? deve rodar? sobe.

Leve (só config/logger/ctypes): o agente residente usa sem carregar o `core` inteiro.
A ponte em si confere a pref `remote_bot` a cada `PREF_POLL_S` e se encerra quando
ela é desligada — não há sinal para parar.
"""
import subprocess
from pathlib import Path

from .config import settings
from .logger import log

MUTEX = "Local\\JARVIS_MESSENGER"
SYNCHRONIZE = 0x00100000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
PREF_KEYS = {"telegram": "pref_remote_telegram", "discord": "pref_remote_discord"}


def has_token():
    return bool(settings.TELEGRAM_BOT_TOKEN or settings.DISCORD_BOT_TOKEN)


def _token(channel):
    return settings.TELEGRAM_BOT_TOKEN if channel == "telegram" else settings.DISCORD_BOT_TOKEN


def _pref(channel):
    """Lê a pref do canal direto do SQLite (sem importar o pacote core inteiro)."""
    import json
    import sqlite3
    try:
        conn = sqlite3.connect(str(settings.DB_PATH))
        try:
            row = conn.execute("SELECT value FROM config WHERE key = ?", (PREF_KEYS[channel],)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    if not row:
        return False
    try:
        return bool(json.loads(row[0]))
    except (TypeError, ValueError):
        return str(row[0]).lower() == "true"


def active_channels():
    """Canais com token no .env e ligados no /config → INTEGRAÇÕES."""
    return {ch for ch in PREF_KEYS if _token(ch) and _pref(ch)}


def should_run():
    return bool(active_channels())


def is_running():
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX)
    except (AttributeError, OSError):
        return False
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def script():
    return Path(settings.DIR_BACKEND) / "messenger.py"


def start(popen=subprocess.Popen):
    """Sobe a ponte desacoplada (se já não estiver no ar). True = rodando ou iniciada."""
    if is_running():
        return True
    from .autostart import pythonw_path
    try:
        popen([str(pythonw_path()), str(script())], cwd=str(settings.DIR_BACKEND),
              creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, close_fds=True)
        log.info("[PONTE] Processo da ponte iniciado.")
        return True
    except OSError as e:
        log.error(f"[PONTE] Falha ao iniciar a ponte: {e}")
        return False
