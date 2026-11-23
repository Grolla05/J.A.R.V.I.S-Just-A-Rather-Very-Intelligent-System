"""winget — busca, instalação e download de software pelo gerenciador oficial do Windows.

Sem `shell=True`: a lista de argumentos vai direto ao processo. O id do pacote é
validado (`valid_id`) antes de virar argumento. Quem chama confirma com o usuário
antes de `install`/`download` (`services/software.py`).
"""
import difflib
import re
import subprocess

from core.logger import log

SEARCH_TIMEOUT = 60
INSTALL_TIMEOUT = 1800
SOURCE = "winget"
_ID_RE = re.compile(r"^[A-Za-z0-9][\w.+\-]{1,127}$")
_ROW_RE = re.compile(r"^(?P<name>.+?)\s+(?P<id>[A-Za-z0-9][\w+\-]*(?:\.[\w+\-]+)+)\s+(?P<version>\S+)")


def valid_id(package_id):
    package_id = package_id or ""
    return bool(_ID_RE.match(package_id)) and "." in package_id


def _run(args, timeout):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="ignore",
                          timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def available(run=_run):
    try:
        return run(["winget", "--version"], 15).returncode == 0
    except Exception:
        return False


def parse_search(output):
    """Tabela do `winget search` → [{'name', 'id', 'version'}]. Funciona em pt-BR e en-US."""
    lines = [line.rstrip("\r") for line in (output or "").splitlines()]
    sep = next((i for i, line in enumerate(lines) if line.startswith("---")), None)
    if sep is None or sep == 0:
        return []
    header = lines[sep - 1]
    starts = [m.start() for m in re.finditer(r"\S+", header)]
    if len(starts) < 3:
        return []
    id_col, ver_col = starts[1], starts[2]
    end_col = starts[3] if len(starts) > 3 else None
    items = []
    for line in lines[sep + 1:]:
        if not line.strip():
            continue
        item = None
        aligned = (len(line) > ver_col and line[id_col - 1] == " " and line[ver_col - 1] == " "
                   and line[id_col] != " ")
        if aligned:
            name, pid = line[:id_col].strip(), line[id_col:ver_col].strip()
            version = (line[ver_col:end_col] if end_col else line[ver_col:]).strip().split(" ")[0]
            if valid_id(pid) and " " not in pid:
                item = {"name": name, "id": pid, "version": version}
        if item is None:   # nome transbordou a coluna: separa por regex
            match = _ROW_RE.match(line.strip())
            if match and valid_id(match["id"]):
                item = {"name": match["name"].strip(), "id": match["id"], "version": match["version"]}
        if item:
            items.append(item)
    return items


def search(query, limit=8, run=_run):
    try:
        result = run(["winget", "search", query, "--source", SOURCE, "--accept-source-agreements",
                      "--disable-interactivity"], SEARCH_TIMEOUT)
    except Exception as e:
        log.warning(f"[WINGET] Busca falhou: {e}")
        return []
    return parse_search(result.stdout)[:limit]


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def best_match(query, items):
    """Pacote certo para o pedido, ou None se nenhum bate com segurança."""
    q = _norm(query)
    if not q:
        return None
    for item in items:   # nome ou fim do id idêntico
        if q in (_norm(item["name"]), _norm(item["id"].split(".")[-1]), _norm(item["id"])):
            return item
    names = {_norm(i["name"]): i for i in items}
    close = difflib.get_close_matches(q, list(names), n=1, cutoff=0.75)
    return names[close[0]] if close else None


def _exec(args, timeout, run):
    try:
        result = run(args, timeout)
    except Exception as e:
        return False, str(e)
    out = (result.stdout or "").strip()
    return result.returncode == 0, out[-300:]


def install(package_id, run=_run):
    if not valid_id(package_id):
        return False, "id de pacote inválido"
    log.info(f"[WINGET] Instalando {package_id}.")
    return _exec(["winget", "install", "--id", package_id, "--exact", "--source", SOURCE, "--silent",
                  "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"],
                 INSTALL_TIMEOUT, run)


def download(package_id, dest, run=_run):
    if not valid_id(package_id):
        return False, "id de pacote inválido"
    log.info(f"[WINGET] Baixando instalador de {package_id}.")
    return _exec(["winget", "download", "--id", package_id, "--exact", "--source", SOURCE,
                  "--download-directory", str(dest), "--accept-package-agreements",
                  "--accept-source-agreements", "--disable-interactivity"], INSTALL_TIMEOUT, run)
