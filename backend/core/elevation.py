"""Firewall elevado sem elevar o JARVIS — tarefa agendada `\\JARVIS\\Firewall`.

O Firewall do Windows (bloquear IP/programa no Vigia de rede) exige um processo
elevado, mas a TUI elevada perde o arrastar arquivo do Explorer (UIPI) e dar
admin ao JARVIS inteiro (skills, modelo) é poder demais. Então só **uma tarefa**
roda como administrador:

- `\\JARVIS\\Firewall` — sem gatilho, "privilégios mais altos", criada **uma vez**
  com um UAC (instalador ou `/config` → SISTEMA). O próprio usuário a dispara
  sem UAC (`schtasks /Run`); ela roda `agent.py --firewall-queue`, que atende os
  pedidos de `core/firewall.py` (revalidados: só regras "JARVIS bloqueio") e sai.

TUI, agente e ponte continuam sem admin. Leve de propósito (só `config` e
`logger`): o agente importa.

    pythonw agent.py --elevation-install   (precisa estar elevado)
    pythonw agent.py --elevation-remove

Passa pelo agent.py porque ele prepara o ambiente (JARVIS_DATA_DIR no layout
instalado, pacote `core` leve) antes de importar qualquer coisa.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

if sys.stdout is None:  # pythonw (UAC do /config): o logger escreve no stdout
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from .config import settings  # noqa: E402
from .logger import log  # noqa: E402

FIREWALL_TASK = "\\JARVIS\\Firewall"
QUEUE_FLAG = "--firewall-queue"   # mesmo valor do agent.py
LEGACY_TASKS = ("\\JARVIS\\Agente", "\\JARVIS\\TUI")  # versão que elevava tudo (nunca publicada)
RUN_TIMEOUT_S = 15
TASK_TIME_LIMIT = "PT2M"  # a fila termina em segundos; o limite só evita processo preso
SW_HIDE = 0
CREATE_NO_WINDOW = 0x08000000


def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def current_user():
    user = os.environ.get("USERNAME", "")
    domain = os.environ.get("USERDOMAIN", "")
    return f"{domain}\\{user}" if domain and user else user


def task_xml(command, arguments, workdir, user, description):
    """XML do Agendador: sem gatilho (sob demanda), nível mais alto, só deste usuário."""
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Author>J.A.R.V.I.S</Author><Description>{escape(description)}</Description></RegistrationInfo>
  <Triggers />
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>Queue</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <ExecutionTimeLimit>{TASK_TIME_LIMIT}</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(command))}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(str(workdir))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _run(args, run=subprocess.run):
    try:
        result = run(args, capture_output=True, text=True, errors="ignore", timeout=RUN_TIMEOUT_S,
                     creationflags=CREATE_NO_WINDOW)
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except Exception as e:
        return 1, str(e)


def task_exists(name=FIREWALL_TASK, run=subprocess.run):
    code, out = _run(["schtasks", "/Query", "/TN", name], run)
    return code == 0 and bool(out.strip())


def is_installed(run=subprocess.run):
    return task_exists(FIREWALL_TASK, run)


def run_task(name=FIREWALL_TASK, run=subprocess.run):
    return _run(["schtasks", "/Run", "/TN", name], run)[0] == 0


def _create(name, xml, run=subprocess.run):
    fd, path = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    try:
        Path(path).write_text(xml, encoding="utf-16")
        code, out = _run(["schtasks", "/Create", "/TN", name, "/XML", path, "/F"], run)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if code != 0:
        raise RuntimeError(f"schtasks recusou {name}: {out.strip()[:160]}")


def install(run=subprocess.run, user=None):
    """Cria a tarefa do firewall (precisa estar elevado). Levanta RuntimeError se o Agendador recusar."""
    from . import autostart
    _create(FIREWALL_TASK, task_xml(autostart.pythonw_path(), f'"{autostart.agent_script()}" {QUEUE_FLAG}',
                                    settings.DIR_BACKEND, user or current_user(),
                                    "Firewall do J.A.R.V.I.S: aplica só regras \"JARVIS bloqueio\" pedidas "
                                    "pelo Vigia de rede."), run)
    log.info("[ADMIN] Tarefa elevada do firewall criada.")
    return "Firewall do JARVIS ligado (tarefa elevada; o resto do JARVIS segue sem admin)."


def remove(run=subprocess.run):
    for name in (FIREWALL_TASK, *LEGACY_TASKS):
        _run(["schtasks", "/Delete", "/TN", name, "/F"], run)
    log.info("[ADMIN] Tarefa elevada do firewall removida.")
    return "Firewall do JARVIS desligado."


def request(action):
    """Pede o UAC (uma vez) para criar/apagar a tarefa. True se o Windows aceitou abrir."""
    if action not in ("install", "remove"):
        raise ValueError(action)
    from . import autostart
    try:
        import ctypes
        code = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(autostart.pythonw_path()),
                                                   f'"{autostart.agent_script()}" --elevation-{action}',
                                                   str(settings.DIR_BACKEND), SW_HIDE)
    except Exception as e:
        log.warning(f"[ADMIN] UAC indisponível: {e}")
        return False
    return code > 32


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not is_admin():
        log.error("[ADMIN] precisa rodar elevado.")
        return 1
    try:
        if "--remove" in argv:
            remove()
        elif "--install" in argv:
            install()
        elif "--queue" in argv:
            from . import firewall
            firewall.process_queue()
        else:
            log.error("Uso: agent.py --elevation-install | --elevation-remove | --firewall-queue")
            return 2
    except RuntimeError as e:
        log.error(f"[ADMIN] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
