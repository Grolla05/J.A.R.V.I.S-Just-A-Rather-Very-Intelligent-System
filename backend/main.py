import os
import sys
import threading

from core import log, settings


def start_jarvis():
    settings.perform_sanity_check()
    log.info(f"Inicializando {settings.PROJECT_NAME} v{settings.VERSION} (TUI)")

    # A TUI mora em <raiz>/frontend (pacote `frontend`), separada do backend.
    if str(settings.DIR_ROOT) not in sys.path:
        sys.path.insert(0, str(settings.DIR_ROOT))

    try:
        from core.hardware import scan_system_hardware
        from core.llm import warm_up_ollama
        from frontend.app import JarvisApp
    except ImportError as e:
        log.critical(f"Falha na importação dos módulos de serviço: {e}")
        sys.exit(1)

    # Warm-up do Ollama e scan de hardware (PowerShell WMI) em paralelo à TUI:
    # escondem a latência do 1º comando sem travar o boot.
    threading.Thread(target=warm_up_ollama, daemon=True).start()
    threading.Thread(target=scan_system_hardware, daemon=True).start()

    JarvisApp().run()


if __name__ == '__main__':
    try:
        start_jarvis()
    except KeyboardInterrupt:
        log.info("Aplicação finalizada pelo usuário.")
    # Mata threads presas em I/O bloqueante (microfone, monitor) imediatamente.
    os._exit(0)
