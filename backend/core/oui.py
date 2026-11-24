"""Fabricante do aparelho pelo MAC — base OUI offline (`core/data/oui.tsv.gz`).

Nada sai do PC: a lista da IEEE vai junto com o código (gerada por
`tools/update_oui.py`) e carrega só no primeiro uso. MAC com o bit
"administrado localmente" (0x02 no 1º byte) é **privado/aleatório** — o que
celulares e notebooks usam por rede Wi-Fi —, então não tem fabricante.
"""
import gzip
import re
import threading
from pathlib import Path

from .logger import log

DATA_FILE = Path(__file__).resolve().parent / "data" / "oui.tsv.gz"
_table = None
_lock = threading.Lock()

# Sufixos jurídicos/genéricos que só alongam o nome ("Samsung Electronics Co.,Ltd" → "Samsung Electronics")
_SUFFIX_RE = re.compile(
    r"[\s,.]*\b(co\.?,?\s*ltd\.?|company|limited|ltd\.?|inc\.?|incorporated|corp\.?|corporation|corporate|"
    r"gmbh|s\.?a\.?|s\.?r\.?l\.?|llc|l\.?l\.?c\.?|ag|plc|b\.?v\.?|pte\.?|oy|ab|kg|co\.?)\s*$",
    re.I,
)


def normalize(mac):
    """'AA:bb-CC.dd...' → 'AABBCCDDEEFF' ('' se não tem 12 dígitos hex)."""
    digits = re.sub(r"[^0-9a-fA-F]", "", str(mac or "")).upper()
    return digits if len(digits) == 12 else ""


def is_private(mac):
    """MAC administrado localmente (aleatório/privado): bit 0x02 do 1º byte."""
    digits = normalize(mac)
    return bool(digits) and bool(int(digits[:2], 16) & 0x02)


def short_name(name):
    name = " ".join(str(name or "").split())
    for _ in range(3):  # "Foo Technologies Co., Ltd." tem dois sufixos
        cleaned = _SUFFIX_RE.sub("", name).strip(" ,.")
        if cleaned == name or not cleaned:
            break
        name = cleaned
    return name


def _load(path=None):
    table = {}
    try:
        with gzip.open(path or DATA_FILE, "rt", encoding="utf-8") as fh:
            for line in fh:
                prefix, _, name = line.rstrip("\n").partition("\t")
                if prefix and name:
                    table[prefix] = name
    except OSError as e:
        log.warning(f"[REDE] Base de fabricantes indisponível: {e}")
    return table


def _get_table():
    global _table
    if _table is None:
        with _lock:
            if _table is None:
                _table = _load()
    return _table


def vendor(mac, table=None):
    """Fabricante (nome curto) ou None (desconhecido, privado ou MAC inválido)."""
    digits = normalize(mac)
    if not digits or is_private(digits):
        return None
    name = (table if table is not None else _get_table()).get(digits[:6])
    return short_name(name) if name else None
