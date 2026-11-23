"""Rascunho e envio seguro de e-mail.

- O LLM só escreve **assunto e corpo** (`prompts/email_reply.md` / `email_compose.md`).
  O destinatário vem da fala do usuário (e-mail novo) ou do remetente original
  (resposta) — nunca do texto do e-mail nem do modelo.
- Nada sai sem "sim": `confirm_send` arma a pendência com Para/Assunto/anexo/corpo
  à vista. "Não" salva como rascunho no Gmail. Outra frase ("deixa mais formal")
  refaz o rascunho e pergunta de novo (`on_other`).
"""
import json
import re
from pathlib import Path

from core import gmail, pending
from core.database import db
from core.logger import log
from core.prompts import load_prompt
from services import email_contacts, local_files

CONFIRM_TIMEOUT_S = 180   # tempo para ler o rascunho antes de responder
SIGNATURE_KEY = "email_signature"


def _query(messages):
    from core.llm import query_ollama
    return query_ollama(messages, format="json", temperature=0.4)


def _signature():
    try:
        value = db.get_config(SIGNATURE_KEY)
    except Exception:
        return ""
    return (value or "").strip() if isinstance(value, str) else ""


def set_signature(text):
    db.save_config(SIGNATURE_KEY, (text or "").strip())
    return "Assinatura salva, Senhor." if text else "Assinatura removida, Senhor."


def _read_body(msg):
    try:
        return gmail.read_body(msg["id"])
    except Exception as e:
        log.debug(f"[EMAIL] Corpo indisponível para o rascunho: {e}")
        return msg.get("snippet", "")


def _parse(answer):
    try:
        data = json.loads(answer or "")
    except (TypeError, ValueError):
        match = re.search(r"\{.*\}", answer or "", re.S)
        try:
            data = json.loads(match.group(0)) if match else {}
        except ValueError:
            data = {}
    return data if isinstance(data, dict) else {}


def _finish(draft, data, fallback_subject, instruction):
    body = str(data.get("body") or "").strip() or (instruction or "").strip() or "(sem texto)"
    signature = _signature()
    if signature and not body.endswith(signature):
        body = f"{body}\n\n{signature}"
    draft.update(subject=str(data.get("subject") or "").strip() or fallback_subject, body=body)
    return draft


def draft_reply(msg, instruction, query=None):
    original = _read_body(msg)
    prompt = load_prompt("email_reply.md", sender=msg.get("from_name") or msg.get("from_addr", ""),
                         subject=msg.get("subject", ""), original=original[:4000], instruction=instruction or "")
    data = _parse((query or _query)([{"role": "user", "content": prompt}]))
    draft = {"to": msg["from_addr"], "thread_id": msg.get("thread_id"), "reply_to": msg, "attachments": [],
             "instruction": instruction}
    return _finish(draft, data, f"Re: {msg.get('subject', '')}", instruction)


def draft_new(to, instruction, attachments=(), query=None, alias=None):
    names = ", ".join(Path(a).name for a in attachments) or "nenhum"
    prompt = load_prompt("email_compose.md", recipient=to, instruction=instruction or "", attachments=names)
    data = _parse((query or _query)([{"role": "user", "content": prompt}]))
    draft = {"to": to, "thread_id": None, "reply_to": None, "attachments": list(attachments),
             "instruction": instruction, "alias": alias}
    subject = f"Arquivo: {Path(attachments[0]).name}" if attachments else "Mensagem"
    return _finish(draft, data, subject, instruction)


def describe(draft):
    lines = [f"**Para:** {draft['to']}", f"**Assunto:** {draft['subject']}"]
    for path in draft.get("attachments") or ():
        lines.append(f"**Anexo:** `{path}` ({local_files.size_text(path)})")
    lines += ["", draft["body"]]
    return "\n".join(lines)


def _raw(draft):
    return gmail.build_mime(draft["to"], draft["subject"], draft["body"], reply_to=draft.get("reply_to"),
                            attachments=draft.get("attachments") or ())


def _send(draft):
    try:
        gmail.send(_raw(draft), thread_id=draft.get("thread_id"))
    except gmail.GmailError as e:
        return str(e)
    except OSError as e:
        return f"Não consegui ler o anexo, Senhor: {e}"
    if draft.get("alias"):
        email_contacts.remember(draft["alias"], draft["to"])
    return f"E-mail enviado para {draft['to']}, Senhor."


def _save_draft(draft):
    try:
        gmail.save_draft(_raw(draft), thread_id=draft.get("thread_id"))
    except (gmail.GmailError, OSError) as e:
        return f"Não enviei. Também não consegui salvar o rascunho: {e}"
    return "Não enviei, Senhor. Ficou salvo nos rascunhos do Gmail."


def _adjust(draft, owner):
    def adjust(command):
        instruction = f"{draft.get('instruction') or ''}\nAjuste pedido: {command}"
        try:
            if draft.get("reply_to"):
                new = draft_reply(draft["reply_to"], instruction)
            else:
                new = draft_new(draft["to"], instruction, draft.get("attachments") or (), alias=draft.get("alias"))
        except Exception as e:
            log.warning(f"[EMAIL] Ajuste do rascunho falhou: {e}")
            return "Não consegui refazer o rascunho, Senhor. Nada foi enviado."
        new["to"] = draft["to"]   # o destinatário nunca muda num ajuste
        return confirm_send(new, owner=owner)
    return adjust


def confirm_send(draft, owner=None):
    """Arma a confirmação com o rascunho à vista. Devolve o texto mostrado ao usuário."""
    owner = owner or pending.current_owner()
    question = (f"Rascunho pronto, Senhor:\n\n{describe(draft)}\n\n"
                "Confirma o envio? (**sim** envia · **não** guarda como rascunho · ou diga o que mudar)")
    armed = pending.arm("EMAIL_SEND", question, lambda d=draft: _send(d), target=draft["to"],
                        on_decline=lambda d=draft: _save_draft(d), on_other=_adjust(draft, owner),
                        timeout_s=CONFIRM_TIMEOUT_S, owner=owner)
    return question if armed else pending.BUSY_REPLY
