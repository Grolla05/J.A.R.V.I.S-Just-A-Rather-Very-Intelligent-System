"""Softwares que o usuário manteve no Vigia de rede (tabela `net_trusted_apps` do SQLite).

Quando o usuário responde "Manter" a um alerta de processo (ou `/rede confiar <n>`),
o software entra aqui. O `net_guard` consulta esta tabela **antes** de chamar o
juiz: software mantido nunca mais vira alerta — nem depois de `/rede reset`, que
só apaga a linha de base.

Identidade = nome do processo (sem caixa) + caminho do executável. Se os dois
lados têm caminho, ele precisa bater: um `chrome.exe` em outra pasta não herda a
confiança do Chrome de verdade. Caminho desconhecido (AccessDenied) casa só pelo nome.
"""
import sqlite3

from core.database import db
from core.logger import log


def _norm(text):
    return (text or "").strip().lower()


def keep(name, exe, kind, reason="mantido"):
    """Grava (ou renova) o software. Devolve False se o nome é vazio ou o banco falhou."""
    name = (name or "").strip()
    if not name:
        return False
    try:
        with db.connection() as conn:
            conn.execute(
                "INSERT INTO net_trusted_apps (name, name_key, exe, exe_key, kind, reason) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(name_key, exe_key) DO UPDATE SET kind = excluded.kind, reason = excluded.reason, "
                "decided_at = CURRENT_TIMESTAMP",
                (name, _norm(name), (exe or "").strip(), _norm(exe), kind or "", reason or ""),
            )
        log.info(f"[REDE] Software mantido gravado: {name}.")
        return True
    except sqlite3.Error as e:
        log.error(f"[REDE] Falha ao gravar software mantido: {e}")
        return False


def is_trusted(name, exe):
    """True se o usuário já manteve este software (mesmo executável quando ambos são conhecidos)."""
    key = _norm(name)
    if not key:
        return False
    try:
        with db.connection() as conn:
            rows = conn.execute("SELECT exe_key FROM net_trusted_apps WHERE name_key = ?", (key,)).fetchall()
    except sqlite3.Error as e:
        log.error(f"[REDE] Falha ao ler softwares mantidos: {e}")
        return False
    current = _norm(exe)
    return any(not stored or not current or stored == current for (stored,) in rows)


def list_all():
    """Mais recente primeiro: [{'id', 'name', 'exe', 'kind', 'decided_at'}]."""
    try:
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, exe, kind, decided_at FROM net_trusted_apps ORDER BY decided_at DESC, id DESC"
            ).fetchall()
    except sqlite3.Error as e:
        log.error(f"[REDE] Falha ao listar softwares mantidos: {e}")
        return []
    return [{"id": i, "name": n, "exe": e, "kind": k, "decided_at": d} for i, n, e, k, d in rows]


def count():
    return len(list_all())


def forget(index):
    """/rede esquecer <n> — tira o software da lista (o próximo acesso volta a ser julgado)."""
    items = list_all()
    if not 1 <= index <= len(items):
        return f"Não há software {index} na lista, Senhor. `/rede mantidos` mostra os números."
    item = items[index - 1]
    try:
        with db.connection() as conn:
            conn.execute("DELETE FROM net_trusted_apps WHERE id = ?", (item["id"],))
    except sqlite3.Error as e:
        log.error(f"[REDE] Falha ao esquecer software: {e}")
        return f"Não consegui tirar {item['name']} da lista, Senhor."
    return f"{item['name']} saiu da lista de mantidos, Senhor. O próximo acesso dele volta a ser julgado."


def list_text():
    """/rede mantidos — lista numerada."""
    items = list_all()
    if not items:
        return ("Nenhum software mantido ainda, Senhor. Quando um alerta de rede aparecer, "
                "**Manter** grava o programa aqui.")
    lines = ["**Softwares mantidos** (`/rede esquecer <n>` tira da lista):", ""]
    for i, item in enumerate(items, 1):
        where = f" · `{item['exe']}`" if item["exe"] else ""
        lines.append(f"{i}. **{item['name']}**{where}")
    return "\n".join(lines)
