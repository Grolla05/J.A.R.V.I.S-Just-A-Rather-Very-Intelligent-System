"""Caixa de entrada para TUI, voz, briefing e ponte: lista priorizada + leitura.

A última lista mostrada fica guardada (`_last`): "e-mail 2" é sempre o 2º da lista
que o usuário viu. O corpo lido vai ao modelo **como dado** (`prompts/email_summarize.md`)
— nada nele vira skill, confirmação ou destinatário.
"""
import re

from core import gmail
from core.database import db
from core.logger import log
from core.prompts import load_prompt
from services import email_triage as triage

VIP_KEY = "email_vip"
LIST_MAX = 20
_last = []


def vip_list():
    try:
        value = db.get_config(VIP_KEY)
    except Exception:
        return set()
    return {v.lower() for v in value} if isinstance(value, list) else set()


def add_vip(address):
    address = (address or "").strip().lower()
    if not gmail.valid_address(address):
        return f"`{address}` não é um e-mail válido, Senhor."
    current = sorted(vip_list() | {address})
    db.save_config(VIP_KEY, current)
    return f"{address} agora é VIP: e-mails dele sobem para o topo, Senhor."


def ready():
    """Texto de erro se o Gmail não está pronto; None se está."""
    if not gmail.is_configured():
        return gmail.NOT_CONFIGURED
    if not gmail.is_connected():
        return gmail.NOT_CONNECTED
    return None


def priority(limit=LIST_MAX):
    items = triage.prioritize(gmail.inbox(max_results=limit), vip_list())
    _last[:] = items
    return items


def priority_text(limit=10, short=False):
    problem = ready()
    if problem:
        return problem
    try:
        items = priority()
    except gmail.GmailError as e:
        return str(e)
    return triage.summary(items) if short else triage.markdown(items, limit)


def get(n):
    return _last[n - 1] if 1 <= n <= len(_last) else None


def number_in(text):
    match = re.search(r"\b(\d{1,2})\b", text or "")
    return int(match.group(1)) if match else None


def _stream(messages):
    from core.llm import query_ollama_stream
    return query_ollama_stream(messages, temperature=0.3)


def read_text(n):
    """Resumo do e-mail n (stream de pedaços) ou texto de erro."""
    problem = ready()
    if problem:
        return problem
    if not _last:
        try:
            priority()
        except gmail.GmailError as e:
            return str(e)
    msg = get(n)
    if not msg:
        return f"Não há e-mail {n} na lista, Senhor. Peça \"meus e-mails\" primeiro."
    try:
        body = gmail.read_body(msg["id"])
    except gmail.GmailError as e:
        return str(e)
    log.info(f"[EMAIL] Lendo e-mail {n} ({len(body)} caracteres).")
    head = f"**{msg['subject']}** — {msg.get('from_name') or msg['from_addr']}\n\n"
    prompt = load_prompt("email_summarize.md", sender=msg.get("from_name") or msg["from_addr"],
                         subject=msg["subject"], body=body)

    def chunks():
        yield head
        yield from _stream([{"role": "user", "content": prompt}])
    return chunks()


def briefing_line():
    """Linha do briefing (curta, sem Markdown) ou None se o Gmail não está pronto."""
    if ready():
        return None
    try:
        return triage.summary(priority())
    except gmail.GmailError as e:
        log.debug(f"[EMAIL] Briefing sem e-mail: {e}")
        return None


# ------------------------------------------------------------- comandos da TUI
def reply_text(n, instruction):
    """/email responder <n> <o que dizer> → rascunho + confirmação."""
    from services import email_compose
    problem = ready()
    if problem:
        return problem
    msg = get(n)
    if not msg:
        return f"Não há e-mail {n} na lista, Senhor. Use `/email` primeiro."
    try:
        return email_compose.confirm_send(email_compose.draft_reply(msg, instruction))
    except gmail.GmailError as e:
        return str(e)


def new_text(recipient, instruction):
    """/email novo <para> <o que dizer> → contato resolvido + rascunho + confirmação."""
    from services import email_compose, email_contacts
    problem = ready()
    if problem:
        return problem
    status, found = email_contacts.resolve(recipient)
    if status == email_contacts.MANY:
        return email_contacts.ask_text(recipient, found)
    if status == email_contacts.NONE:
        return f"Não achei o e-mail de **{recipient}**, Senhor. Use o endereço completo."
    alias = None if gmail.valid_address(recipient) else recipient
    try:
        return email_compose.confirm_send(email_compose.draft_new(found, instruction, alias=alias))
    except gmail.GmailError as e:
        return str(e)


def contact_text(alias, address):
    from services import email_contacts
    if email_contacts.remember(alias, address):
        return f"Anotado, Senhor: **{alias}** → `{address}`."
    return "Uso: `/email contato <apelido> <endereço válido>`."
