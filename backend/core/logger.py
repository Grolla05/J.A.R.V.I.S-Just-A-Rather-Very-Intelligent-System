import logging
import sys

from colorama import Fore, Style, init

from .config import settings

init(autoreset=True)

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

    def debug(self, msg):
        if settings.DEBUG: self.logger.debug(f"{Fore.CYAN}[DEBUG]{Style.RESET_ALL} {msg}")

    def info(self, msg): 
        self.logger.info(f"{Fore.GREEN}[INFO]{Style.RESET_ALL} {msg}")

    def warning(self, msg): 
        self.logger.warning(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} {msg}")

    def error(self, msg): 
        self.logger.error(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {msg}")

    def critical(self, msg): 
        self.logger.critical(f"{Fore.RED}{Style.BRIGHT}[CRITICAL]{Style.RESET_ALL} {msg}")

log = JarvisLogger()