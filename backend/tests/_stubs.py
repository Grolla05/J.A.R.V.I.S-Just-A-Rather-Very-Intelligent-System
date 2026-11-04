"""Stubs de dependências pesadas/não instaladas para permitir importar o pacote
`core` em ambiente de teste sem hardware (mic/GPU/WMI) nem servidor MCP.

Chame `install()` ANTES de qualquer `import core` ou `from core...`.
"""
import sys
from unittest.mock import MagicMock

# Roots não instalados no venv — substituídos por mocks para permitir importar
# o pacote `core` (e a cadeia obsidian/SystemInfo) sem hardware/rede.
_STUB_MODULES = (
    "mcp",
    "mcp.client",
    "mcp.client.stdio",
    "GPUtil",
    "wmi",
    "requests",   # core.obsidian
    "psutil",     # core.SystemInfo (só importado, não exercido nos testes)
    "ollama",     # core.llm (lazy: import dentro de _get_client)
)


def install():
    for name in _STUB_MODULES:
        sys.modules.setdefault(name, MagicMock())
