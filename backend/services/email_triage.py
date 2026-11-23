"""Prioridade e categoria dos e-mails — regras determinísticas (lógica pura, testada).

Score: marcador IMPORTANT/STARRED (+), remetente VIP (++), palavras de urgência no
assunto (+), não lido (+), Promoções/Social (−). Faixas ALTA / MÉDIA / BAIXA.
Categoria serve ao "organize meu e-mail" (`services/email_organize.py`).
"""
import re
import unicodedata

HIGH, MEDIUM, LOW = "ALTA", "MÉDIA", "BAIXA"
URGENT, FINANCE, PROMO, SOCIAL, OTHER = "urgente", "financeiro", "promocoes", "social", "outros"

_URGENT_RE = re.compile(r"\b(urgente|urgencia|prazo|hoje|imediat\w*|importante|asap|entrevista|prova|"
                        r"reuniao|deadline|ultimo dia|vence\w*|vencimento|atrasad\w*)\b")
_FINANCE_RE = re.compile(r"\b(fatura|boleto|pagamento|cobranca|nota fiscal|nf-?e|extrato|pix|recibo|"
                         r"invoice|vencimento|parcela|cartao)\b")
_PROMO_RE = re.compile(r"(\d+\s?% ?off|\bpromo\w*|\bdesconto\w*|\boferta\w*|black friday|cupom|newsletter)")


def _plain(text):
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def score(msg, vip=()):
    labels = set(msg.get("labels") or [])
    subject = _plain(msg.get("subject"))
    points = 0
    if "IMPORTANT" in labels:
        points += 2
    if "STARRED" in labels:
        points += 2
    if (msg.get("from_addr") or "").lower() in {v.lower() for v in vip or ()}:
        points += 4
    if _URGENT_RE.search(subject):
        points += 2
    if _FINANCE_RE.search(subject):
        points += 1
    if msg.get("unread"):
        points += 1
    if labels & {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"} or _PROMO_RE.search(subject):
        points -= 4
    return points


def band(points):
    if points >= 4:
        return HIGH
    if points >= 2:
        return MEDIUM
    return LOW


def category(msg):
    labels = set(msg.get("labels") or [])
    subject = _plain(msg.get("subject"))
    if "CATEGORY_PROMOTIONS" in labels or _PROMO_RE.search(subject):
        return PROMO
    if "CATEGORY_SOCIAL" in labels:
        return SOCIAL
    if _FINANCE_RE.search(subject):
        return FINANCE
    if _URGENT_RE.search(subject) or "IMPORTANT" in labels and "URGENTE" in (msg.get("subject") or "").upper():
        return URGENT
    return OTHER


def prioritize(messages, vip=()):
    """Cópias anotadas com 'score' e 'band', mais importante primeiro (estável)."""
    items = [{**m, "score": score(m, vip)} for m in messages]
    for item in items:
        item["band"] = band(item["score"])
    return sorted(items, key=lambda m: -m["score"])


def markdown(items, limit=10):
    if not items:
        return "Caixa de entrada sem novidades nos últimos dias, Senhor."
    lines = ["**E-mails por prioridade** (`/email ler <n>` · `/email responder <n> <o que dizer>`):", ""]
    for i, m in enumerate(items[:limit], 1):
        dot = "●" if m.get("unread") else "○"
        lines.append(f"{i}. `{m['band']}` {dot} **{m['subject']}** — {m.get('from_name') or m.get('from_addr')}")
    return "\n".join(lines)


def summary(items, n=3):
    """Fala curta (voz/briefing), sem Markdown."""
    if not items:
        return "Caixa vazia de novidades, Senhor."
    high = [m for m in items if m.get("band") == HIGH]
    top = (high or items)[:n]
    parts = [f"{m['subject']}, de {m.get('from_name') or m.get('from_addr')}" for m in top]
    lead = f"{len(high)} e-mails urgentes" if high else f"{len(items)} e-mails recentes, nenhum urgente"
    return f"{lead}. " + "; ".join(parts) + "."
