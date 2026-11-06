import logging
import re
import sys
import threading
from collections import deque

from colorama import Fore, Style, init

from .config import settings

init(autoreset=True)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TAG = re.compile(r"^\[(DEBUG|INFO|WARN|ERROR|CRITICAL)\]\s*")


class RingBufferHandler(logging.Handler):
    """Guarda os últimos `capacity` registros em memória (tela /log da TUI).
    Cada item: {'time': 'HH:MM:SS', 'level': 'INFO', 'module': 'brain', 'message': '...'}."""

    def __init__(self, capacity=500):
        super().__init__(level=logging.DEBUG)
        self.records = deque(maxlen=capacity)
        self._lock_buf = threading.Lock()

    def emit(self, record):
        try:
            message = _TAG.sub("", _ANSI.sub("", record.getMessage()))
            level = "WARN" if record.levelname == "WARNING" else record.levelname
            from datetime import datetime
            item = {
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": level,
                "module": record.module,
                "message": message,
            }
            with self._lock_buf:
                self.records.append(item)
        except Exception:
            self.handleError(record)

    def snapshot(self):
        with self._lock_buf:
            return list(self.records)


class JarvisLogger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(JarvisLogger, cls).__new__(cls)
            cls._instance._setup_logger()
        return cls._instance

    def _setup_logger(self):
        self.logger = logging.getLogger("JARVIS_CORE")
        self.logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
        
        if self.logger.handlers:
            return

        # Buffer em memória p/ a tela de log da TUI (independe do console/arquivo)
        self.buffer = RingBufferHandler(500)
        self.logger.addHandler(self.buffer)

        # Configura o handler de console com UTF-8 e errors='replace'
        # para que emojis nunca causem UnicodeEncodeError no terminal Windows (cp1252)
        console_formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', datefmt='%H:%M:%S')
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.stream = open(
            sys.stdout.fileno(),
            mode='w',
            encoding='utf-8',
            errors='replace',
            closefd=False,
            buffering=1
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        self._console_handler = console_handler

        # No core/logger.py, dentro de _setup_logger:

        try:
            from datetime import datetime
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            
            # Gera o nome do arquivo com a data de HOJE para o início do sistema
            datestr = datetime.now().strftime("%Y-%m-%d")
            log_filename = settings.DIR_LOGS / f"jarvis_{datestr}.log"
            
            # Usamos o FileHandler simples para o arquivo do dia
            # A rotação pode ser tratada reiniciando o sistema ou via TimedRotating
            file_handler = logging.FileHandler(
                filename=str(log_filename),
                encoding='utf-8'
            )
            
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
            
        except Exception as e:
            # Usamos print aqui pois o logger pode não estar pronto
            log.critical(f"Erro ao configurar arquivo de log: {e}")

    def use_tui(self, ui_handler=None):
        """Desliga o console (stdout corromperia a tela da TUI) e, opcionalmente,
        pluga um handler que entrega os logs à interface. O arquivo de log segue."""
        if getattr(self, "_console_handler", None):
            self.logger.removeHandler(self._console_handler)
            self._console_handler = None
        if ui_handler is not None:
            self.logger.addHandler(ui_handler)

    def debug(self, msg):
        if settings.DEBUG: self.logger.debug(f"{Fore.CYAN}[DEBUG]{Style.RESET_ALL} {msg}", stacklevel=2)

    def info(self, msg): 
        self.logger.info(f"{Fore.GREEN}[INFO]{Style.RESET_ALL} {msg}", stacklevel=2)

    def warning(self, msg): 
        self.logger.warning(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} {msg}", stacklevel=2)

    def error(self, msg): 
        self.logger.error(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {msg}", stacklevel=2)

    def critical(self, msg): 
        self.logger.critical(f"{Fore.RED}{Style.BRIGHT}[CRITICAL]{Style.RESET_ALL} {msg}", stacklevel=2)

log = JarvisLogger()