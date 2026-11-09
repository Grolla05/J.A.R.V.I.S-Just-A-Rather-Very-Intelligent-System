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
    # --copilot: aberto pelo agente residente (Win+J) já direto no modo voz.
    start_mode = "copilot" if "--copilot" in sys.argv[1:] else None
    JarvisApp(boot_fn=run_boot, start_mode=start_mode).run()


if __name__ == '__main__':
    try:
        start_jarvis()
    except KeyboardInterrupt:
        log.info("Aplicação finalizada pelo usuário.")
    # Mata threads presas em I/O bloqueante (microfone, monitor) imediatamente.
    os._exit(0)
