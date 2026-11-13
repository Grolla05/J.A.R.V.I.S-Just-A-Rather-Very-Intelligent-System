import faulthandler
import os
import sys

from core import log, settings


def _enable_crash_log():
    """Crash nativo (0xC0000005 em PortAudio, CUDA...) não passa pelo logger:
    o faulthandler grava o stack de todas as threads em logs/crash.log."""
    try:
        settings.DIR_LOGS.mkdir(parents=True, exist_ok=True)
        # Fica aberto até o fim do processo (o faulthandler escreve nele no crash).
        crash_file = open(settings.DIR_LOGS / "crash.log", "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(file=crash_file, all_threads=True)
        return crash_file
    except OSError as e:
        log.warning(f"crash.log indisponível: {e}")
        return None


def start_jarvis():
    settings.perform_sanity_check()
    _enable_crash_log()
    # Perfil do Windows Terminal com a logo do JARVIS (vale na próxima aba aberta).
    from core.wt_profile import ensure_profile
    ensure_profile()
    log.info(f"Inicializando {settings.PROJECT_NAME} v{settings.VERSION} (TUI)")

    # Antes de carregar a TUI: Ollama no ar (sobe `ollama serve` se estiver offline).
    from core.ollama_server import ensure_ollama_running
    ensure_ollama_running()

    # A TUI mora em <raiz>/frontend (pacote `frontend`), separada do backend.
    if str(settings.DIR_ROOT) not in sys.path:
        sys.path.insert(0, str(settings.DIR_ROOT))

    try:
        from core.boot import run_boot
        from frontend.app import JarvisApp
    except ImportError as e:
        log.critical(f"Falha na importação dos módulos de serviço: {e}")
        sys.exit(1)

    # A tela de boot roda as checagens (config, banco, skills, Obsidian, mic) e
    # dispara em threads daemon o warm-up do Ollama e o scan de hardware (WMI),
    # que escondem a latência do 1º comando sem travar o boot.
    # --copilot: aberto pelo agente residente (Win+J / bandeja) já direto no
    # modo voz e sem a tela de boot (as checagens rodam em segundo plano).
    from_agent = "--copilot" in sys.argv[1:]
    start_mode = "copilot" if from_agent else None
    update_fn, install_fn = _update_hooks(sys.argv[1:])
    JarvisApp(boot_fn=run_boot, start_mode=start_mode, quiet_boot=from_agent,
              update_fn=update_fn, install_fn=install_fn).run()


def _update_hooks(args):
    """Tela "ATUALIZAÇÃO DISPONÍVEL!!": (update_fn, install_fn) do JarvisApp.
    `--update-preview 9.9.9` força a tela sem rede e sem instalar (dev)."""
    from core import updater
    if "--update-preview" in args:
        i = args.index("--update-preview")
        latest = args[i + 1] if i + 1 < len(args) else "9.9.9"
        return (lambda: {"version": latest, "current": settings.VERSION}), None
    return updater.check_available, updater.request_install


if __name__ == '__main__':
    try:
        start_jarvis()
    except KeyboardInterrupt:
        log.info("Aplicação finalizada pelo usuário.")
    # Mata threads presas em I/O bloqueante (microfone, monitor) imediatamente.
    os._exit(0)
