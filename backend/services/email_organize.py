"""'Organize meu e-mail': plano por categoria → confirmação → marcadores no Gmail.

Promoções e Social: arquivar (e marcar lido). Financeiro: marcador JARVIS/Financeiro.
Urgente: marcador JARVIS/Urgente + estrela. O resto fica onde está. Nada é apagado:
arquivar só tira da caixa de entrada (continua em "Todos os e-mails").
"""
from core import gmail, pending
from core.logger import log
from services import email_triage as triage

LABEL_URGENT, LABEL_FINANCE = "JARVIS/Urgente", "JARVIS/Financeiro"
SCAN_MAX = 100
CONFIRM_TIMEOUT_S = 120


def build_plan(messages, vip=()):
    plan = {"archive": [], "labels": {LABEL_URGENT: [], LABEL_FINANCE: []}, "star": []}
    vip = {v.lower() for v in vip or ()}
    for m in messages:
        if "INBOX" not in (m.get("labels") or ["INBOX"]):
            continue
        cat = triage.category(m)
        if (m.get("from_addr") or "").lower() in vip and cat in (triage.PROMO, triage.SOCIAL):
            continue   # VIP nunca é arquivado
        if cat in (triage.PROMO, triage.SOCIAL):
            plan["archive"].append(m["id"])
        elif cat == triage.FINANCE:
            plan["labels"][LABEL_FINANCE].append(m["id"])
        elif cat == triage.URGENT:
            plan["labels"][LABEL_URGENT].append(m["id"])
            plan["star"].append(m["id"])
    plan["labels"] = {k: v for k, v in plan["labels"].items() if v}
    return plan


def is_empty(plan):
    return not (plan["archive"] or plan["labels"] or plan["star"])


def plan_text(plan):
    lines = ["**Plano para a caixa de entrada:**", ""]
    if plan["archive"]:
        lines.append(f"- {len(plan['archive'])} promoções/redes sociais → arquivar e marcar como lidas")
    for label, ids in plan["labels"].items():
        extra = " + estrela" if label == LABEL_URGENT else ""
        lines.append(f"- {len(ids)} → marcador `{label}`{extra}")
    lines += ["", "Nada é apagado; tudo pode ser desfeito no Gmail."]
    return "\n".join(lines)


def apply(plan):
    try:
        if plan["archive"]:
            gmail.batch_modify(ids=plan["archive"], add=[], remove=["INBOX", "UNREAD"])
        for label, ids in plan["labels"].items():
            gmail.batch_modify(ids=ids, add=[gmail.ensure_label(label)], remove=[])
        if plan["star"]:
            gmail.batch_modify(ids=plan["star"], add=["STARRED"], remove=[])
    except gmail.GmailError as e:
        return f"Organização interrompida, Senhor: {e}"
    total = len(plan["archive"]) + sum(len(v) for v in plan["labels"].values())
    log.info(f"[EMAIL] Caixa organizada: {total} mensagens.")
    return f"Caixa de entrada organizada, Senhor: {total} mensagens tratadas."


def organize(fetch=None, vip=None, owner=None):
    """Monta o plano e pede confirmação. Devolve o texto para o usuário."""
    if vip is None:
        from services import mailbox
        vip = mailbox.vip_list()
    try:
        messages = (fetch or gmail.inbox)(max_results=SCAN_MAX, query="in:inbox")
    except gmail.GmailError as e:
        return str(e)
    plan = build_plan(messages, vip)
    if is_empty(plan):
        return "A caixa de entrada já está em ordem, Senhor. Nada a mover."
    question = f"{plan_text(plan)}\n\nConfirma? (**sim** aplica · **não** deixa como está)"
    armed = pending.arm("EMAIL_ORGANIZE", question, lambda p=plan: apply(p),
                        on_decline=lambda: "Deixei a caixa como estava, Senhor.",
                        timeout_s=CONFIRM_TIMEOUT_S, owner=owner)
    return question if armed else pending.BUSY_REPLY
