"""Encerramento seguro de processos — usado pela skill APP_CONTROL e pelo vigia de rede.

Antes de encerrar, confere se o PID ainda é o mesmo processo (nome e hora de
criação): entre a pergunta e o "sim" o Windows pode reaproveitar o PID.
Também guarda a lista de processos que o JARVIS nunca encerra.
"""
import os

from .logger import log

# Nunca encerrados pelo JARVIS (nome sem .exe, minúsculo): o sistema, o shell e o
# próprio runtime/terminal do JARVIS.
PROTECTED = frozenset({
    "system", "system idle process", "idle", "registry", "smss", "csrss", "wininit", "winlogon",
    "services", "lsass", "svchost", "dwm", "explorer", "fontdrvhost", "sihost", "ctfmon",
    "conhost", "openconsole", "windowsterminal", "python", "pythonw", "ollama",
})


def stem(name):
    """'Chrome.EXE' -> 'chrome'."""
    name = (name or "").strip().lower()
    return name[:-4] if name.endswith(".exe") else name


def is_protected(name, pid=None):
    if pid is not None and pid in (os.getpid(), os.getppid()):
        return True
    return stem(name) in PROTECTED


def terminate_if_same(pid, name, created, psutil_mod=None):
    """Encerra o processo se ainda for o mesmo. Devolve 'ok' | 'changed' | 'protected' | 'error'."""
    try:
        psutil = psutil_mod
        if psutil is None:
            import psutil
        proc = psutil.Process(pid)
        if proc.name().lower() != (name or "").lower() or abs(float(proc.create_time()) - float(created)) > 1.0:
            return "changed"
        if is_protected(name, pid):
            return "protected"
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        return "ok"
    except Exception as e:
        log.warning(f"Não consegui encerrar {name} (PID {pid}): {e}")
        return "error"
