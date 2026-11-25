"""Firewall do Windows (netsh advfirewall): bloquear/desbloquear IP e programa.

Só monta e roda comandos com **argv fixo** (lista, sem shell): o alvo é um IP
validado por `ipaddress` (nunca LAN, loopback ou reservado) ou o caminho do
executável que o psutil deu — nunca texto do LLM. Toda regra criada leva o
prefixo `RULE_PREFIX`, então `/rede bloqueios` e o desbloqueio só mexem nas
regras do JARVIS. Quem decide se pode bloquear (confirmação, bloqueio
automático) é o `services/net_guard`.

**Só o firewall roda elevado** — a TUI e o agente não (TUI elevada perde o
arrastar arquivo do Explorer: UIPI do Windows). `run_commands` roda direto se o
processo já é admin; senão grava um pedido em `DIR_DATA/firewall/` e dispara a
tarefa `\\JARVIS\\Firewall` (`core/elevation.py`, criada com um UAC só; o próprio
usuário roda sem UAC). A tarefa (`agent.py --firewall-queue` → `process_queue`)
**revalida cada comando** contra os formatos acima (`is_allowed_command`): o
pedido é um arquivo do usuário, então nada fora deles roda elevado.
"""
import ipaddress
import json
import ntpath
import os
import subprocess
import time
import uuid

from .config import settings
from .logger import log

RULE_PREFIX = "JARVIS bloqueio"
RUN_TIMEOUT_S = 10
QUEUE_TIMEOUT_S = 20   # espera a tarefa elevada responder
QUEUE_POLL_S = 0.2
TASK_NAME = "\\JARVIS\\Firewall"  # mesmo valor de core/elevation.py
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


def is_allowed_command(command):
    """True só para os comandos que este módulo monta (o que a tarefa elevada aceita rodar)."""
    if not isinstance(command, list) or not all(isinstance(p, str) for p in command):
        return False
    if command[:4] != ["netsh", "advfirewall", "firewall", "add"] and \
            command[:4] != ["netsh", "advfirewall", "firewall", "delete"]:
        return False
    try:
        if command[3] == "delete":
            return len(command) == 6 and command[4] == "rule" and command[5].startswith("name=") \
                and command == delete_rule_command(command[5][5:])
        if len(command) == 9 and command[6].startswith("dir=") and command[8].startswith("remoteip="):
            return command in block_ip_commands(validate_ip(command[8][9:]))
        if len(command) == 10 and command[8].startswith("program="):
            return command == block_program_inbound_command(command[8][8:])
    except ValueError:
        return False
    return False


def available(admin=None, task_exists=None):
    """Dá para mexer no firewall? Já admin, ou com a tarefa elevada criada."""
    if (admin or is_admin)():
        return True
    if task_exists is None:
        from . import elevation
        return elevation.is_installed()
    return task_exists()


def _queue_dir():
    return settings.DIR_DATA / "firewall"


def _run_direct(commands, run):
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


def run_commands(commands, run=None):
    """(ok, erro). `run` injetado (testes) ou processo já admin → direto; senão, pela tarefa elevada."""
    if any(not is_allowed_command(c) for c in commands):
        return False, "comando fora do formato do JARVIS"
    if run is not None or is_admin():
        return _run_direct(commands, run or subprocess.run)
    return run_via_task(commands)


def run_via_task(commands, trigger=None, timeout=QUEUE_TIMEOUT_S, sleep=time.sleep, now=time.monotonic):
    """Grava o pedido, dispara `\\JARVIS\\Firewall` e espera a resposta (ok, erro)."""
    folder = _queue_dir()
    folder.mkdir(parents=True, exist_ok=True)
    rid = uuid.uuid4().hex
    request, result = folder / f"req-{rid}.json", folder / f"res-{rid}.json"
    request.write_text(json.dumps({"commands": commands}), encoding="utf-8")
    if trigger is None:
        from . import elevation
        trigger = lambda: elevation.run_task(TASK_NAME)  # noqa: E731
    if not trigger():
        _remove(request)
        return False, "a tarefa elevada do firewall não existe ou não abriu (ligue no /config → SISTEMA)"
    end = now() + timeout
    while now() < end:
        if result.exists():
            try:
                data = json.loads(result.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                sleep(QUEUE_POLL_S)
                continue
            _remove(result)
            return bool(data.get("ok")), str(data.get("error", ""))[:160]
        sleep(QUEUE_POLL_S)
    _remove(request)
    return False, "a tarefa elevada do firewall não respondeu a tempo"


def _remove(path):
    try:
        path.unlink()
    except OSError:
        pass


def process_queue(run=subprocess.run, folder=None):
    """Roda na tarefa elevada: atende cada pedido pendente. Comando fora do formato é recusado
    sem rodar nada daquele pedido. A resposta é criada com O_EXCL (não segue arquivo pré-plantado)."""
    folder = folder or _queue_dir()
    handled = 0
    for request in sorted(folder.glob("req-*.json")) if folder.is_dir() else ():
        rid = request.stem[4:]
        if not rid.isalnum():
            _remove(request)
            continue
        try:
            commands = json.loads(request.read_text(encoding="utf-8")).get("commands", [])
        except (OSError, ValueError, AttributeError):
            commands = None
        _remove(request)
        if not isinstance(commands, list) or not commands or not all(is_allowed_command(c) for c in commands):
            log.warning("[FIREWALL] Pedido recusado: comando fora do formato do JARVIS.")
            ok, error = False, "pedido recusado"
        else:
            ok, error = _run_direct(commands, run)
        result = folder / f"res-{rid}.json"
        _remove(result)
        try:
            fd = os.open(result, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"ok": ok, "error": error}, fh)
        except OSError as e:
            log.warning(f"[FIREWALL] Não gravei a resposta {rid}: {e}")
        handled += 1
    return handled


def shown(command):
    """Comando para o usuário colar num terminal de administrador."""
    return " ".join(f'"{part}"' if " " in part else part for part in command)
