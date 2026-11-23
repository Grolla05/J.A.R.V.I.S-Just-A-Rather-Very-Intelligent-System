"""Achar um arquivo do usuário pelo nome (ex.: anexar "proposta.txt" num e-mail).

Procura só nas pastas pessoais (Área de Trabalho, Documentos, Downloads e as do
OneDrive), com profundidade limitada, mais recente primeiro. Nunca devolve arquivo
sensível (.env, chaves, cofres de senha, .ssh, AppData) nem fora da pasta do
usuário — quem chama mostra caminho e tamanho na confirmação.
"""
import os
from pathlib import Path

FOUND, MANY, NONE, BLOCKED = "found", "many", "none", "blocked"
MAX_BYTES = 25 * 1024 * 1024        # limite de anexo do Gmail
MAX_DEPTH = 4
MAX_VISITED = 20_000
MAX_RESULTS = 5

_SENSITIVE_NAMES = {".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials.json", "token.json",
                    "known_hosts", "authorized_keys", ".netrc", ".git-credentials", ".npmrc", ".pypirc"}
_SENSITIVE_EXT = {".pem", ".key", ".pfx", ".p12", ".kdbx", ".kdb", ".ppk", ".asc", ".gpg", ".keystore", ".jks"}
_SENSITIVE_DIRS = {".ssh", ".gnupg", "appdata", ".aws", ".azure", ".kube", ".git", "node_modules"}


def _home():
    return Path(os.path.expanduser("~"))


def default_roots(home=None):
    home = Path(home or _home())
    roots = [home / "Desktop", home / "Documents", home / "Downloads"]
    for one in sorted(home.glob("OneDrive*")):
        roots += [one / "Desktop", one / "Documents", one / "Área de Trabalho", one / "Documentos"]
    return [r for r in roots if r.is_dir()]


def _is_sensitive(path):
    name = path.name.lower()
    if name in _SENSITIVE_NAMES or name.startswith(".env") or name.startswith("id_rsa"):
        return True
    if path.suffix.lower() in _SENSITIVE_EXT:
        return True
    return any(part.lower() in _SENSITIVE_DIRS for part in path.parts)


def check(path, home=None):
    """Motivo da recusa (texto) ou None se o arquivo pode ser anexado."""
    home = Path(home or _home()).resolve()
    try:
        resolved = Path(path).resolve()
    except OSError:
        return "não consegui ler esse caminho"
    try:
        rel = resolved.relative_to(home)
    except ValueError:
        return "fica fora da sua pasta de usuário"
    if _is_sensitive(rel):
        return "é um arquivo sensível (senhas, chaves ou configuração) — não envio por e-mail"
    if not resolved.is_file():
        return "não é um arquivo"
    if resolved.stat().st_size > MAX_BYTES:
        return f"passa de {human_size(MAX_BYTES)} (limite de anexo do Gmail)"
    return None


def human_size(size):
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB".replace(".", ",")
    return f"{size / 1024 / 1024:.1f} MB".replace(".", ",")


def size_text(path):
    try:
        return human_size(Path(path).stat().st_size)
    except OSError:
        return "?"


def _search(name, roots):
    target, hits, visited = name.lower(), [], 0
    for root in roots:
        root = Path(root)
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).parts) - base_depth
            dirnames[:] = [d for d in dirnames if d.lower() not in _SENSITIVE_DIRS and not d.startswith(".")
                           and depth < MAX_DEPTH]
            for f in filenames:
                visited += 1
                if f.lower() == target:
                    hits.append(Path(dirpath) / f)
            if visited > MAX_VISITED:
                break
    hits = list(dict.fromkeys(hits))
    return sorted(hits, key=lambda p: p.stat().st_mtime, reverse=True)[:MAX_RESULTS]


def find(query, home=None, roots=None):
    """(FOUND, Path) | (MANY, [Path]) | (NONE, None) | (BLOCKED, motivo)."""
    query = (query or "").strip().strip('"').strip("'")
    if not query:
        return NONE, None
    home = Path(home or _home())
    candidate = Path(os.path.expandvars(os.path.expanduser(query)))
    if candidate.is_absolute():
        if not candidate.exists():
            return NONE, None
        reason = check(candidate, home)
        return (BLOCKED, reason) if reason else (FOUND, candidate)
    if _is_sensitive(Path(query)):
        return BLOCKED, "é um arquivo sensível (senhas, chaves ou configuração) — não envio por e-mail"
    hits = [p for p in _search(Path(query).name, roots if roots is not None else default_roots(home))
            if check(p, home) is None]
    if not hits:
        return NONE, None
    return (FOUND, hits[0]) if len(hits) == 1 else (MANY, hits)
