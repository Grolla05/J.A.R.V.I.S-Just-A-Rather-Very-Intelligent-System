"""Iniciar com o Windows: valor `JARVIS` em HKCU\\...\\CurrentVersion\\Run.

O valor sobe o agente residente (agent.py) via pythonw — sem janela — no logon.
O instalador marca isso numa checkbox; /config e a bandeja ligam/desligam.
"""
import sys
from pathlib import Path

from .config import settings
from .logger import log

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "JARVIS"


def _winreg():
    try:
        import winreg
        return winreg
    except ImportError:  # pragma: no cover - só Windows
        return None


def pythonw_path():
    """pythonw.exe do runtime instalado ({app}\\runtime) ou ao lado do python atual."""
    installed = settings.DIR_ROOT.parent / "runtime" / "pythonw.exe"
    if settings.IS_INSTALLED and installed.exists():
        return installed
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def agent_script():
    return settings.DIR_BACKEND / "agent.py"


def agent_command():
    return f'"{pythonw_path()}" "{agent_script()}"'


def is_enabled():
    reg = _winreg()
    if reg is None:
        return False
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
            reg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def enable():
    reg = _winreg()
    if reg is None:
        return False
    try:
        with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
            reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, agent_command())
        log.info("🚀 J.A.R.V.I.S vai iniciar com o Windows.")
        return True
    except OSError as e:
        log.error(f"Falha ao ligar o início automático: {e}")
        return False


def disable():
    reg = _winreg()
    if reg is None:
        return False
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
            reg.DeleteValue(key, VALUE_NAME)
        log.info("J.A.R.V.I.S não inicia mais com o Windows.")
        return True
    except FileNotFoundError:
        return True
    except OSError as e:
        log.error(f"Falha ao desligar o início automático: {e}")
        return False


def set_enabled(on):
    return enable() if on else disable()


# ------------------------------------------------------- agente em 2º plano
AGENT_MUTEX = "Local\\JARVIS_AGENT"  # mesmo nome do agent.py
SYNCHRONIZE = 0x00100000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def is_agent_running():
    """O agente segura um mutex nomeado enquanto vive."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenMutexW(SYNCHRONIZE, False, AGENT_MUTEX)
    except (AttributeError, OSError):
        return False
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def start_agent():
    """Sobe o agente desacoplado desta TUI (sobrevive ao fechar o terminal)."""
    import subprocess
    try:
        subprocess.Popen([str(pythonw_path()), str(agent_script())], cwd=str(settings.DIR_BACKEND),
                         creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, close_fds=True)
        return True
    except OSError as e:
        log.error(f"Falha ao iniciar o agente: {e}")
        return False
