"""Ponte Telegram/Discord do J.A.R.V.I.S — processo próprio, sem janela (pythonw).

O cérebro roda aqui, no PC: Telegram e Discord são só o fio. Este processo abre
conexões de SAÍDA (long polling / gateway) — nenhuma porta aberta, nenhum webhook.

Quem sobe: o agente residente (no logon) e o /config quando a pref "Ponte
Telegram/Discord" é ligada em /config → INTEGRAÇÕES (`core/messenger_ctl.start`). Uma instância só (mutex
`Local\\JARVIS_MESSENGER`). Desligar a pref encerra a ponte em até `PREF_POLL_S`.

Rodar à mão (vê o log no console): `python messenger.py`.
"""
import os
import sys
import threading
from pathlib import Path

PREF_POLL_S = 30
ERROR_ALREADY_EXISTS = 183


def _prepare_environment():
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    app_dir = Path(__file__).resolve().parents[2]
    if (app_dir / "runtime").is_dir() and not os.getenv("JARVIS_DATA_DIR"):
        os.environ["JARVIS_DATA_DIR"] = str(Path(os.environ.get("APPDATA", "~")).expanduser() / "JARVIS")
    os.environ.setdefault("PYTHONUTF8", "1")
    backend = Path(__file__).resolve().parent
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


def _single_instance(name):
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, name)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def main():
    _prepare_environment()
    from core.messenger_ctl import MUTEX
    if _single_instance(MUTEX) is None:
        return 0

    from core import discord_bot, manager, messenger_ctl
    from core.config import settings
    from core.logger import log
    from core.telegram_bot import TelegramBridge
    from services import remote_chat

    if getattr(sys.stdout, "name", "") == os.devnull:
        log.use_tui()   # sem console: só arquivo de log
    if not messenger_ctl.should_run():
        log.info("[PONTE] Desligada (sem token ou canal desligado em /config → INTEGRAÇÕES).")
        return 0
    manager.ensure_loaded()   # skills (o brain roteia para elas)
    running = {}   # canal -> (thread, stop_event)

    def start_channel(channel):
        stop = threading.Event()
        if channel == "telegram":
            bridge = TelegramBridge(settings.TELEGRAM_BOT_TOKEN, remote_chat.handle_message)
            thread = threading.Thread(target=bridge.run, args=(stop,), name="jarvis-telegram", daemon=True)
        else:
            thread = threading.Thread(target=discord_bot.run, args=(settings.DISCORD_BOT_TOKEN,
                                                                    remote_chat.handle_message, stop),
                                      name="jarvis-discord", daemon=True)
        thread.start()
        running[channel] = (thread, stop)
        log.info(f"[PONTE] {channel} no ar.")

    def stop_channel(channel):
        thread, stop = running.pop(channel)
        stop.set()
        thread.join(timeout=5)
        log.info(f"[PONTE] {channel} desligado.")

    idle = threading.Event()
    while True:
        wanted = messenger_ctl.active_channels()
        for channel in set(running) - wanted:
            stop_channel(channel)
        for channel in wanted - set(running):
            start_channel(channel)
        if not running:
            log.info("[PONTE] Nenhum canal ligado: encerrando.")
            break
        idle.wait(PREF_POLL_S)
    return 0


if __name__ == "__main__":
    code = main()
    os._exit(code or 0)
