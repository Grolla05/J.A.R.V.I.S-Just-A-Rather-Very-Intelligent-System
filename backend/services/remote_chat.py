"""Ponte Telegram/Discord → cérebro do JARVIS (núcleo sem rede, testável).

A plataforma é só o fio: a mensagem chega aqui (processo `messenger.py`, no PC do
usuário), vai ao `brain.execute_command_stream` em **modo Chat** (sem skills de
automation/system) e a resposta volta pelo mesmo canal.

Segurança:
- Só IDs da allowlist (`TELEGRAM_ALLOWED_IDS` / `DISCORD_ALLOWED_IDS`) conversam.
  Lista vazia = ninguém. Estranho só recebe o próprio ID em `/id` (para configurar).
- Toda confirmação armada daqui tem dono `canal:usuário`: só o "sim" dessa pessoa
  aprova (core/pending.py).
"""
import uuid

from core.config import settings
from core.database import db
from core.logger import log

TELEGRAM, DISCORD = "telegram", "discord"
LIMITS = {TELEGRAM: 4000, DISCORD: 1900}
TITLES = {TELEGRAM: "Telegram", DISCORD: "Discord"}
MODE = "remote"

HELP = ("Às ordens, Senhor. Sou o J.A.R.V.I.S, falando do seu computador.\n\n"
        "Converse normalmente. Atalhos: /nova (nova conversa) · /briefing · /email · /id.\n"
        "Ações que mexem em algo (enviar e-mail, organizar a caixa) sempre pedem um \"sim\" seu antes.")


def _allowlist(channel):
    return {str(i).strip() for i in (settings.TELEGRAM_ALLOWED_IDS if channel == TELEGRAM
                                     else settings.DISCORD_ALLOWED_IDS) if str(i).strip()}


def allowed(channel, user_id):
    return str(user_id) in _allowlist(channel)


def _session_key(channel, user_id):
    return f"remote_session:{channel}:{user_id}"


def _set_title(session_id, title):
    from services import sessions
    sessions.update_session_title(session_id, title)


def new_session(channel, user_id):
    session_id = f"{channel}-{user_id}-{uuid.uuid4().hex[:8]}"
    db.save_config(_session_key(channel, user_id), session_id)
    _set_title(session_id, TITLES.get(channel, channel))
    return session_id


def session_for(channel, user_id):
    current = db.get_config(_session_key(channel, user_id))
    return current if isinstance(current, str) and current else new_session(channel, user_id)


def split_message(text, limit):
    """Quebra em pedaços ≤ limit, de preferência em parágrafo, depois em linha, por fim no meio."""
    text = text or ""
    if not text.strip():
        return []
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit + 1)
        if cut <= 0:
            cut = text.rfind("\n", 0, limit + 1)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:]
    if text:
        parts.append(text)
    return parts


def _email_text():
    from services import mailbox
    return mailbox.priority_text()


def _briefing_text():
    from core import briefing
    return briefing.generate()


def _ask_brain(channel, user_id, text, stream_fn):
    session_id = session_for(channel, user_id)
    db.log_interaction("user", text, session_id, mode=MODE)
    if stream_fn is None:
        from services.brain import execute_command_stream as stream_fn
    try:
        reply = "".join(str(chunk) for chunk in stream_fn(text, session_id=session_id, mode="chat",
                                                          owner=f"{channel}:{user_id}") if chunk)
    except Exception as e:
        log.error(f"[PONTE] Cérebro falhou ({channel}): {e}")
        return "Não consegui pensar nisso agora, Senhor. O Ollama está rodando no computador?"
    reply = reply.strip() or "Sem resposta, Senhor."
    db.log_interaction("assistant", reply, session_id, mode=MODE)
    return reply


def handle_message(channel, user_id, text, stream_fn=None):
    """Resposta (lista de mensagens já no limite da plataforma). [] = não responder."""
    user_id, text = str(user_id), (text or "").strip()
    if not text:
        return []
    command = text.split()[0].lower().split("@")[0]
    if not allowed(channel, user_id):
        if command == "/id":
            var = "TELEGRAM_ALLOWED_IDS" if channel == TELEGRAM else "DISCORD_ALLOWED_IDS"
            return [f"Seu ID é {user_id}. Para conversar comigo, o dono do computador precisa pôr esse número "
                    f"em {var} no .env do JARVIS."]
        log.info(f"[PONTE] Mensagem ignorada: {channel} {user_id} fora da allowlist.")
        return []
    limit = LIMITS.get(channel, 1900)
    if command in ("/start", "/help", "/ajuda"):
        reply = HELP
    elif command == "/id":
        reply = f"Seu ID é {user_id}, Senhor."
    elif command == "/nova":
        new_session(channel, user_id)
        reply = "Nova conversa aberta, Senhor."
    elif command == "/email":
        reply = _email_text()
    elif command == "/briefing":
        reply = _briefing_text()
    else:
        reply = _ask_brain(channel, user_id, text, stream_fn)
    return split_message(reply, limit)
