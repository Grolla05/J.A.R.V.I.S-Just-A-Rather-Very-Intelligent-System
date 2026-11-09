"""Abre a TUI numa janela nova do terminal (usado pelo agente residente).

Instalado: {app}\\jarvis.cmd --here (dentro de um Windows Terminal novo, ou de
um console novo sem o wt). Dev: python main.py na pasta backend/. `--copilot`
faz a TUI já subir no modo Copilot.
"""
import shutil
import subprocess
import sys
from pathlib import Path

from .config import settings
from .logger import log

WINDOW_TITLE = "JARVIS"
CREATE_NEW_CONSOLE = 0x00000010


def python_exe():
    """python.exe (com console) ao lado do interpretador atual — o agente roda em pythonw."""
    exe = Path(sys.executable)
    candidate = exe.with_name("python.exe")
    return candidate if candidate.exists() else exe


def tui_command(copilot=True, wt=None):
    """(argv, cwd) para abrir a TUI. `wt` = caminho do wt.exe ou None."""
    extra = ["--copilot"] if copilot else []
    launcher = settings.DIR_ROOT.parent / "jarvis.cmd"
    if settings.IS_INSTALLED and launcher.exists():
        inner = ["cmd.exe", "/c", str(launcher), "--here", *extra]
        cwd = launcher.parent
    else:
        inner = [str(python_exe()), "main.py", *extra]
        cwd = settings.DIR_BACKEND
    if wt:
        return [wt, "-w", "new", "--title", WINDOW_TITLE, "-d", str(cwd), *inner], cwd
    return inner, cwd


def launch_tui(copilot=True):
    """Abre a TUI. Retorna o Popen (ou None se falhou)."""
    wt = shutil.which("wt.exe") or shutil.which("wt")
    argv, cwd = tui_command(copilot, wt)
    try:
        flags = 0 if wt else CREATE_NEW_CONSOLE
        proc = subprocess.Popen(argv, cwd=str(cwd), creationflags=flags)
        log.info(f"🚀 TUI aberta pelo agente ({'Windows Terminal' if wt else 'console'}).")
        return proc
    except OSError as e:
        log.error(f"Falha ao abrir a TUI: {e}")
        return None
