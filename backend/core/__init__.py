"""Pacote `core`. Importar é leve: banco, skills e SystemInfo só carregam no
primeiro acesso (`from core import db` continua funcionando — PEP 562)."""
import importlib
import logging

from .config import settings
from .logger import log

# Leve (REST via requests). Fica direto para `core.obsidian` continuar sendo a
# instância ObsidianClient, e não o submódulo.
from .obsidian import get_vault_context, obsidian
from .prompts import load_prompt

# --- 1. Filtro de Poluição (Noise Reduction) ---
# Silencia bibliotecas que "falam demais" no console
LIBRARIES_TO_SILENCE = [
    "urllib3",
    "asyncio",
    "multipart",
    "httpcore",
    "httpx",  # Ollama usa muito isso
]

for lib in LIBRARIES_TO_SILENCE:
    logging.getLogger(lib).setLevel(logging.WARNING)

# Nome → (submódulo, atributo). Carregados só quando alguém pedir.
_LAZY = {
    "db": (".database", "db"),                  # abre/migra o SQLite
    "manager": (".skill_loader", "manager"),    # skills carregam no 1º uso de manager.skills
    "SystemInfo": (".SystemInfo", "SystemInfo"),
}


def __getattr__(name):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    value = getattr(importlib.import_module(module_name, __name__), attr)
    globals()[name] = value  # próximos acessos não passam mais por aqui
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))


__all__ = ["settings", "log", "db", "obsidian", "get_vault_context", "manager", "SystemInfo", "load_prompt"]
