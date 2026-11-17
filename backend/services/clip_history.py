"""Histórico persistente do clipboard (tabela `clipboard_history` do SQLite).

Quem grava é o `ClipboardMonitor` (pref "Monitor de clipboard"), via `add`.
Recopiar o mesmo texto só sobe o item para o topo (digest único); ficam as
`MAX_ROWS` cópias mais recentes. O que tem cara de senha/token não é gravado
(`looks_secret`). O conteúdo nunca vai para o log — só tipo e tamanho.
"""
import hashlib
import re
import sqlite3

from core.database import db
from core.logger import log

MAX_ROWS = 200
MAX_CHARS = 20_000
KIND_LABELS = {"code": "código", "error": "erro", "english": "inglês", "url": "link", "text": "texto"}

_SECRET_PREFIXES = ("sk-", "ghp_", "gho_", "github_pat_", "xox", "AKIA", "AIza", "eyJ")


def _digest(text):
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()


def looks_secret(text):
    """Token único sem espaços com cara de senha/chave (não entra no histórico)."""
    text = (text or "").strip()
    if not (8 <= len(text) <= 128) or re.search(r"\s", text):
        return False
    if re.match(r"^https?://", text, re.I):
        return False
    if text.startswith(_SECRET_PREFIXES):
        return True
    classes = sum(bool(re.search(p, text)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    return classes >= 3


def add(kind, text):
    """Grava uma cópia; devolve False se foi descartada (vazia, segredo ou erro)."""
    text = (text or "").strip()[:MAX_CHARS]
    if not text or looks_secret(text):
        return False
    try:
        with db.connection() as conn:
            # REPLACE troca a linha de mesmo digest por uma nova (id maior): recopiar sobe ao topo.
            # A ordem é pelo id — CURRENT_TIMESTAMP tem resolução de 1 s e empata.
            conn.execute(
                "INSERT OR REPLACE INTO clipboard_history (kind, content, digest) VALUES (?, ?, ?)",
                (kind or "text", text, _digest(text)),
            )
            conn.execute(
                "DELETE FROM clipboard_history WHERE id NOT IN "
                "(SELECT id FROM clipboard_history ORDER BY id DESC LIMIT ?)",
                (MAX_ROWS,),
            )
        return True
    except sqlite3.Error as e:
        log.error(f"[CLIPBOARD] Falha ao gravar no histórico: {e}")
        return False


def _rows(where="", params=(), limit=20):
    try:
        with db.connection() as conn:
            rows = conn.execute(
                f"SELECT kind, content, copied_at FROM clipboard_history {where} "
                "ORDER BY id DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
    except sqlite3.Error as e:
        log.error(f"[CLIPBOARD] Falha ao ler o histórico: {e}")
        return []
    return [{"kind": k, "text": c, "copied_at": t} for k, c, t in rows]


def recent(limit=20):
    """Cópias mais recentes primeiro: [{'kind', 'text', 'copied_at' (UTC)}]."""
    return _rows(limit=limit)


def search(term, limit=20):
    term = (term or "").strip()
    if not term:
        return []
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return _rows("WHERE content LIKE ? ESCAPE '\\'", (f"%{escaped}%",), limit)


def get(n):
    """n-ésima cópia mais recente (1 = a última), ou None."""
    if n < 1:
        return None
    items = _rows(limit=n)
    return items[n - 1] if len(items) >= n else None


def clear():
    """Apaga tudo; devolve quantas cópias saíram."""
    try:
        with db.connection() as conn:
            return conn.execute("DELETE FROM clipboard_history").rowcount
    except sqlite3.Error as e:
        log.error(f"[CLIPBOARD] Falha ao limpar o histórico: {e}")
        return 0


def to_markdown(items, title):
    """Lista numerada para a conversa (o número vale em /clip usar <n>)."""
    from services import sessions
    lines = [f"**{title}**", ""]
    for i, item in enumerate(items, 1):
        preview = " ".join(item["text"].split())[:70].replace("`", "'")
        local = str(sessions.to_local(item["copied_at"]))  # 'YYYY-MM-DD HH:MM:SS' no fuso local
        when = f"{local[8:10]}/{local[5:7]} {local[11:16]}" if len(local) >= 16 else "?"
        lines.append(f"{i}. *{KIND_LABELS.get(item['kind'], item['kind'])}* · {when} · `{preview}`")
    return "\n".join(lines)
