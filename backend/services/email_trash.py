"""'Apaga o e-mail 3' → Lixeira do Gmail, sempre com confirmação.

Só move para a Lixeira (`gmail.trash`): o Gmail esvazia sozinho em 30 dias e dá
para desfazer. Exclusão permanente não existe no JARVIS.

O que apagar sai **da fala do usuário**, nunca do conteúdo dos e-mails:
- números da última lista mostrada ("e-mails 2 e 5"), ou
- uma categoria clara ("as promoções", "as de rede social") aplicada a essa lista.
Sem número nem categoria ("apaga meus e-mails") → pergunta quais; nada é armado.
"""
import re
import unicodedata

from core import gmail, pending
from services import email_triage as triage
from services import mailbox

CONFIRM_TIMEOUT_S = 120
MAX_TRASH = 50
SHOW_MAX = 15
_CATEGORIES = (
    (re.compile(r"\b(promoc\w*|propaganda\w*|ofertas?|newsletters?|marketing|spam)\b"), triage.PROMO),
    (re.compile(r"\b(rede social|redes sociais|social|sociais|notificac\w*)\b"), triage.SOCIAL),
)


def _plain(text):
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _numbers(text):
    seen = []
    for n in re.findall(r"\b(\d{1,2})\b", text or ""):
        if int(n) not in seen:
            seen.append(int(n))
    return seen


def select(text):
    """E-mails da última lista que a frase aponta (por número ou categoria)."""
    numbers = _numbers(text)
    if numbers:
        return [m for m in (mailbox.get(n) for n in numbers) if m]
    plain = _plain(text)
    for pattern, cat in _CATEGORIES:
        if pattern.search(plain):
            return [m for m in mailbox._last if triage.category(m) == cat]
    return []


def _move(items):
    try:
        moved = gmail.trash([m["id"] for m in items])
    except gmail.GmailError as e:
        return str(e)
    ids = {m["id"] for m in items}
    mailbox._last[:] = [m for m in mailbox._last if m["id"] not in ids]   # a numeração vista muda
    return (f"{moved} e-mail(s) na Lixeira do Gmail, Senhor. Dá para recuperar por 30 dias. "
            "Peça \"meus e-mails\" para ver a lista nova.")


def request(text, owner=None):
    """Arma a confirmação e devolve o texto para o usuário."""
    problem = mailbox.ready()
    if problem:
        return problem
    if not mailbox._last:
        try:
            mailbox.priority()
        except gmail.GmailError as e:
            return str(e)
    items = select(text)[:MAX_TRASH]
    if not items:
        return ("Quais e-mails, Senhor? Diga os números da lista (\"apaga os e-mails 2 e 5\") ou uma categoria "
                "(\"apaga as promoções\"). `/email` mostra a lista numerada.")
    lines = [f"Mover para a Lixeira do Gmail ({len(items)}):", ""]
    lines += [f"- **{m['subject']}** — {m.get('from_name') or m.get('from_addr')}" for m in items[:SHOW_MAX]]
    if len(items) > SHOW_MAX:
        lines.append(f"- … e mais {len(items) - SHOW_MAX}")
    lines += ["", "Ficam recuperáveis por 30 dias. Confirma? (**sim** / **não**)"]
    question = "\n".join(lines)
    armed = pending.arm("EMAIL_TRASH", question, lambda it=items: _move(it),
                        on_decline=lambda: "Nada foi apagado, Senhor.", timeout_s=CONFIRM_TIMEOUT_S, owner=owner)
    return question if armed else pending.BUSY_REPLY
