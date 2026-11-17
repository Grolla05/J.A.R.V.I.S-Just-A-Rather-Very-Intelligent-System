"""Registro de insights: ideias, decisões e brainstorms do usuário vão para o vault.

Destino: uma nota por mês em `🧠 Brainstorms/` (`core.obsidian.INSIGHTS_NOTE_PATH`),
sempre por *append* — nada que já está na nota é reescrito.

- Automático: depois de um turno de conversa a TUI chama `capture()` numa thread;
  `worth_checking()` descarta o óbvio sem gastar LLM e `extract()` pergunta ao
  modelo (JSON) se houve uma ideia do usuário.
- Explícito: `/ideia <texto>` e a skill INSIGHT_SAVE chamam `save()` direto.
- Obsidian fora do ar: o registro fica na fila `insights_pending` (tabela config)
  e é gravado no próximo salvamento que der certo (`flush_pending`).
- Repetição: o mesmo resumo não é gravado duas vezes em `SEEN_DAYS` dias.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta

from core.database import db
from core.llm import query_ollama
from core.logger import log
from core.obsidian import INSIGHTS_NOTE_PATH, obsidian
from core.prompts import load_prompt

SAVED, DUPLICATE, QUEUED = "saved", "duplicate", "queued"
PENDING_KEY, SEEN_KEY = "insights_pending", "insights_seen"
MIN_CHARS, MIN_WORDS = 40, 8
SEEN_DAYS = 7
PENDING_MAX = 50
TITLE_MAX, SUMMARY_MAX = 80, 1200
EXTRACT_INPUT_MAX = 3000  # caracteres de cada lado da conversa que vão ao modelo

# Modelos pequenos às vezes devolvem "INSIGHT: Modo viagem" ou "Ideia - Modo viagem"
_TITLE_PREFIX_RE = re.compile(r"^(insight|ideia|idea|brainstorm|decis[ãa]o|t[íi]tulo)\s*[:\-–—]\s*", re.I)

_MONTHS = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
           "agosto", "setembro", "outubro", "novembro", "dezembro")
_HEADER = """---
tipo: brainstorm
criado: {date}
tags:
  - tipo/brainstorm
  - origem/jarvis
---
# Insights — {month_name} de {year}

> Ideias, decisões e brainstorms registrados pelo J.A.R.V.I.S durante as conversas.
"""


def worth_checking(user_text):
    """Vale perguntar ao modelo? Mensagem curta, comando ou trecho de código: não."""
    text = (user_text or "").strip()
    if len(text) < MIN_CHARS or text.startswith("/") or "```" in text or "~~~" in text:
        return False
    return len(text.split()) >= MIN_WORDS


def extract(user_text, reply=""):
    """{'title', 'summary'} se a mensagem trouxe uma ideia/decisão do usuário; senão None."""
    prompt = load_prompt("extract_insight.md", message=(user_text or "")[:EXTRACT_INPUT_MAX],
                         reply=(reply or "")[:EXTRACT_INPUT_MAX])
    try:
        raw = query_ollama([{"role": "user", "content": prompt}], format="json", temperature=0)
        data = json.loads(raw or "{}")
    except Exception as e:
        log.debug(f"[INSIGHTS] Extração falhou: {e}")
        return None
    if not isinstance(data, dict) or data.get("insight") is not True:
        return None
    title = _TITLE_PREFIX_RE.sub("", _clean(data.get("title"), TITLE_MAX)).strip()
    summary = _clean(data.get("summary"), SUMMARY_MAX, keep_lines=True)
    return {"title": title, "summary": summary} if title and summary else None


def _clean(value, limit, keep_lines=False):
    text = str(value or "").strip()
    if not keep_lines:
        text = " ".join(text.split())
    return text[:limit].strip()


def _digest(summary):
    normalized = re.sub(r"\W+", " ", (summary or "").lower()).strip()
    return hashlib.sha1(normalized.encode("utf-8", "ignore")).hexdigest()


def note_path(now):
    return INSIGHTS_NOTE_PATH.format(month=now.strftime("%Y-%m"))


def note_header(now):
    return _HEADER.format(date=now.strftime("%Y-%m-%d"), month_name=_MONTHS[now.month - 1], year=now.year)


def entry(title, summary, origin, now):
    lines = ["", f"## {now.strftime('%d/%m %H:%M')} — {title}", "", summary]
    if origin:
        lines += ["", f"> origem: {origin}"]
    return "\n".join(lines) + "\n"


def _seen(now):
    """Digests recentes ({digest: 'YYYY-MM-DD'}), já sem os vencidos."""
    data = db.get_config(SEEN_KEY)
    limit = (now - timedelta(days=SEEN_DAYS)).strftime("%Y-%m-%d")
    return {k: v for k, v in data.items() if isinstance(v, str) and v >= limit} if isinstance(data, dict) else {}


def _pending():
    data = db.get_config(PENDING_KEY)
    return [i for i in data if isinstance(i, dict) and i.get("path") and i.get("text")] if isinstance(data, list) else []


def flush_pending(client=None):
    """Tenta gravar o que ficou na fila; devolve quantos entraram no vault."""
    client = client or obsidian
    queue = _pending()
    if not queue:
        return 0
    done = 0
    for item in queue:
        if not client.append_note(item["path"], item["text"], header=item.get("header", "")):
            break  # Obsidian ainda fora: mantém a ordem e tenta depois
        done += 1
    if done:
        db.save_config(PENDING_KEY, queue[done:])
        log.info(f"[INSIGHTS] {done} registro(s) da fila gravados no vault.")
    return done


def save(title, summary, origin="", now=None, client=None):
    """Grava um insight. SAVED, DUPLICATE (já registrado há pouco) ou QUEUED (Obsidian fora)."""
    client = client or obsidian
    now = now or datetime.now()
    title, summary = _clean(title, TITLE_MAX), _clean(summary, SUMMARY_MAX, keep_lines=True)
    if not title or not summary:
        raise ValueError("Insight sem título ou sem conteúdo.")
    seen = _seen(now)
    digest = _digest(summary)
    if digest in seen:
        return DUPLICATE
    seen[digest] = now.strftime("%Y-%m-%d")
    db.save_config(SEEN_KEY, seen)

    item = {"path": note_path(now), "header": note_header(now), "text": entry(title, summary, origin, now)}
    queue = _pending()
    if queue:  # o que ficou para trás entra antes, na ordem em que aconteceu
        flush_pending(client)
        queue = _pending()
    if not queue and client.append_note(item["path"], item["text"], header=item["header"]):
        log.info(f"[INSIGHTS] Registrado no vault ({len(summary)} caracteres).")
        return SAVED
    db.save_config(PENDING_KEY, (queue + [item])[-PENDING_MAX:])
    log.warning("[INSIGHTS] Obsidian inacessível: insight guardado na fila.")
    return QUEUED


def save_text(text, origin="", now=None, client=None):
    """`/ideia <texto>` e skill: a 1ª linha (ou frase) vira o título. Devolve a fala do JARVIS."""
    text = (text or "").strip()
    if not text:
        return "Qual é a ideia, Senhor? Use `/ideia <texto>`."
    first = re.split(r"(?<=[.!?])\s|\n", text, maxsplit=1)[0].strip()
    title = first if len(first) <= TITLE_MAX else first[:TITLE_MAX - 1].rstrip() + "…"
    return reply_for(save(title, text, origin, now, client), title)


def reply_for(status, title):
    if status == SAVED:
        return f"Ideia registrada em **🧠 Brainstorms**: {title}"
    if status == DUPLICATE:
        return "Essa ideia já está registrada, Senhor. Não vou anotar duas vezes."
    return "O Obsidian não respondeu. Guardei a ideia e gravo no vault assim que ele voltar, Senhor."


def capture(user_text, reply="", origin="", now=None, client=None):
    """Pós-turno: detecta e grava. Devolve o título (gravado ou na fila) ou None."""
    if not worth_checking(user_text):
        return None
    found = extract(user_text, reply)
    if not found:
        return None
    try:
        status = save(found["title"], found["summary"], origin, now, client)
    except Exception as e:
        log.warning(f"[INSIGHTS] Falha ao registrar: {e}")
        return None
    return None if status == DUPLICATE else found["title"]
