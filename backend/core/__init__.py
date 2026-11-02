import logging

from .bridge import JarvisAPI
from .config import settings
from .database import db
from .logger import log
from .obsidian import get_vault_context, mcp_client, obsidian
from .prompts import load_prompt
from .skill_loader import manager
from .SystemInfo import SystemInfo
from .utils import escape_js

# --- 1. Filtro de Poluição (Noise Reduction) ---
# Silencia bibliotecas que "falam demais" no console
LIBRARIES_TO_SILENCE = [
    "urllib3", 
    "asyncio", 
    "multipart", 
    "httpcore",
    "httpx" # Ollama usa muito isso
]

for lib in LIBRARIES_TO_SILENCE:
    logging.getLogger(lib).setLevel(logging.WARNING)

__all__ = ["settings", "log", "db", "obsidian", "mcp_client", "get_vault_context", "manager", "SystemInfo", "JarvisAPI", "load_prompt", "escape_js"]
