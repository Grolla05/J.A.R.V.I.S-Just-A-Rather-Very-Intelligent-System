"""Contatos de e-mail: "Guilherme" → endereço.

Ordem: endereço digitado → apelido salvo (tabela `email_contacts`) → pessoas com esse
nome nas mensagens do Gmail (`gmail.find_contacts`). Mais de um candidato = pergunta;
o apelido só é salvo depois de um envio confirmado (`email_compose`) ou por
`/email contato <apelido> <endereço>`.
"""
import re
import sqlite3
import unicodedata

from core import gmail
from core.database import db
from core.logger import log

FOUND, MANY, NONE = "found", "many", "none"
_ARTICLES = {"o", "a", "os", "as", "pro", "pra", "para", "ao", "do", "da", "sr", "sra", "senhor", "senhora"}


def _key(alias):
    text = unicodedata.normalize("NFKD", (alias or "").lower())
    words = re.findall(r"\w+", "".join(c for c in text if not unicodedata.combining(c)))
    return " ".join(w for w in words if w not in _ARTICLES)


def remember(alias, address):
    key, address = _key(alias), (address or "").strip().lower()
    if not key or not gmail.valid_address(address):
        return False
    try:
        with db.connection() as conn:
            conn.execute("INSERT INTO email_contacts (alias, address) VALUES (?, ?) "
                         "ON CONFLICT(alias) DO UPDATE SET address = excluded.address, last_used = CURRENT_TIMESTAMP",
                         (key, address))
        return True
    except sqlite3.Error as e:
        log.error(f"[EMAIL] Falha ao salvar contato: {e}")
        return False


def _saved(alias):
    try:
        with db.connection() as conn:
            row = conn.execute("SELECT address FROM email_contacts WHERE alias = ?", (_key(alias),)).fetchone()
    except sqlite3.Error as e:
        log.error(f"[EMAIL] Falha ao ler contatos: {e}")
        return None
    return row[0] if row else None


def resolve(name, finder=None):
    """(FOUND, endereço) | (MANY, [candidatos]) | (NONE, None)."""
    name = (name or "").strip()
    if not name:
        return NONE, None
    if gmail.valid_address(name):
        return FOUND, name.lower()
    saved = _saved(name)
    if saved:
        return FOUND, saved
    try:
        cands = (finder or gmail.find_contacts)(_key(name) or name)
    except Exception as e:
        log.debug(f"[EMAIL] Busca de contato falhou: {e}")
        return NONE, None
    if not cands:
        return NONE, None
    if len(cands) == 1:
        return FOUND, cands[0]["address"]
    return MANY, cands


def ask_text(name, cands):
    lines = [f"Encontrei mais de um **{name}**, Senhor. Repita o pedido com o endereço certo:", ""]
    lines += [f"{i}. {c['name']} · `{c['address']}`" for i, c in enumerate(cands, 1)]
    lines += ["", f"Dica: `/email contato {name.split()[0]} <endereço>` grava o apelido."]
    return "\n".join(lines)
