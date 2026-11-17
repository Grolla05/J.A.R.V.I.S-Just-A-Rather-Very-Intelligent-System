"""Lembretes contextuais: o JARVIS avisa sozinho antes dos compromissos e na hora pedida.

Dois tipos de disparo, reunidos em `collect()` (chamado pela TUI a cada 30 s, numa thread):

1. Agenda (Google Agenda, `core.google_calendar.upcoming`), por evento com horário:
   - LEAD  — `reminder_lead` min antes ("em 2 horas o senhor tem a prova…");
   - LEAVE — evento com local e rota conhecida: avisa `LEAVE_WARN_MIN` antes da hora
     de sair (início − trajeto − `LEAVE_MARGIN_MIN`);
   - FINAL — sem rota: `reminder_final` min antes do início.
   Cada disparo sai uma vez: a chave `id|início|tipo` fica em `reminders_fired`
   (mudar o horário do evento rearma). LEAD atrasado mais de `LEAD_GRACE_MIN` é
   descartado — não faz sentido dizer "em 2 horas" faltando 20 minutos.
2. Pedido ("me lembra em 30 min de…", `/lembrete`): tabela `reminders` do SQLite.
   Os que venceram com a TUI fechada saem num resumo na próxima abertura.

A frase do aviso de agenda vem do LLM (`prompts/reminder.md`) só para variar o tom;
se ela não trouxer o horário certo (ou o modelo demorar), vale o texto determinístico.
Lógica pura com relógio e fontes injetáveis — a TUI só entrega.
"""
import json
import re
import sqlite3
import time
import unicodedata
from datetime import datetime, timedelta

from core.database import db
from core.logger import log
from core.prompts import load_prompt

LEAD, LEAVE, FINAL, MANUAL = "lead", "leave", "final", "manual"
FIRED_KEY, GEO_KEY = "reminders_fired", "reminders_geo_cache"
LEAD_GRACE_MIN = 30     # LEAD mais atrasado que isso não sai
LEAVE_MARGIN_MIN = 10   # folga na chegada
LEAVE_WARN_MIN = 15     # antecedência do aviso de saída
TRAVEL_HORIZON_MIN = 180  # só calcula rota de evento a até 3 h
TRAVEL_TTL_S = 600
FIRED_KEEP_DAYS = 2
MANUAL_LATE_MIN = 5     # lembrete vencido há mais que isso = "enquanto estava fora"
LOOKAHEAD_HOURS = 24
PHRASE_TIMEOUT_S = 8
GEO_CACHE_MAX = 40

_ONLINE_RE = re.compile(r"https?://|meet\.google|zoom|teams|discord|online|remoto|virtual", re.I)
_travel_cache = {}  # (id, início) -> (monotonic, resultado)


# --------------------------------------------------------------- utilidades
def _plain(text):
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def humanize(minutes):
    """125 -> '2 horas e 5 minutos'; 60 -> '1 hora'; 1 -> '1 minuto'."""
    minutes = max(0, int(round(minutes)))
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hora" + ("s" if hours != 1 else ""))
    if mins or not hours:
        parts.append(f"{mins} minuto" + ("s" if mins != 1 else ""))
    return " e ".join(parts)


def _minutes_between(later, earlier):
    return int(round((later - earlier).total_seconds() / 60))


# ------------------------------------------------------------------ agenda
def event_key(event, kind):
    start = event["start"].isoformat() if event.get("start") else "?"
    return f"{event.get('id') or event.get('title', '')}|{start}|{kind}"


def plan_event(event, lead_min, final_min, travel_min=None):
    """[(tipo, quando)] dos avisos de um evento. Dia inteiro / sem horário: nenhum."""
    start = event.get("start")
    if event.get("all_day") or not start:
        return []
    plan = []
    if lead_min:
        plan.append((LEAD, start - timedelta(minutes=lead_min)))
    if travel_min is not None:
        leave_at = start - timedelta(minutes=travel_min + LEAVE_MARGIN_MIN)
        plan.append((LEAVE, leave_at - timedelta(minutes=LEAVE_WARN_MIN)))
    elif final_min:
        plan.append((FINAL, start - timedelta(minutes=final_min)))
    return plan


def due(now, events, fired, lead_min, final_min, travel_fn=None):
    """Avisos de agenda que devem sair agora. Devolve (avisos, chaves a marcar).
    Um aviso por evento por rodada: se dois venceram juntos, sai o mais próximo do
    início e o outro é marcado como feito."""
    out, keys = [], []
    for event in events:
        start = event.get("start")
        if event.get("all_day") or not start or start <= now:
            continue
        travel = None
        if travel_fn and _minutes_between(start, now) <= TRAVEL_HORIZON_MIN:
            try:
                travel = travel_fn(event)
            except Exception as e:
                log.debug(f"[LEMBRETES] Rota do evento indisponível: {e}")
        ready = []
        for kind, when in plan_event(event, lead_min, final_min, travel["minutes"] if travel else None):
            key = event_key(event, kind)
            if key in fired or when > now:
                continue
            if kind == LEAD and _minutes_between(now, when) > LEAD_GRACE_MIN:
                continue
            ready.append((when, kind, key))
        if not ready:
            continue
        ready.sort()
        _when, kind, key = ready[-1]
        keys.extend(k for _w, _k, k in ready)
        out.append({"kind": kind, "key": key, "event": event,
                    "minutes": _minutes_between(start, now), "travel": travel if kind == LEAVE else None})
    return out, keys


def _fired(now):
    data = db.get_config(FIRED_KEY)
    limit = (now - timedelta(days=FIRED_KEEP_DAYS)).strftime("%Y-%m-%d")
    return {k: v for k, v in data.items() if isinstance(v, str) and v >= limit} if isinstance(data, dict) else {}


def mark_fired(keys, now, fired=None):
    fired = _fired(now) if fired is None else dict(fired)
    fired.update({key: now.strftime("%Y-%m-%d") for key in keys})
    db.save_config(FIRED_KEY, fired)
    return fired


# ------------------------------------------------------------- deslocamento
def _geocode_cached(address, traffic):
    cache = db.get_config(GEO_KEY)
    cache = cache if isinstance(cache, dict) else {}
    key = _plain(address).strip()
    if cache.get(key):
        return cache[key]
    place = traffic.geocode(address)
    # Só o acerto vai para o cache: geocode() devolve None tanto para "não existe"
    # quanto para timeout, e um timeout guardado deixaria o evento sem trajeto para
    # sempre. A nova tentativa já é limitada pelo cache de TRAVEL_TTL_S do trajeto.
    if place:
        cache[key] = place
        for old in list(cache)[:-GEO_CACHE_MAX]:
            del cache[old]
        db.save_config(GEO_KEY, cache)
    return place


def travel_minutes(event, traffic=None, clock=time.monotonic):
    """{'minutes', 'dest'} de casa até o evento, ou None (sem casa, sem local, online ou sem rota).
    Destino: local salvo com /rota citado no título/local do evento, senão o endereço do evento."""
    if traffic is None:
        from core import traffic
    cache_key = (event.get("id") or event.get("title"), event.get("start"))
    hit = _travel_cache.get(cache_key)
    if hit and clock() - hit[0] < TRAVEL_TTL_S:
        return hit[1]
    result = _travel(event, traffic)
    _travel_cache[cache_key] = (clock(), result)
    for old in list(_travel_cache)[:-50]:
        del _travel_cache[old]
    return result


def _travel(event, traffic):
    home = traffic.get_place("casa")
    if not home:
        return None
    location = (event.get("location") or "").strip()
    text = _plain(f"{event.get('title', '')} {location}")
    dest, label = None, ""
    for tag, place in traffic.list_places().items():
        name = traffic.tag_label(tag)
        if tag != "casa" and re.search(rf"\b{re.escape(name)}\b", text):
            dest, label = place, name
            break
    if dest is None:
        if not location or _ONLINE_RE.search(location):
            return None
        dest = _geocode_cached(location, traffic)
        label = location.split(",")[0].strip()
    if not dest:
        return None
    route = traffic.route(home, dest)
    if not route or not route.get("minutes"):
        return None
    return {"minutes": int(route["minutes"]), "dest": label}


# ------------------------------------------------------------------- frase
def fallback_phrase(kind, event, minutes, travel=None):
    """Texto determinístico do aviso — também são os fatos passados ao LLM."""
    title, at = event["title"], event["start"].strftime("%H:%M")
    place = f" em {event['location'].split(',')[0].strip()}" if event.get("location") else ""
    if kind == LEAVE and travel:
        leave_in = max(0, minutes - travel["minutes"] - LEAVE_MARGIN_MIN)
        when = f"em {humanize(leave_in)}" if leave_in else "agora"
        return (f"Senhor, saia {when} para {title} às {at}: "
                f"são {travel['minutes']} minutos de trajeto até {travel['dest']}.")
    if kind == FINAL:
        return f"Senhor, {title} começa em {humanize(minutes)}, às {at}{place}."
    return f"Senhor, em {humanize(minutes)}, às {at}, o senhor tem {title}{place}."


def phrase(kind, event, minutes, travel=None, query=None):
    """Frase do aviso no tom JARVIS. O LLM só reescreve os fatos; sem o horário
    certo na resposta (ou sem resposta) vale o texto determinístico."""
    facts = fallback_phrase(kind, event, minutes, travel)
    try:
        if query is None:
            from core.llm import query_ollama as query
        answer = query([{"role": "user", "content": load_prompt("reminder.md", facts=facts)}],
                       temperature=0.6, timeout=PHRASE_TIMEOUT_S)
    except Exception as e:
        log.debug(f"[LEMBRETES] Frase do modelo indisponível: {e}")
        return facts
    text = " ".join(str(answer or "").replace("*", "").replace("#", "").split()).strip('"“” ')
    if not text or len(text) > 280 or not keeps_facts(kind, text, event, minutes) or invents_numbers(text, facts):
        return facts
    return text


def invents_numbers(text, facts):
    """Número na frase que não está nos fatos = inventado (visto no teste real: um
    aviso de 2 h com "Sai em 15 minutos" que ninguém pediu)."""
    known = set(re.findall(r"\d+", facts))
    return any(n not in known for n in re.findall(r"\d+", text))


_NUMBER_WORDS = {1: ("um", "uma"), 2: ("dois", "duas"), 3: ("três", "tres")}


def _mentions_amount(text, amount, unit):
    """'2 horas' / 'duas horas' / '2h' — o número com a unidade logo depois."""
    words = (str(amount),) + _NUMBER_WORDS.get(amount, ())
    short = "h" if unit == "hora" else "min"
    return any(re.search(rf"\b{re.escape(w)}\s*(?:{unit}|{short}\b)", text) for w in words)


def keeps_facts(kind, text, event, minutes):
    """A frase do modelo manteve o essencial? Horário exato, o "daqui a quanto tempo"
    (o que dá a sensação de aviso) e, no de saída, a ordem de sair."""
    low = text.lower()
    if event["start"].strftime("%H:%M") not in text:
        return False
    if kind == LEAVE:
        return bool(re.search(r"\bsa(ia|ir|ída|ida)\b", low))
    hours, mins = divmod(max(0, int(round(minutes))), 60)
    if hours:
        return _mentions_amount(low, hours, "hora")
    return _mentions_amount(low, mins, "minuto")


# ------------------------------------------------------- lembretes por pedido
_NUMBERS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "cinco": 5, "dez": 10, "quinze": 15,
            "vinte": 20, "trinta": 30, "quarenta": 40, "meia": 0.5}
_WORDS = "|".join(_NUMBERS)
_REL_HM_RE = re.compile(r"\b(?:em|daqui(?:\s+a)?|dentro\s+de)\s+(\d{1,2})\s*h\s*(\d{1,2})\b")
_REL_RE = re.compile(
    rf"\b(?:em|daqui(?:\s+a)?|dentro\s+de)\s+(\d+(?:[.,]\d+)?|{_WORDS})\s*"
    r"(horas?|hrs?|h|minutos?|mins?|min|m|segundos?|seg|s)\b"
    rf"(?:\s+e\s+(\d{{1,2}}|meia)(?:\s*(?:minutos?|mins?|min))?)?")
_ABS_RE = re.compile(r"\b(?:[aà]s?\s+)?(\d{1,2})\s*(?:(?::|h)\s*(\d{2})\b|h\b|\s+horas?\b)")
_ABS_AT_RE = re.compile(r"\b[aà]s\s+(\d{1,2})\b(?!\s*[:h\d])")
_TOMORROW_RE = re.compile(r"\bamanha\b")
_REQUEST_RE = re.compile(
    r"^\s*(jarvis[,!.]?\s+)?(por favor[,]?\s+)?((me\s+)?(lembr[ae]r?|avis[ae]r?)(\s+me)?\b|lembrete\b|cri[ae]\s+um\s+lembrete\b)?"
    r"[\s:,\-]*", re.I)
_LEAD_WORD_RE = re.compile(r"^(de|que|para|pra|sobre)\s+", re.I)


def _amount(token):
    token = token.replace(",", ".")
    return float(token) if token[0].isdigit() else float(_NUMBERS[token])


def _strip_accents_keep_len(text):
    """Sem acentos, mesmo comprimento (as posições dos matches valem no texto original)."""
    out = []
    for ch in text:
        base = unicodedata.normalize("NFKD", ch)[0]
        out.append(base if len(base) == 1 else ch)
    return "".join(out)


def parse_when(text, now):
    """'me lembra em 30 min de tirar a roupa' -> (datetime, 'tirar a roupa'). None se não há horário.
    Aceita: em/daqui N min|horas, em 1h30, meia hora, 1 hora e meia, às 18h, 18:30, amanhã às 9h."""
    original = (text or "").strip()
    plain = _strip_accents_keep_len(original).lower()
    tomorrow = _TOMORROW_RE.search(plain)
    when = span = None

    match = _REL_HM_RE.search(plain)
    if match:
        when, span = now + timedelta(hours=int(match.group(1)), minutes=int(match.group(2))), match.span()
    if when is None:
        match = _REL_RE.search(plain)
        if match:
            amount, unit = _amount(match.group(1)), match.group(2)
            if unit.startswith("h"):
                delta = timedelta(hours=amount)
            elif unit.startswith("s"):
                delta = timedelta(seconds=amount)
            else:
                delta = timedelta(minutes=amount)
            extra = match.group(3)
            if extra:
                delta += timedelta(minutes=30 if extra == "meia" else int(extra)) if unit.startswith("h") \
                    else timedelta(seconds=30 if extra == "meia" else 0)
            when, span = now + delta, match.span()
    if when is None:
        match = _ABS_RE.search(plain) or _ABS_AT_RE.search(plain)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2)) if match.re is _ABS_RE and match.group(2) else 0
            if hour > 23 or minute > 59:
                return None
            when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if tomorrow or when <= now:
                when += timedelta(days=1)
            span = match.span()
    if when is None:
        return None

    rest = original[:span[0]] + " " + original[span[1]:]
    if tomorrow:
        rest = re.sub(r"\bamanh[ãa]\b", " ", rest, flags=re.I)
    return when, clean_text(rest)


def clean_text(text):
    """Tira o pedido ('me lembra', 'de', 'que'…) e deixa só o assunto."""
    rest = _REQUEST_RE.sub("", " ".join((text or "").split()), count=1)
    rest = _LEAD_WORD_RE.sub("", rest.strip(" ,.;:-"))
    return rest.strip(" ,.;:-")


def _iso(when):
    return when.replace(microsecond=0).isoformat()


def add(text, due_at):
    try:
        with db.connection() as conn:
            return conn.execute("INSERT INTO reminders (text, due_at) VALUES (?, ?)", (text, _iso(due_at))).lastrowid
    except sqlite3.Error as e:
        log.error(f"[LEMBRETES] Falha ao gravar: {e}")
        return None


def pending():
    """Lembretes ainda não disparados, o mais próximo primeiro: [{'id','text','due_at'}]."""
    try:
        with db.connection() as conn:
            rows = conn.execute("SELECT id, text, due_at FROM reminders WHERE fired_at IS NULL "
                                "ORDER BY due_at, id").fetchall()
    except sqlite3.Error as e:
        log.error(f"[LEMBRETES] Falha ao ler: {e}")
        return []
    return [{"id": i, "text": t, "due_at": datetime.fromisoformat(d)} for i, t, d in rows]


def remove(index):
    """Remove o n-ésimo pendente (número da lista). Devolve o lembrete removido ou None."""
    items = pending()
    if not 1 <= index <= len(items):
        return None
    item = items[index - 1]
    try:
        with db.connection() as conn:
            conn.execute("DELETE FROM reminders WHERE id = ?", (item["id"],))
    except sqlite3.Error as e:
        log.error(f"[LEMBRETES] Falha ao remover: {e}")
        return None
    return item


def pop_due(now):
    """Lembretes vencidos: marca como disparados e devolve."""
    items = [i for i in pending() if i["due_at"] <= now]
    if not items:
        return []
    try:
        with db.connection() as conn:
            conn.executemany("UPDATE reminders SET fired_at = ? WHERE id = ?",
                             [(_iso(now), i["id"]) for i in items])
    except sqlite3.Error as e:
        log.error(f"[LEMBRETES] Falha ao marcar como disparado: {e}")
        return []
    return items


def _when_label(due_at, now):
    at = due_at.strftime("%H:%M")
    days = (due_at.date() - now.date()).days
    if days == 0:
        return f"hoje às {at}"
    return f"amanhã às {at}" if days == 1 else f"{due_at.strftime('%d/%m')} às {at}"


def _ask_llm(text):
    """Horário que o regex não pegou: o modelo devolve {'text', 'minutes'} (ou nada)."""
    try:
        from core.llm import query_ollama
        raw = query_ollama([{"role": "system", "content": load_prompt("skills/reminder_parse.md")},
                            {"role": "user", "content": text}], format="json", temperature=0)
        data = json.loads(raw or "{}")
    except Exception as e:
        log.debug(f"[LEMBRETES] Modelo não entendeu o horário: {e}")
        return None
    minutes = data.get("minutes") if isinstance(data, dict) else None
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not 0 < minutes <= 60 * 24 * 30:
        return None
    return float(minutes), str(data.get("text") or "").strip()


def create_from_text(text, now=None, ask_llm=_ask_llm):
    """`/lembrete <quando> <texto>` e skill REMINDER. Devolve a fala do JARVIS."""
    now = now or datetime.now()
    parsed = parse_when(text, now)
    if parsed is None and ask_llm:
        guess = ask_llm(text)
        if guess:
            parsed = (now + timedelta(minutes=guess[0]), guess[1] or clean_text(text))
    if parsed is None:
        return ("Para quando, Senhor? Diga o horário: `/lembrete em 30 min tirar a roupa` "
                "ou `/lembrete às 18h ligar para o João`.")
    due_at, subject = parsed
    if not subject:
        return "Lembrar do quê, Senhor? Diga o assunto junto com o horário."
    subject = subject[:200]
    if add(subject, due_at) is None:
        return "Não consegui gravar o lembrete, Senhor."
    return (f"Lembrete marcado para {_when_label(due_at, now)} "
            f"(em {humanize(_minutes_between(due_at, now))}): {subject}.")


def list_text(now=None):
    now = now or datetime.now()
    items = pending()
    if not items:
        return "Nenhum lembrete pendente, Senhor. Crie um com `/lembrete em 30 min <assunto>`."
    lines = [f"{i}. **{_when_label(item['due_at'], now)}** — {item['text']}" for i, item in enumerate(items, 1)]
    return "**Lembretes pendentes**\n\n" + "\n".join(lines) + "\n\n`/lembrete rm <n>` remove."


def remove_text(index):
    item = remove(index)
    if not item:
        return f"Não há lembrete {index}, Senhor. `/lembrete` lista os números."
    return f"Lembrete removido: {item['text']}."


# ------------------------------------------------------------------ coleta
def _prefs():
    from services import user_prefs
    return {key: user_prefs.get(key) for key in ("event_reminders", "reminder_lead", "reminder_final")}


def collect(now=None, calendar=None, prefs=None, travel_fn=travel_minutes, phrase_fn=phrase):
    """Tudo que deve ser avisado agora: [{'text', 'kind', 'urgent'}]. Nunca levanta.
    `urgent` (saída, início iminente, lembrete pedido) passa pelo Não Perturbe."""
    now = now or datetime.now()
    out = []
    try:
        manual = pop_due(now)
        late = [m for m in manual if _minutes_between(now, m["due_at"]) > MANUAL_LATE_MIN]
        for item in manual:
            if item not in late:
                out.append({"text": f"Lembrete, Senhor: {item['text']}.", "kind": MANUAL, "urgent": True})
        if late:
            listed = "; ".join(f"{m['text']} ({m['due_at'].strftime('%d/%m %H:%M')})" for m in late)
            noun = "lembrete venceu" if len(late) == 1 else "lembretes venceram"
            out.append({"text": f"Enquanto estive fora, {len(late)} {noun}, Senhor: {listed}.",
                        "kind": MANUAL, "urgent": True})
    except Exception as e:
        log.warning(f"[LEMBRETES] Lembretes pedidos indisponíveis: {e}")

    try:
        prefs = _prefs() if prefs is None else prefs
        if prefs.get("event_reminders"):
            if calendar is None:
                from core import google_calendar as calendar
            events = calendar.upcoming(LOOKAHEAD_HOURS, now)
            fired = _fired(now)
            found, keys = due(now, events, fired, prefs.get("reminder_lead") or 0,
                              prefs.get("reminder_final") or 0, travel_fn)
            if keys:
                mark_fired(keys, now, fired)  # antes de falar: o próximo tick não repete
            for item in found:
                text = phrase_fn(item["kind"], item["event"], item["minutes"], item["travel"])
                out.append({"text": text, "kind": item["kind"], "urgent": item["kind"] != LEAD})
    except Exception as e:
        log.warning(f"[LEMBRETES] Avisos da agenda indisponíveis: {e}")
    return out
