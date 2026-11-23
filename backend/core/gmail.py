"""Gmail — ler, responder, enviar e organizar (REST, escopo `gmail.modify`).

Conta própria (`google_gmail` no Cofre, card próprio em /config → INTEGRAÇÕES): a
Agenda segue com o token dela. `gmail.modify` lê, cria rascunho, envia e mexe em
marcadores/arquivo — **não** apaga de vez. Este módulo nem expõe trash/delete.

Quem chama decide quando enviar: `send()` só é chamado depois do "sim" do usuário
(`services/email_compose.py`). Erros sobem como `GmailError` com texto amigável.
"""
import base64
import html as html_lib
import mimetypes
import re
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid, parseaddr
from pathlib import Path

from core.config import settings
from core.google_auth import CONSOLE_URL, NOT_CONFIGURED, GoogleAccount, GoogleError  # noqa: F401
from core.logger import log

SCOPE = "https://www.googleapis.com/auth/gmail.modify"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
SECRET_NAME = "google_gmail"
NOT_CONNECTED = "O Gmail não está conectado, Senhor. Conecte em /config → INTEGRAÇÕES."
DEFAULT_QUERY = "in:inbox newer_than:7d"
_META_HEADERS = ("From", "To", "Subject", "Date", "Message-ID", "References")
_ADDR_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")

_label_cache = {}


class GmailError(GoogleError):
    """Erro do Gmail já traduzido para o usuário."""


def _probe(token):
    import requests
    r = requests.get(f"{API}/profile", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    return r.json().get("emailAddress") if r.status_code == 200 else None


account = GoogleAccount([SCOPE], SECRET_NAME, "Gmail", error_cls=GmailError, not_connected=NOT_CONNECTED,
                        account_probe=_probe)


def is_configured():
    return account.is_configured()


def is_connected():
    return account.is_connected()


def connect():
    return account.connect()


def disconnect():
    _label_cache.clear()
    return account.disconnect()


def _api(method, path, params=None, json=None):
    return account.request(method, f"{API}{path}", params=params, json=json)


# ------------------------------------------------------------------ leitura
def valid_address(addr):
    addr = (addr or "").strip()
    return bool(_ADDR_RE.match(addr))


def parse_message(item):
    headers = {h.get("name", "").lower(): h.get("value", "") for h in (item.get("payload") or {}).get("headers", [])}
    name, addr = parseaddr(headers.get("from", ""))
    labels = list(item.get("labelIds") or [])
    return {
        "id": item.get("id", ""), "thread_id": item.get("threadId", ""),
        "from_name": name or addr, "from_addr": addr.lower(), "to": headers.get("to", ""),
        "subject": (headers.get("subject") or "(sem assunto)").strip(), "date": headers.get("date", ""),
        "message_id": headers.get("message-id", ""), "references": headers.get("references", ""),
        "labels": labels, "unread": "UNREAD" in labels, "snippet": html_lib.unescape(item.get("snippet") or ""),
    }


def inbox(max_results=20, query=DEFAULT_QUERY):
    """Mensagens mais recentes (metadados). Levanta GmailError."""
    listing = _api("GET", "/messages", params={"maxResults": max_results, "q": query})
    items = []
    for ref in listing.get("messages") or []:
        meta = _api("GET", f"/messages/{ref['id']}",
                    params={"format": "metadata", "metadataHeaders": list(_META_HEADERS)})
        items.append(parse_message(meta))
    return items


def _decode(data):
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def html_to_text(raw):
    raw = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", raw or "")
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", raw)
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", raw))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_body(payload):
    """Corpo em texto: prefere text/plain; senão converte o HTML."""
    plain, html_parts = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if mime == "text/plain" and data:
            plain.append(_decode(data))
        elif mime == "text/html" and data:
            html_parts.append(_decode(data))
        for sub in part.get("parts") or []:
            walk(sub)

    walk(payload or {})
    if plain:
        return "\n".join(plain).strip()
    return html_to_text("\n".join(html_parts)).strip()


def read_body(msg_id):
    item = _api("GET", f"/messages/{msg_id}", params={"format": "full"})
    return extract_body(item.get("payload"))[:settings.EMAIL_TEXT_MAX]


# ------------------------------------------------------------------ escrita
def build_mime(to, subject, body, reply_to=None, attachments=()):
    """Mensagem pronta para a API (raw base64url). `reply_to` = mensagem original (parse_message)."""
    if not valid_address(to):
        raise GmailError(f"`{to}` não é um endereço de e-mail válido, Senhor.")
    msg = EmailMessage()
    msg["To"] = to
    subject = (subject or "").strip() or "(sem assunto)"
    if reply_to:
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        if reply_to.get("message_id"):
            msg["In-Reply-To"] = reply_to["message_id"]
            msg["References"] = f"{reply_to.get('references', '')} {reply_to['message_id']}".strip()
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="jarvis.local")
    msg.set_content(body or "", charset="utf-8")
    for path in attachments or ():
        path = Path(path)
        ctype, _enc = mimetypes.guess_type(path.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")


def send(raw, thread_id=None):
    body = {"raw": raw}
    if thread_id:
        body["threadId"] = thread_id
    result = _api("POST", "/messages/send", json=body)
    log.info("[EMAIL] Mensagem enviada pelo Gmail.")
    return result


def save_draft(raw, thread_id=None):
    message = {"raw": raw}
    if thread_id:
        message["threadId"] = thread_id
    return _api("POST", "/drafts", json={"message": message})


# -------------------------------------------------------------- organização
def list_labels():
    return _api("GET", "/labels").get("labels") or []


def ensure_label(name):
    """Id do marcador (cria se não existir)."""
    if name in _label_cache:
        return _label_cache[name]
    for label in list_labels():
        if label.get("name") == name:
            _label_cache[name] = label["id"]
            return label["id"]
    created = _api("POST", "/labels", json={"name": name, "labelListVisibility": "labelShow",
                                            "messageListVisibility": "show"})
    _label_cache[name] = created.get("id")
    return _label_cache[name]


def batch_modify(ids, add=(), remove=()):
    """Marcadores em lote (arquivar = tirar INBOX; lido = tirar UNREAD). Nunca apaga."""
    ids = list(ids)
    if not ids:
        return {}
    return _api("POST", "/messages/batchModify",
                json={"ids": ids, "addLabelIds": list(add), "removeLabelIds": list(remove)})


# ----------------------------------------------------------------- contatos
def find_contacts(name, limit=5):
    """Pessoas com esse nome nas mensagens trocadas: [{'name', 'address', 'count'}], mais frequente primeiro."""
    name = (name or "").strip()
    if not name:
        return []
    listing = _api("GET", "/messages", params={"maxResults": 20, "q": f'from:"{name}" OR to:"{name}"'})
    found, needle = {}, name.lower()
    for ref in listing.get("messages") or []:
        meta = _api("GET", f"/messages/{ref['id']}",
                    params={"format": "metadata", "metadataHeaders": ["From", "To", "Cc"]})
        headers = [h.get("value", "") for h in (meta.get("payload") or {}).get("headers", [])]
        for person, addr in getaddresses(headers):
            addr = addr.lower()
            if not valid_address(addr) or (needle not in person.lower() and needle not in addr):
                continue
            entry = found.setdefault(addr, {"name": person or addr, "address": addr, "count": 0})
            entry["count"] += 1
    return sorted(found.values(), key=lambda c: -c["count"])[:limit]
