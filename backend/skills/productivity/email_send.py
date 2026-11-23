"""Skill EMAIL_SEND — responde ou escreve e-mail (com anexo do computador) e pede confirmação.

Fluxo: o modelo extrai {reply_to_index, recipient, file, instruction} (`prompts/email_extract.md`)
→ contato (`services.email_contacts`) e arquivo (`services.local_files`) resolvidos fora do
LLM → rascunho (`services.email_compose`) → confirmação. Nada é enviado sem "sim".
"""
import json

from core import gmail
from core.logger import log
from core.prompts import load_prompt
from services import email_compose, email_contacts, local_files, mailbox

INTENT = "EMAIL_SEND"
PROMPT_TEXT = load_prompt("skills/email_send.md")
KEYWORDS = ("email*", "e-mail*", "respond*", "responde", "envi*", "manda*", "escrev*", "anex*")


def _extract(command):
    from core.llm import query_ollama
    return query_ollama([{"role": "user", "content": load_prompt("email_extract.md", command=command)}],
                        format="json", temperature=0)


def _fields(entity, command):
    try:
        data = json.loads(_extract(command) or "{}")
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    index = data.get("reply_to_index")
    try:
        index = int(index) if index not in (None, "", "null") else None
    except (TypeError, ValueError):
        index = None
    clean = lambda v: (str(v).strip() if v not in (None, "null") else "") or ""  # noqa: E731
    return index, clean(data.get("recipient")), clean(data.get("file")), clean(data.get("instruction")) or command


def execute(entity, command):
    problem = mailbox.ready()
    if problem:
        return problem
    index, recipient, filename, instruction = _fields(entity, command)
    try:
        if index:
            msg = mailbox.get(index)
            if not msg:
                mailbox.priority()
                msg = mailbox.get(index)
            if not msg:
                return f"Não há e-mail {index} na lista, Senhor. Peça \"meus e-mails\" primeiro."
            return email_compose.confirm_send(email_compose.draft_reply(msg, instruction))

        if not recipient:
            return "Para quem envio, Senhor? Diga o nome ou o endereço."
        status, found = email_contacts.resolve(recipient)
        if status == email_contacts.MANY:
            return email_contacts.ask_text(recipient, found)
        if status == email_contacts.NONE:
            return (f"Não achei o e-mail de **{recipient}**, Senhor. Diga o endereço ou grave com "
                    f"`/email contato {recipient.split()[0]} <endereço>`.")
        attachments = []
        if filename:
            fstatus, fvalue = local_files.find(filename)
            if fstatus == local_files.BLOCKED:
                return f"Não anexo `{filename}`, Senhor: {fvalue}."
            if fstatus == local_files.NONE:
                return f"Não encontrei `{filename}` na Área de Trabalho, Documentos ou Downloads, Senhor."
            if fstatus == local_files.MANY:
                lines = [f"Achei mais de um `{filename}`, Senhor. Repita com o caminho completo:", ""]
                lines += [f"{i}. `{p}`" for i, p in enumerate(fvalue, 1)]
                return "\n".join(lines)
            attachments = [str(fvalue)]
        alias = None if gmail.valid_address(recipient) else recipient
        draft = email_compose.draft_new(found, instruction, attachments, alias=alias)
        return email_compose.confirm_send(draft)
    except gmail.GmailError as e:
        return str(e)
    except Exception as e:
        log.warning(f"[EMAIL] EMAIL_SEND falhou: {e}")
        return "Não consegui montar o e-mail agora, Senhor. Nada foi enviado."
