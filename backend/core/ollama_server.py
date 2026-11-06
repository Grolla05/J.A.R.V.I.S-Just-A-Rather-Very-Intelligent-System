"""Garante que o servidor Ollama esteja no ar antes do JARVIS carregar.

`ensure_ollama_running()` roda no início do `main.py`, antes da TUI:
1. Sonda `GET {OLLAMA_HOST}/api/version` (timeout curto, sem proxy).
2. No ar → segue. Fora do ar e host local → `ollama serve` em segundo plano
   (processo desacoplado: sobrevive ao fechamento do JARVIS, como o app oficial).
3. Espera a API responder por até `OLLAMA_START_TIMEOUT` segundos.

Nunca derruba o boot: se o Ollama não estiver instalado ou não subir, registra
o motivo e o JARVIS segue (a etapa "core.llm / Ollama" da tela de boot avisa).
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .config import settings
from .logger import log

DEFAULT_HOST = "http://localhost:11434"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}

# Opener sem proxy: um HTTP_PROXY do sistema não pode interceptar o localhost.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _base_url(host=None):
    host = (host or settings.OLLAMA_HOST or DEFAULT_HOST).strip().rstrip("/")
    if not host.startswith("http"):
        host = f"http://{host}"
    return host


def is_local_host(host=None):
    """True se o OLLAMA_HOST aponta para esta máquina (só aí faz sentido subir o servidor)."""
    return (urlparse(_base_url(host)).hostname or "") in _LOCAL_HOSTS


def is_ollama_running(host=None, timeout=2.0):
    """Sonda a API do Ollama. Qualquer resposta HTTP 200 = servidor no ar."""
    try:
        with _opener.open(f"{_base_url(host)}/api/version", timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def find_ollama_executable():
    """Caminho do `ollama` no PATH ou na pasta padrão do instalador do Windows."""
    found = shutil.which("ollama")
    if found:
        return found
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def start_ollama_server(executable):
    """Dispara `ollama serve` desacoplado do terminal do JARVIS.

    Sem janela, em outro grupo de processo (o Ctrl+C da TUI não o derruba) e com a
    saída descartada (nada pode escrever no stdout da TUI). Repassa o OLLAMA_HOST
    para o servidor escutar no mesmo endereço que o cliente vai procurar.
    """
    env = os.environ.copy()
    if settings.OLLAMA_HOST:
        env["OLLAMA_HOST"] = settings.OLLAMA_HOST
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        [executable, "serve"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        env=env,
        **kwargs,
    )


def wait_until_ready(timeout, interval=0.5, process=None, host=None):
    """Espera a API responder. Para antes se o processo iniciado morrer."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_ollama_running(host):
            return True
        if process is not None and process.poll() is not None:
            # O `serve` saiu: pode ser outro Ollama (ex: app da bandeja) subindo
            # na mesma porta. Uma última sonda decide.
            return is_ollama_running(host)
        time.sleep(interval)
    return is_ollama_running(host)


def ensure_ollama_running(timeout=None):
    """Garante o Ollama no ar. Retorna (status, detalhe):
    "running" (já estava), "started" (subiu agora) ou "failed".
    """
    host = _base_url()
    if is_ollama_running(host):
        log.info(f"✅ Ollama online em {host}")
        return "running", f"já estava online em {host}"

    if not settings.OLLAMA_AUTOSTART:
        log.warning(f"⚠️ Ollama offline em {host} e OLLAMA_AUTOSTART=False")
        return "failed", "offline · autostart desligado"

    if not is_local_host(host):
        log.warning(f"⚠️ Ollama remoto offline em {host} — não dá para subir daqui")
        return "failed", f"host remoto {host} offline"

    executable = find_ollama_executable()
    if not executable:
        log.error("❌ Ollama offline e executável não encontrado. Instale em https://ollama.com")
        return "failed", "ollama não instalado"

    log.info(f"🚀 Ollama offline — iniciando servidor ({executable} serve)...")
    try:
        process = start_ollama_server(executable)
    except OSError as e:
        log.error(f"❌ Falha ao executar 'ollama serve': {e}")
        return "failed", f"falha ao iniciar ({type(e).__name__})"

    timeout = settings.OLLAMA_START_TIMEOUT if timeout is None else timeout
    start = time.monotonic()
    if wait_until_ready(timeout, process=process, host=host):
        elapsed = time.monotonic() - start
        log.info(f"✅ Servidor Ollama iniciado em {elapsed:.1f}s")
        return "started", f"iniciado em {elapsed:.1f}s"

    log.error(f"❌ Ollama não respondeu em {timeout}s após 'ollama serve'")
    return "failed", f"sem resposta em {timeout}s"
