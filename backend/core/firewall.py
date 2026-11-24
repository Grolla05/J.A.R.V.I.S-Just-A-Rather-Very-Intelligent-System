"""Firewall do Windows (netsh advfirewall): bloquear/desbloquear IP e programa.

Só monta e roda comandos com **argv fixo** (lista, sem shell): o alvo é um IP
validado por `ipaddress` (nunca LAN, loopback ou reservado) ou o caminho do
executável que o psutil deu — nunca texto do LLM. Toda regra criada leva o
prefixo `RULE_PREFIX`, então `/rede bloqueios` e o desbloqueio só mexem nas
regras do JARVIS. Precisa de administrador (`is_admin`); quem decide se pode
bloquear (confirmação, bloqueio automático) é o `services/net_guard`.
"""
import ipaddress
import ntpath
import subprocess

from .logger import log

RULE_PREFIX = "JARVIS bloqueio"
RUN_TIMEOUT_S = 10
_DIRECTIONS = (("in", "entrada"), ("out", "saida"))


def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def validate_ip(ip):
    """IP público normalizado, ou ValueError com a frase para o usuário."""
    text = (ip or "").strip()
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        raise ValueError(f"`{text}` não é um endereço IP válido, Senhor.") from None
    if not addr.is_global or addr.is_multicast:
        raise ValueError(f"{text} é um endereço local ou reservado. Não bloqueio a sua própria rede, Senhor.")
    return str(addr)


def ip_rule_names(ip):
    return [f"{RULE_PREFIX} {ip} ({label})" for _, label in _DIRECTIONS]


def block_ip_commands(ip):
    """Duas regras (entrada e saída) para um IP já validado."""
    return [["netsh", "advfirewall", "firewall", "add", "rule", f"name={RULE_PREFIX} {ip} ({label})",
             f"dir={direction}", "action=block", f"remoteip={ip}"]
            for direction, label in _DIRECTIONS]


def program_rule_name(exe):
    return f"{RULE_PREFIX} programa {ntpath.basename(exe)}"


def block_program_inbound_command(exe):
    """Entrada bloqueada para um executável (processo suspeito com porta exposta)."""
    if not exe or not ntpath.isabs(exe) or not exe.lower().endswith(".exe") or '"' in exe:
        raise ValueError("caminho de executável inválido")
    return ["netsh", "advfirewall", "firewall", "add", "rule", f"name={program_rule_name(exe)}",
            "dir=in", "action=block", f"program={exe}", "enable=yes"]


def delete_rule_command(name):
    if not name.startswith(RULE_PREFIX):
        raise ValueError("só apago regras do JARVIS")
    return ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"]


def run_commands(commands, run=subprocess.run):
    """Roda cada comando; devolve (ok, erro). Para no primeiro que falhar."""
    for command in commands:
        try:
            result = run(command, capture_output=True, text=True, errors="ignore", timeout=RUN_TIMEOUT_S,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            log.warning(f"[FIREWALL] {command[3:5]} falhou: {e}")
            return False, str(e)
        if result.returncode != 0:
            return False, (result.stdout or result.stderr or "").strip()[:160]
    return True, ""


def shown(command):
    """Comando para o usuário colar num terminal de administrador."""
    return " ".join(f'"{part}"' if " " in part else part for part in command)
