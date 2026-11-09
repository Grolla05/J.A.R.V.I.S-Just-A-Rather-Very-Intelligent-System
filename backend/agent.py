"""Agente residente do J.A.R.V.I.S — sobe com o Windows, sem janela (pythonw).

Segura o atalho global (GLOBAL_HOTKEY, padrão Win+J) e fica na bandeja:
- TUI fechada            -> abre a TUI já no Copilot;
- TUI aberta, sem foco   -> traz a janela para frente e manda ao Copilot;
- TUI em foco            -> volta ao Chat.
Fechar a TUI (Ctrl+Q ou o X) não fecha o agente: o próximo Win+J reabre.

Leve de propósito: nada de Ollama, SystemInfo ou Textual aqui. Uma instância
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

    from core import autostart, launcher, presence
    from core.config import settings
    from core.hotkey import GlobalHotkey
    from core.logger import log
    from core.window_utils import force_foreground, user32

    if sys.stdout is not None and getattr(sys.stdout, "name", "") == os.devnull:
        log.use_tui()  # sem console: só arquivo de log
    log.info("🛰️ Agente residente do J.A.R.V.I.S no ar.")

    def on_hotkey():
        action = handle_hotkey(presence.read_tui, lambda: launcher.launch_tui(copilot=True),
                               user32.GetForegroundWindow, force_foreground, presence.signal)
        log.info(f"Atalho global: {action}")

    hotkey = None
    if settings.GLOBAL_HOTKEY:
        try:
            hotkey = GlobalHotkey(settings.GLOBAL_HOTKEY, on_hotkey)
            hotkey.start()
        except ValueError as e:
            log.warning(f"GLOBAL_HOTKEY inválido: {e}")

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
        if hotkey:
            hotkey.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Abrir J.A.R.V.I.S", open_tui, default=True),
        pystray.MenuItem("Iniciar com o Windows", toggle_autostart, checked=lambda _i: autostart.is_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair do agente", quit_agent),
    )
    title = f"J.A.R.V.I.S — {settings.GLOBAL_HOTKEY or 'sem atalho'}"
    pystray.Icon("jarvis", _tray_image(), title, menu).run()
    log.info("Agente residente encerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
