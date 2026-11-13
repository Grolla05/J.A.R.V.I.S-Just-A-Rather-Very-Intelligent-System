"""Agente residente do J.A.R.V.I.S — sobe com o Windows, sem janela (pythonw).

Segura o atalho global (GLOBAL_HOTKEY, padrão Win+J) e fica na bandeja:
- TUI fechada            -> abre a TUI já no Copilot;
- TUI aberta, sem foco   -> traz a janela para frente e manda ao Copilot;
- TUI em foco            -> volta ao Chat.
Fechar a TUI (Ctrl+Q ou o X) não fecha o agente: o próximo Win+J reabre.

Também segura TRANSLATE_HOTKEY (padrão Ctrl+Alt+T): copia o texto selecionado
em qualquer app, traduz no Ollama (pt → inglês, resto → pt-BR), põe a tradução
no clipboard e mostra num toast da bandeja.

Subindo com o Windows (`--logon`, gravado no valor do HKCU\\...\\Run), verifica
se há Release novo no GitHub; havendo, abre a TUI, que mostra a tela
"ATUALIZAÇÃO DISPONÍVEL!!" (core/updater.py). Qualquer tecla ali dispara o
evento `presence.INSTALL_UPDATE`: o agente espera a TUI fechar, instala e o
setup o reabre. Sem agente rodando, a TUI sobe um com `--install-update`.

Leve de propósito: nada de SystemInfo ou Textual; o Ollama só é tocado ao traduzir. Uma instância
só (mutex `Local\\JARVIS_AGENT`). Rodar: `pythonw agent.py` (ou `python agent.py`
para ver o log no console).
"""
import ctypes
import os
import sys
import threading
from pathlib import Path

MUTEX_NAME = "Local\\JARVIS_AGENT"
ERROR_ALREADY_EXISTS = 183
TRANSLATE_HOTKEY_ID = 0x4A54  # 'JT' — o Win+J usa 0x4A41
TOAST_CHARS = 240
LOGON_FLAG = "--logon"
INSTALL_FLAG = "--install-update"  # mesmo valor de core/updater.py
TRAY_WAIT_S = 5  # dá tempo do ícone da bandeja subir antes do 1º toast


def _prepare_environment():
    """Antes de importar `core`: pythonw não tem stdout (o logger escreve nele) e,
    no layout instalado, os dados graváveis ficam em %APPDATA%\\JARVIS (como no jarvis.cmd)."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    app_dir = Path(__file__).resolve().parents[2]  # {app}\app\backend\agent.py -> {app}
    if (app_dir / "runtime").is_dir() and not os.getenv("JARVIS_DATA_DIR"):
        os.environ["JARVIS_DATA_DIR"] = str(Path(os.environ.get("APPDATA", "~")).expanduser() / "JARVIS")
    os.environ.setdefault("PYTHONUTF8", "1")
    backend = Path(__file__).resolve().parent
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    # `import core.x` rodaria o core/__init__ (banco, MCP do Obsidian, todas as
    # skills, SystemInfo): pesado demais para quem vive na bandeja. Um pacote
    # `core` vazio apontando para a mesma pasta carrega só os submódulos usados.
    if "core" not in sys.modules:
        import types
        pkg = types.ModuleType("core")
        pkg.__path__ = [str(backend / "core")]
        sys.modules["core"] = pkg


def handle_hotkey(read_tui, launch, foreground, focus, signal):
    """Decide o que o Win+J faz. Dependências injetadas (testes sem Win32).
    Retorna 'launch', 'to_chat' ou 'summon'."""
    tui = read_tui()
    if not tui:
        launch()
        return "launch"
    hwnd = tui.get("hwnd")
    if hwnd and foreground() == hwnd:
        signal("TO_CHAT")
        return "to_chat"
    if hwnd:
        focus(hwnd)
    signal("SUMMON")
    return "summon"


def translate_selection(copy, translate, write, notify):
    """Fluxo do atalho de tradução. Dependências injetadas (testes sem Win32/Ollama).
    Retorna 'empty', 'no_model' ou 'ok'."""
    text = copy()
    if not text:
        notify("Selecione um texto antes de usar o atalho, Senhor.", "J.A.R.V.I.S — tradução")
        return "empty"
    translation, target = translate(text)
    if not translation:
        notify("O modelo não respondeu. O Ollama está rodando?", "J.A.R.V.I.S — tradução")
        return "no_model"
    write(translation)
    short = translation if len(translation) <= TOAST_CHARS else translation[:TOAST_CHARS - 1] + "…"
    notify(short, f"Tradução para {target} (copiada)")
    return "ok"


def run_update_check(from_logon, updater, notify, tui_open, sleep, launch_tui):
    """Thread do agente: avisa o resultado de uma atualização anterior e, só
    quando o agente subiu com o Windows, procura Release novo. Havendo, abre a
    TUI (ela mostra a tela de atualização). Devolve 'prompted', 'deferred'
    (TUI já aberta), 'no-update' ou None fora do logon."""
    sleep(TRAY_WAIT_S)
    updater.announce_result(notify)
    if not from_logon:
        return None
    # logo após o logon a rede pode não estar pronta: mesmas tentativas do install
    if not updater.check_available(use_cache=False, retries=updater.RETRY_DELAYS, sleep=sleep):
        return "no-update"
    if tui_open():
        return "deferred"
    launch_tui()
    return "prompted"


def run_install(updater, notify, tui_open, sleep, exit_agent):
    """Pedido da tela de atualização: instala e, com o setup aberto, fecha o
    agente (libera o runtime; o setup o reabre)."""
    status = updater.install_latest(notify, tui_open, sleep)
    if status == "installing":
        exit_agent()
    return status


def _single_instance():
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def _tray_image():
    from PIL import Image, ImageDraw

    from core.config import settings
    icon = settings.DIR_ROOT.parent / "jarvis.ico"  # instalado
    for path in (icon, settings.DIR_ROOT / "installer" / "assets" / "jarvis.ico"):
        if path.exists():
            return Image.open(path)
    # Sem .ico (installer/assets/jarvis.ico ainda não existe): marcador liso,
    # só porque o pystray exige uma imagem.
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=(0, 229, 255, 255))
    return img


def main():
    _prepare_environment()
    if _single_instance() is None:
        return 0  # já existe um agente rodando

    import time

    from core import autostart, launcher, presence, updater
    from core.config import settings
    from core.hotkey import GlobalHotkey
    from core.logger import log
    from core.window_utils import force_foreground, user32

    if sys.stdout is not None and getattr(sys.stdout, "name", "") == os.devnull:
        log.use_tui()  # sem console: só arquivo de log
    from_logon = LOGON_FLAG in sys.argv[1:]
    install_now = INSTALL_FLAG in sys.argv[1:]
    log.info(f"🛰️ Agente residente do J.A.R.V.I.S no ar{' (logon)' if from_logon else ''}.")
    autostart.ensure_logon_flag()

    def on_hotkey():
        action = handle_hotkey(presence.read_tui, lambda: launcher.launch_tui(copilot=True),
                               user32.GetForegroundWindow, force_foreground, presence.signal)
        log.info(f"Atalho global: {action}")

    tray = {"icon": None}

    def notify(message, title):
        icon = tray["icon"]
        if icon is not None:
            try:
                icon.notify(message, title)
                return
            except Exception as e:
                log.warning(f"Toast da bandeja falhou: {e}")
        log.info(f"{title}: {len(message)} caracteres (sem bandeja para mostrar).")

    def on_translate():
        from core import clipboard, selection

        def run():
            result = translate_selection(selection.copy_selection, clipboard.translate_auto,
                                         selection.write_clipboard, notify)
            log.info(f"Atalho de tradução: {result}")
        threading.Thread(target=run, daemon=True, name="jarvis-translate").start()

    hotkey = None
    translate_hotkey = None
    if settings.TRANSLATE_HOTKEY:
        try:
            translate_hotkey = GlobalHotkey(settings.TRANSLATE_HOTKEY, on_translate,
                                            hotkey_id=TRANSLATE_HOTKEY_ID, name="TRANSLATE_HOTKEY")
            translate_hotkey.start()
        except ValueError as e:
            log.warning(f"TRANSLATE_HOTKEY inválido: {e}")
    if settings.GLOBAL_HOTKEY:
        try:
            hotkey = GlobalHotkey(settings.GLOBAL_HOTKEY, on_hotkey)
            hotkey.start()
        except ValueError as e:
            log.warning(f"GLOBAL_HOTKEY inválido: {e}")

    def exit_agent():
        icon = tray["icon"]
        if icon is not None:
            try:
                icon.stop()
            except Exception as e:
                log.debug(f"Bandeja não fechou: {e}")
        os._exit(0)

    def tui_open():
        return bool(presence.read_tui())

    installing = threading.Lock()

    def start_install():
        if not installing.acquire(blocking=False):
            return  # já instalando (tecla dupla, sinal repetido)

        def run():
            status = run_install(updater, notify, tui_open, time.sleep, exit_agent)
            log.info(f"Atualização pedida pela TUI: {status}")
            installing.release()
        threading.Thread(target=run, daemon=True, name="jarvis-install").start()

    presence.wait_signals(lambda _name: start_install(), threading.Event(), events=presence.AGENT_EVENTS)
    if install_now:
        start_install()
    else:
        threading.Thread(
            target=run_update_check, daemon=True, name="jarvis-update",
            args=(from_logon, updater, notify, tui_open, time.sleep, lambda: launcher.launch_tui(copilot=False)),
        ).start()

    try:
        import pystray
    except ImportError:
        log.warning("pystray ausente: agente roda sem ícone na bandeja.")
        threading.Event().wait()  # segura o processo (o atalho vive na thread daemon)
        return 0

    def open_tui(_icon=None, _item=None):
        on_hotkey()

    def toggle_autostart(_icon, _item):
        autostart.set_enabled(not autostart.is_enabled())

    def quit_agent(icon, _item):
        for listener in (hotkey, translate_hotkey):
            if listener:
                listener.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Abrir J.A.R.V.I.S", open_tui, default=True),
        pystray.MenuItem("Iniciar com o Windows", toggle_autostart, checked=lambda _i: autostart.is_enabled()),
        pystray.MenuItem(f"Traduzir seleção: {settings.TRANSLATE_HOTKEY or 'desligado'}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair do agente", quit_agent),
    )
    title = f"J.A.R.V.I.S — {settings.GLOBAL_HOTKEY or 'sem atalho'}"
    tray["icon"] = pystray.Icon("jarvis", _tray_image(), title, menu)
    tray["icon"].run()
    log.info("Agente residente encerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
