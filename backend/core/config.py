import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 1. Definição de Caminhos Absolutos
# O arquivo atual é backend/core/config.py
# .parent = backend/core/
# .parent.parent = backend/
FILE_PATH = Path(__file__).resolve()
BACKEND_DIR = FILE_PATH.parent.parent
ROOT_DIR = BACKEND_DIR.parent  # A raiz do projeto (onde fica o .env)

# 2. Carregar variáveis de ambiente (.env)
env_path = ROOT_DIR / ".env"
load_dotenv(dotenv_path=env_path)

def _optional_int(name):
    """Lê inteiro opcional do .env. Ausente/inválido -> None (= não repassa ao Ollama)."""
    raw = os.getenv(name, "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else None


class Settings:
    # --- Informações do Projeto ---
    PROJECT_NAME: str = "J.A.R.V.I.S."
    VERSION: str = "1.0.0"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    DEBUG: bool = os.getenv("DEBUG_MODE", "False").lower() == "true"

    # --- Caminhos de Diretórios (Essencial para não dar erro de file not found) ---
    DIR_ROOT = ROOT_DIR
    DIR_BACKEND = BACKEND_DIR
    DIR_LOGS = BACKEND_DIR / "logs"
    LOG_FILE_PATH = DIR_LOGS / "jarvis-"
    DIR_DATABASE = BACKEND_DIR / "database"
    DIR_SOUNDS = BACKEND_DIR / "assets" / "sounds"
    
    # --- Configurações de IA Local (Ollama) ---
    # Agora o modelo é controlado por aqui. Se mudar no .env, muda no cérebro todo.
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL")
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST")
    # keep_alive do modelo na VRAM. -1 = nunca descarrega (resposta sempre rápida,
    # mas ocupa VRAM enquanto o JARVIS roda). Aceita também duração ("30m").
    # Numérico vira int (a API trata "30m" como duração, mas "-1" precisa ser int).
    _KEEP_ALIVE_RAW = os.getenv("OLLAMA_KEEP_ALIVE", "-1")
    OLLAMA_KEEP_ALIVE = int(_KEEP_ALIVE_RAW) if _KEEP_ALIVE_RAW.lstrip("-").isdigit() else _KEEP_ALIVE_RAW
    # Opções do runner. None (padrão) = não repassa, o Ollama decide.
    # OLLAMA_NUM_CTX: janela de contexto; menor = KV cache menor = cabe mais na VRAM (ex: 4096).
    # OLLAMA_NUM_GPU: camadas na GPU; 99 = todas. Se o Ollama recusar (VRAM insuficiente),
    # o llm.py desativa esta opção e segue com o padrão do Ollama (ver core/llm.py).
    OLLAMA_NUM_CTX = _optional_int("OLLAMA_NUM_CTX")
    OLLAMA_NUM_GPU = _optional_int("OLLAMA_NUM_GPU")

    # --- Configurações de Visão (Ollama multimodal — upload de imagem no Chat) ---
    OLLAMA_VISION_MODEL: str = os.getenv("OLLAMA_VISION_MODEL", "moondream")
    # keep_alive curto — modelo de visão é usado esporadicamente, não deve
    # competir por VRAM com OLLAMA_MODEL (que fica residente via keep_alive=-1).
    OLLAMA_VISION_KEEP_ALIVE = os.getenv("OLLAMA_VISION_KEEP_ALIVE", "5m")
    TIMEOUT_VISION: int = int(os.getenv("TIMEOUT_VISION", "60"))  # 1ª carga na VRAM é lenta

    # --- Configurações de Transcrição (faster-whisper — upload de áudio no Chat) ---
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "auto")           # "cpu" | "cuda" | "auto"
    WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")  # int8 = leve p/ CPU
    TIMEOUT_TRANSCRIPTION: int = int(os.getenv("TIMEOUT_TRANSCRIPTION", "60"))

    # --- Uploads de Chat (imagem/áudio anexados pelo usuário) ---
    DIR_UPLOADS = BACKEND_DIR / "uploads"
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "15"))
    ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif"}
    ALLOWED_AUDIO_MIME = {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/webm", "audio/ogg"}

    # --- Configurações do Obsidian (Memória de Longo Prazo) ---
    OBSIDIAN_HOST: str = os.getenv("OBSIDIAN_HOST")
    OBSIDIAN_API_KEY: str = os.getenv("OBSIDIAN_API_KEY")

    # --- Configurações do Spotify (Web API — OAuth PKCE) ---
    # PKCE não usa client_secret: o único segredo em disco é o refresh token.
    SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
    # ATENÇÃO: o Spotify só aceita HTTP em loopback e exige o IP literal.
    # 'localhost' é REJEITADO no cadastro do app. Este valor precisa ser
    # idêntico, byte a byte, ao registrado em developer.spotify.com/dashboard.
    SPOTIFY_REDIRECT_URI: str = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
    SPOTIFY_MARKET: str = os.getenv("SPOTIFY_MARKET", "BR")
    SPOTIFY_SCOPES: str = (
        "user-read-playback-state "
        "user-modify-playback-state "
        "user-read-currently-playing "
        "playlist-read-private "
        "playlist-read-collaborative"
    )
    SPOTIFY_AUTH_TIMEOUT: int = 120   # s — janela para o usuário autorizar no navegador
    TIMEOUT_SPOTIFY: int = 8          # s — timeout de cada request à Web API

    # Adicionado: Timeouts Globais (Robustez de Rede)
    TIMEOUT_API: int = 10  # Segundos para esperar a IA responder
    TIMEOUT_VOICE: int = 5 # Segundos para esperar o reconhecimento de voz

    # --- Cache de Classificação de Intenção (LRU + TTL) ---
    # Repetir o mesmo comando em <TTL s serve do cache, sem nova ida ao Ollama.
    INTENT_CACHE_TTL: int = 30   # Segundos de validade de cada entrada
    INTENT_CACHE_SIZE: int = 64  # Máximo de entradas antes da evicção LRU

    # --- Telemetria Push (Backend -> UI por delta, sem polling) ---
    TELEMETRY_INTERVAL: float = 1.0   # Frequência de amostragem do loop (s)
    TELEMETRY_CPU_DELTA: float = 5.0  # Push se |ΔCPU%| > este valor
    TELEMETRY_RAM_DELTA: float = 2.0  # Push se |ΔRAM%| > este valor
    TELEMETRY_GPU_DELTA: float = 5.0  # Push se |ΔGPU load%| > este valor

    # --- Configurações de Áudio (Listen/Speak) ---
    DEFAULT_LANGUAGE: str = "pt-BR"
    SPEECH_RATE: int = int(os.getenv("SPEECH_RATE"))    # Velocidade da fala
    MIC_INDEX: int = int(os.getenv("MIC_INDEX")) # Índice do microfone padrão
    # Threshold de energia estático. >0 desliga o dynamic_energy_threshold (instável
    # com ruído de ventilador). 0 mantém o modo dinâmico automático.
    MIC_ENERGY_THRESHOLD: int = int(os.getenv("MIC_ENERGY_THRESHOLD", "300"))

    # --- Configurações do Banco de Dados ---
    DB_NAME: str = "jarvis_memory.db"
    DB_PATH = DIR_DATABASE / DB_NAME

    # Credenciais do Spotify. Fora do Git (.gitignore) — contém refresh token.
    SPOTIFY_TOKEN_PATH = DIR_DATABASE / "spotify_token.json"

    def get_current_log_path(self):
        """Retorna o caminho da pasta logs/ANO/MES e garante que ela exista."""
        from datetime import datetime
        now = datetime.now()
        
        # Cria o caminho logs/2025/12
        year_dir = self.DIR_LOGS / now.strftime("%Y")
        month_dir = year_dir / now.strftime("%m")
        
        # Cria as pastas automaticamente conforme a demanda
        month_dir.mkdir(parents=True, exist_ok=True)
        year_dir.mkdir(parents=True, exist_ok=True)
        return month_dir, year_dir

    def create_dirs(self):
        """Garante a infraestrutura básica (exceto logs dinâmicos)."""
        self.DIR_DATABASE.mkdir(parents=True, exist_ok=True)
        self.DIR_SOUNDS.mkdir(parents=True, exist_ok=True)
        self.DIR_LOGS.mkdir(parents=True, exist_ok=True)
        self.DIR_UPLOADS.mkdir(parents=True, exist_ok=True)

    def perform_sanity_check(self):
        from .logger import log
        """
        Verificação de Saúde do Sistema (Modo Local).
        """
        # Verifica se as pastas cruciais foram criadas
        if not self.DIR_BACKEND.exists():
            log.critical(f"❌ ERRO FATAL: Pasta backend não encontrada em {self.DIR_BACKEND}")
            sys.exit(1)

        # Aviso de Modo Debug
        if self.DEBUG:
            log.warning("⚠️  AVISO: Modo DEBUG ativado. O sistema será mais verboso.")

        # Aviso Informativo sobre o Modelo
        log.info(f"🧠 Modelo de IA definido: {self.OLLAMA_MODEL} (Local)")
        

# Instância única
settings = Settings()
settings.create_dirs()