"""Sessões e histórico do chat de texto (SQLite).

Extraído da antiga JarvisAPI (bridge PyWebView) para ser consumido direto pela
TUI. Toda conexão fecha em `finally` — omitir o close() trava o banco.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.database import db
from core.logger import log

DEFAULT_TITLE = "Nova conversa"


def to_local(timestamp):
    """SQLite grava CURRENT_TIMESTAMP em UTC: 'YYYY-MM-DD HH:MM:SS' → mesmo
    formato no fuso local da máquina. Valor inválido volta como veio."""
    try:
        utc = datetime.strptime(str(timestamp)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return timestamp
    return utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def new_session_id():
    return f"chat_{uuid.uuid4().hex[:12]}"


def get_chat_history(session_id, limit=50):
    """Mensagens da sessão em ordem cronológica: dicts com
    id, role ('user'|'assistant'), content, time e attachment (nome ou None)."""
    conn = None
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, role, content, timestamp, attachment_type, attachment_path FROM history
            WHERE session_id = ?
            ORDER BY timestamp DESC, id DESC LIMIT ?
        ''', (session_id, limit))
        rows = cursor.fetchall()
    except Exception as e:
        log.error(f"Erro ao recuperar histórico da sessão '{session_id}': {e}")
        return []
    finally:
        if conn:
            conn.close()

    rows.reverse()
    messages = []
    for row_id, role, content, timestamp, attachment_type, attachment_path in rows:
        local = to_local(timestamp)
        time_part = local.split(' ')[1][:5] if local and ' ' in local else ""
        attachment = None
        if attachment_type and attachment_path:
            # Nome salvo é "<uuid>_<original>": mostra só o original
            attachment = Path(attachment_path).name.split("_", 1)[-1]
        messages.append({
            "id": row_id,
            "role": "user" if role == "user" else "assistant",
            "content": content or "",
            "time": time_part,
            "attachment": attachment,
        })
    return messages


def delete_history_from(session_id, message_id):
    """Apaga a mensagem `message_id` e tudo depois dela (editar/regenerar)."""
    try:
        db.delete_history_from(session_id, message_id)
        return True
    except Exception as e:
        log.error(f"Erro ao apagar histórico da sessão '{session_id}' a partir de '{message_id}': {e}")
        return False


def _first_prompt(cursor, session_id):
    cursor.execute('''
        SELECT content FROM history
        WHERE session_id = ? AND role = 'user'
        ORDER BY id ASC LIMIT 1
    ''', (session_id,))
    row = cursor.fetchone()
    return row[0] if row else DEFAULT_TITLE


def update_session_title(session_id, new_title):
    conn = None
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sessions (id, title) VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET title = excluded.title
        ''', (session_id, new_title))
        conn.commit()
        return True
    except Exception as e:
        log.error(f"Erro ao atualizar título da sessão '{session_id}': {e}")
        return False
    finally:
        if conn:
            conn.close()


def toggle_session_pin(session_id, is_pinned):
    conn = None
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT title FROM sessions WHERE id = ?', (session_id,))
        row = cursor.fetchone()
        title = row[0] if row else _first_prompt(cursor, session_id)
        cursor.execute('''
            INSERT INTO sessions (id, title, is_pinned) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET is_pinned = excluded.is_pinned
        ''', (session_id, title, 1 if is_pinned else 0))
        conn.commit()
        return True
    except Exception as e:
        log.error(f"Erro ao alternar fixação da sessão '{session_id}': {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_recent_sessions(limit=12):
    """Sessões de texto mais recentes (exclui voice_*), fixadas primeiro.
    Dicts com id, title, is_pinned, last_active ('YYYY-MM-DD HH:MM:SS', hora local),
    msg_count (mensagens na sessão), last_message (texto da última), last_reply
    (última resposta do JARVIS, ou a última mensagem) e mode ('chat'/'copilot',
    da última mensagem com modo gravado; padrão 'chat') — p/ os save slots."""
    conn = None
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT session_id, MAX(timestamp) AS last_active, COUNT(*) AS msg_count
            FROM history
            WHERE session_id NOT LIKE 'voice_%'
            GROUP BY session_id
            ORDER BY last_active DESC
            LIMIT ?
        ''', (limit,))
        session_rows = cursor.fetchall()

        result = []
        for s_id, last_active, msg_count in session_rows:
            cursor.execute('SELECT title, is_pinned FROM sessions WHERE id = ?', (s_id,))
            meta = cursor.fetchone()
            if meta:
                title, is_pinned = meta[0], bool(meta[1])
            else:
                title, is_pinned = _first_prompt(cursor, s_id), False
            cursor.execute('''
                SELECT content FROM history WHERE session_id = ?
                ORDER BY timestamp DESC, id DESC LIMIT 1
            ''', (s_id,))
            last = cursor.fetchone()
            last_message = (last[0] or "") if last else ""
            cursor.execute('''
                SELECT content FROM history WHERE session_id = ? AND role = 'assistant'
                ORDER BY timestamp DESC, id DESC LIMIT 1
            ''', (s_id,))
            reply = cursor.fetchone()
            cursor.execute('''
                SELECT mode FROM history WHERE session_id = ? AND mode IS NOT NULL
                ORDER BY timestamp DESC, id DESC LIMIT 1
            ''', (s_id,))
            mode = cursor.fetchone()
            result.append({"id": s_id, "title": title, "is_pinned": is_pinned,
                           "last_active": to_local(last_active), "msg_count": msg_count,
                           "last_message": last_message,
                           "last_reply": (reply[0] or "") if reply else last_message,
                           "mode": (mode[0] if mode else None) or "chat"})
        result.sort(key=lambda s: not s["is_pinned"])  # sort estável: mantém recência
        return result
    except Exception as e:
        log.error(f"Erro ao obter sessões recentes: {e}")
        return []
    finally:
        if conn:
            conn.close()


def delete_session(session_id):
    """Apaga a sessão inteira (histórico + título/fixação). True se deu certo."""
    conn = None
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM history WHERE session_id = ?', (session_id,))
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        conn.commit()
        return True
    except Exception as e:
        log.error(f"Erro ao apagar a sessão '{session_id}': {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_session_title(session_id):
    conn = None
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT title FROM sessions WHERE id = ?', (session_id,))
        row = cursor.fetchone()
        return row[0] if row else _first_prompt(cursor, session_id)
    except Exception as e:
        log.error(f"Erro ao obter título da sessão '{session_id}': {e}")
        return DEFAULT_TITLE
    finally:
        if conn:
            conn.close()
