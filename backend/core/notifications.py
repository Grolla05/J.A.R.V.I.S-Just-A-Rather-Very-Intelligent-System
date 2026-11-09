"""Notificações (toasts) do Windows: liga/desliga para todos os apps.

Usado pelo Não Perturbe (`services/focus.py`) e pela cena "estudo" do
WORK_MACRO. Mexe só em HKCU (sem admin): o valor
`NOC_GLOBAL_SETTING_TOASTS_ENABLED` é o mesmo interruptor de "Notificações" das
Configurações do Windows. Fora do Windows (ou sem winreg) tudo vira no-op.
"""
from .logger import log

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
_VALUE = "NOC_GLOBAL_SETTING_TOASTS_ENABLED"


def _winreg():
    try:
        import winreg
        return winreg
    except ImportError:  # pragma: no cover - só Windows tem winreg
        return None


def get_toasts_enabled():
    """True/False conforme o registro; ausente = True (padrão do Windows); None sem winreg."""
    reg = _winreg()
    if reg is None:
        return None
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, _KEY) as key:
            value, _type = reg.QueryValueEx(key, _VALUE)
            return bool(value)
    except FileNotFoundError:
        return True
    except OSError as e:
        log.debug(f"Notificações: leitura do registro falhou: {e}")
        return None


def set_toasts_enabled(enabled):
    """Liga/desliga os toasts de todos os apps. Retorna True se gravou."""
    reg = _winreg()
    if reg is None:
        return False
    try:
        with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, _KEY, 0, reg.KEY_SET_VALUE) as key:
            reg.SetValueEx(key, _VALUE, 0, reg.REG_DWORD, 1 if enabled else 0)
        log.info(f"🔔 Notificações do sistema {'ativadas' if enabled else 'silenciadas'}.")
        return True
    except OSError as e:
        log.error(f"Erro ao alternar notificações: {e}")
        return False
