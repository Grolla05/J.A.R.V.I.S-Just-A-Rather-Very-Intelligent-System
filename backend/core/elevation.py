"""JARVIS sempre como administrador — sem UAC a cada abertura.

O Firewall do Windows (bloquear IP/programa no Vigia de rede) exige um processo
elevado. Em vez de rodar tudo pedindo UAC, criamos **uma vez** (um UAC só, pelo
instalador ou pelo `/config` → SISTEMA) duas tarefas agendadas com "executar com
privilégios mais altos":

- `\\JARVIS\\Agente` — no logon **deste usuário**, sobe o agente residente
  (`agent.py --logon`). A TUI e a ponte que ele abre herdam a elevação.
- `\\JARVIS\\TUI` — sob demanda; o `jarvis.cmd` não elevado a dispara
  (`schtasks /Run`) para abrir a TUI já elevada. Só no layout instalado.

Com a tarefa do agente, o valor `JARVIS` do `HKCU\\…\\Run` sai (senão subiriam
dois agentes, e o não elevado poderia ganhar o mutex). `core/autostart.py` passa
a ligar/desligar a tarefa. Remover devolve o valor do Run.

Trade-off: tudo que o JARVIS faz passa a ter poder de admin. Por isso o firewall
só roda com argv fixo (`core/firewall.py`) e ações destrutivas seguem pedindo
confirmação. Leve de propósito (só `config` e `logger`): o agente importa via
`core/autostart.py`.

    pythonw agent.py --elevation-install [--no-autostart]   (precisa estar elevado)
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

AGENT_TASK = "\\JARVIS\\Agente"
TUI_TASK = "\\JARVIS\\TUI"
RUN_TIMEOUT_S = 15
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


def task_xml(command, arguments, workdir, user, on_logon, description):
    """XML do Agendador: logon só de `user`, nível mais alto, sessão interativa, sem prazo
    (o padrão do Agendador mata a tarefa em 72 h — o agente vive o dia inteiro)."""
    trigger = (f"<Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{escape(user)}</UserId>"
               "</LogonTrigger></Triggers>") if on_logon else "<Triggers />"
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Author>J.A.R.V.I.S</Author><Description>{escape(description)}</Description></RegistrationInfo>
  {trigger}
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
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


def task_state(name, run=subprocess.run):
    """None (não existe) | True (habilitada) | False (desabilitada)."""
    code, out = _run(["schtasks", "/Query", "/TN", name, "/FO", "CSV", "/NH"], run)
    if code != 0 or not out.strip():
        return None
    low = out.lower()
    return not ("disabled" in low or "desabilitad" in low)


def set_task_enabled(name, enabled, run=subprocess.run):
    code, out = _run(["schtasks", "/Change", "/TN", name, "/ENABLE" if enabled else "/DISABLE"], run)
    if code != 0:
        log.warning(f"[ADMIN] Não consegui {'ligar' if enabled else 'desligar'} a tarefa {name}: {out.strip()[:120]}")
    return code == 0


def run_task(name, run=subprocess.run):
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


def _tui_launcher():
    launcher = settings.DIR_ROOT.parent / "jarvis.cmd"
    return launcher if (settings.DIR_ROOT.parent / "runtime").is_dir() and launcher.exists() else None


def is_installed(run=subprocess.run):
    return task_state(AGENT_TASK, run) is not None


def install(autostart=True, run=subprocess.run, user=None):
    """Cria as tarefas (precisa estar elevado). Devolve a frase do resultado; levanta RuntimeError."""
    from . import autostart as auto
    user = user or current_user()
    _create(AGENT_TASK, task_xml(auto.pythonw_path(), f'"{auto.agent_script()}" {auto.LOGON_FLAG}',
                                 settings.DIR_BACKEND, user, True,
                                 "Agente residente do J.A.R.V.I.S (elevado: firewall do Vigia de rede)."), run)
    launcher = _tui_launcher()
    if launcher:
        _create(TUI_TASK, task_xml(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"),
                                   f'/c "{launcher}"', launcher.parent, user, False,
                                   "Abre a TUI do J.A.R.V.I.S elevada (sem UAC)."), run)
    if not autostart:
        set_task_enabled(AGENT_TASK, False, run)
    auto.delete_run_value()  # a tarefa substitui o Run (senão sobem dois agentes)
    log.info("[ADMIN] Tarefas elevadas criadas.")
    return "JARVIS passa a rodar como administrador (tarefa agendada, sem UAC a cada abertura)."


def remove(run=subprocess.run):
    """Apaga as tarefas e devolve o início com o Windows ao valor do Run, se estava ligado."""
    from . import autostart as auto
    was_on = task_state(AGENT_TASK, run)
    for name in (AGENT_TASK, TUI_TASK):
        _run(["schtasks", "/Delete", "/TN", name, "/F"], run)
    if was_on:
        auto.write_run_value()
    log.info("[ADMIN] Tarefas elevadas removidas.")
    return "JARVIS volta a rodar sem administrador."


def restart_agent_elevated(run=subprocess.run):
    """Troca um agente não elevado pelo da tarefa (vale já, sem esperar o próximo logon)."""
    from . import autostart as auto
    script = str(auto.agent_script()).lower()
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            cmd = " ".join(proc.info.get("cmdline") or []).lower()
            if proc.pid != os.getpid() and script in cmd and "elevation" not in cmd:
                proc.terminate()
                proc.wait(timeout=5)
    except Exception as e:
        log.debug(f"[ADMIN] Não consegui fechar o agente antigo: {e}")
    return run_task(AGENT_TASK, run)


def request(action):
    """Pede o UAC (uma vez) para instalar/remover as tarefas. True se o Windows aceitou abrir."""
    if action not in ("install", "remove"):
        raise ValueError(action)
    from . import autostart as auto
    try:
        import ctypes
        code = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(auto.pythonw_path()),
                                                   f'"{auto.agent_script()}" --elevation-{action}',
                                                   str(settings.DIR_BACKEND), SW_HIDE)
    except Exception as e:
        log.warning(f"[ADMIN] UAC indisponível: {e}")
        return False
    return code > 32


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not is_admin():
        log.error("[ADMIN] core.elevation precisa rodar elevado.")
        return 1
    try:
        if "--remove" in argv:
            remove()
        elif "--install" in argv:
            install(autostart="--no-autostart" not in argv)
            if "--no-restart" not in argv and task_state(AGENT_TASK):
                restart_agent_elevated()
        else:
            log.error("Uso: agent.py --elevation-install [--no-autostart] | --elevation-remove")
            return 2
    except RuntimeError as e:
        log.error(f"[ADMIN] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
