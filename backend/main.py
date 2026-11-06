import os
import sys

from core import log, settings


def start_jarvis():
    settings.perform_sanity_check()
    log.info(f"Inicializando {settings.PROJECT_NAME} v{settings.VERSION} (TUI)")

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
    JarvisApp(boot_fn=run_boot).run()


if __name__ == '__main__':
    try:
        start_jarvis()
    except KeyboardInterrupt:
        log.info("Aplicação finalizada pelo usuário.")
    # Mata threads presas em I/O bloqueante (microfone, monitor) imediatamente.
    os._exit(0)
