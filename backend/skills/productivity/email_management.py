# ⚠️ ACESSO SENSÍVEL: lê a caixa do Gmail, envia e-mail (com anexo do computador), move e-mails
# para a Lixeira e organiza a caixa. Tudo que altera algo só acontece depois de confirmação
# explícita, com rascunho/lista/plano à vista. Nunca exclui de vez.
"""Skill EMAIL_MANAGEMENT — um cartucho para o Gmail: ler, enviar/responder, apagar e organizar.

A ação sai da frase por regex (sem nova ida ao modelo), nesta ordem:
1. apagar    "apaga o e-mail 3", "joga as promoções na lixeira" → services.email_trash
2. organizar "organize meu e-mail", "limpa minha caixa"         → services.email_organize
3. enviar    "responda o e-mail 2 dizendo que confirmo"         → modelo extrai os campos
             (`prompts/email_extract.md`) → contato/arquivo fora do LLM → rascunho → confirmação
4. ler       "leia o e-mail 2" resume; o resto lista por prioridade (services.mailbox)
"""
import json
import re

from core import gmail
from core.logger import log
from core.prompts import load_prompt
from services import email_compose, email_contacts, email_organize, email_trash, local_files, mailbox

INTENT = "EMAIL_MANAGEMENT"
PROMPT_TEXT = load_prompt("skills/email_management.md")
KEYWORDS = ("email*", "e-mail*", "inbox", "caixa de entrada", "mensage*", "gmail",
            "respond*", "responde", "envi*", "manda*", "escrev*", "anex*",
            "apag*", "exclu*", "delet*", "lixeira", "joga fora", "remov*",
            "organiz*", "arrum*", "limp*")

READ, SEND, TRASH, ORGANIZE = "read", "send", "trash", "organize"

_TRASH_RE = re.compile(r"\b(apag\w*|exclu\w*|delet\w*|lixeira|joga\w* fora|remov\w*)\b")
_ORGANIZE_RE = re.compile(r"\b(organiz\w*|arrum\w*|limp\w*)\b")
_SEND_RE = re.compile(r"\b(respond\w*|envi\w*|mand\w*|escrev\w*|anex\w*|encaminh\w*)\b")
# "me manda um resumo dos e-mails" pede leitura, não envio: pista de leitura sem destinatário.
_READ_CUE_RE = re.compile(r"\b(resum\w*|quais|lista\w*)\b")
_RECIPIENT_RE = re.compile(r"\b(para|pra|pro)\b|@")
_READ_RE = re.compile(r"\b(le|leia|ler|abre|abra|abrir|resum\w*|mostra|o que diz)\b")


def _plain(text):
    return (text or "").lower().replace("ê", "e").replace("é", "e").replace("ç", "c").replace("ã", "a")


def action_for(entity, command):
    """Qual das 4 ações a frase pede (lógica pura, testada)."""
    text = _plain(f"{entity or ''} {command or ''}")
    if _TRASH_RE.search(text):
        return TRASH
    if _ORGANIZE_RE.search(text):
        return ORGANIZE
    if _SEND_RE.search(text) and not (_READ_CUE_RE.search(text) and not _RECIPIENT_RE.search(text)):
        return SEND
    return READ


def execute(entity, command):
    action = action_for(entity, command)
    log.debug(f"[EMAIL] ação: {action}")
    if action == TRASH:
        return email_trash.request(f"{entity or ''} {command or ''}".strip())
    problem = mailbox.ready()
    if problem:
        return problem
    if action == ORGANIZE:
        return email_organize.organize()
    if action == SEND:
        return _send(entity, command)
    return _read(entity, command)


# --- ler ---------------------------------------------------------------------------------

def _read(entity, command):
    text = f"{entity or ''} {command or ''}"
    n = mailbox.number_in(text)
    if n and _READ_RE.search(_plain(text)):
        return mailbox.read_text(n)
    return mailbox.priority_text()


# --- enviar / responder ------------------------------------------------------------------

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


def _send(entity, command):
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
        log.warning(f"[EMAIL] envio falhou: {e}")
        return "Não consegui montar o e-mail agora, Senhor. Nada foi enviado."
