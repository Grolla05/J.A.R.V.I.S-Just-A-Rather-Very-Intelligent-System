import sys
from pathlib import Path

# A TUI vive em <raiz>/frontend: deixa o pacote `frontend` importável nos testes.
_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
