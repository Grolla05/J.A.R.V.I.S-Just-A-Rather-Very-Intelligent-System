"""Gera `core/data/oui.tsv.gz` — fabricante por prefixo de MAC (OUI), offline.

Ferramenta de desenvolvimento (não roda no JARVIS). Baixa a lista pública do
Wireshark (`manuf`, nomes curtos tipo "Samsung") e, se falhar, a da IEEE
(`oui.csv`, nome registrado completo). Só os blocos MA-L (6 dígitos hex)
entram: cobrem a imensa maioria dos aparelhos e o arquivo fica ~0,5 MB.

    cd backend
    python tools/update_oui.py

Rode de vez em quando (fabricantes novos) e commite o .gz.
"""
import csv
import gzip
import io
import re
import sys
from pathlib import Path

import requests

WIRESHARK_URL = "https://www.wireshark.org/download/automated/data/manuf"
IEEE_URL = "https://standards-oui.ieee.org/oui/oui.csv"
OUT = Path(__file__).resolve().parent.parent / "core" / "data" / "oui.tsv.gz"
TIMEOUT_S = 60
_HEX6 = re.compile(r"^[0-9A-F]{6}$")


def parse_manuf(text):
    """Formato do Wireshark: 'AA:BB:CC<TAB>Curto<TAB>Nome longo' (só prefixo de 24 bits)."""
    table = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        prefix = parts[0].replace(":", "").replace("-", "").upper()
        if "/" in prefix or not _HEX6.match(prefix) or len(parts) < 2:
            continue
        name = (parts[1] or (parts[2] if len(parts) > 2 else "")).strip()
        if name:
            table[prefix] = name
    return table


def parse_ieee(text):
    """oui.csv da IEEE: Registry,Assignment,Organization Name,Organization Address."""
    table = {}
    for row in csv.DictReader(io.StringIO(text)):
        prefix = (row.get("Assignment") or "").strip().upper()
        name = (row.get("Organization Name") or "").strip()
        if _HEX6.match(prefix) and name:
            table[prefix] = name
    return table


def fetch():
    headers = {"User-Agent": "Mozilla/5.0 (oui-updater)"}
    for url, parser in ((WIRESHARK_URL, parse_manuf), (IEEE_URL, parse_ieee)):
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT_S)
            resp.raise_for_status()
            table = parser(resp.text)
            if len(table) > 10_000:
                return table, url
        except requests.RequestException as e:
            sys.stderr.write(f"falhou {url}: {e}\n")
    raise SystemExit("Nenhuma fonte respondeu.")


def write(table, out=OUT):
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{k}\t{v}\n" for k, v in sorted(table.items()))
    with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as fh:
        fh.write(body)
    return out


if __name__ == "__main__":
    data, source = fetch()
    path = write(data)
    sys.stdout.write(f"{len(data)} fabricantes de {source} -> {path} ({path.stat().st_size // 1024} KB)\n")
