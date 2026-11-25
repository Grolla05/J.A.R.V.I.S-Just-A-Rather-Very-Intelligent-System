"""Tarefas web em segundo plano: "entra no site X e me traz Y".

Fluxo de `request(pedido)`:
    modelo planeja os passos (headless_plan.md, JSON) → core/headless valida
    (tipos fixos, ≤ 8 passos, URL pública, sem dado sensível) → passo que envia algo?
    pede confirmação (core/pending.py) → roda numa thread daemon → modelo responde o
    objetivo só com o texto da página (headless_answer.md) → state.announce

Sem plano do modelo e com link na frase, abre o link e resume. O texto da página é
dado, nunca instrução: vai ao modelo como bloco citado.
"""
import json
import re
import threading
from urllib.parse import urlsplit

from core import headless, pending
from core.browser import is_fetch_safe
from core.config import settings
from core.logger import log
from core.prompts import load_prompt

CONFIRM_TIMEOUT_S = 60
ANSWER_CHARS = 6000
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_GOAL_PREFIX_RE = re.compile(r"^(?:o\s+)?usu[aá]rio\s+(?:quer|deseja|gostaria\s+de|precisa)\s+"
                             r"(?:saber|ver|obter|conferir|descobrir|encontrar)?\s*(?:qual\s+[eé]\s+)?", re.I)
_STOPWORDS = {"o", "a", "os", "as", "de", "da", "do", "das", "dos", "na", "no", "nas", "nos", "em", "e", "ou",
              "um", "uma", "para", "pra", "por", "com", "que", "qual", "quais", "site", "pagina", "página",
              "preco", "preço", "precos", "preços", "valor", "quanto", "custa", "sobre", "me", "traz", "ver"}
_PRICE_LINE_RE = re.compile(r"^\s*(?:R\$|US\$|\$|€)\s?\d{1,3}(?:[.\s]?\d{3})*(?:,\d{2})?\s*$")
_PRICE_GOAL_RE = re.compile(r"\b(pre[cç]o\w*|valor|quanto\s+custa|custa|barat\w*|caro)\b", re.I)
PRICE_ITEMS = 5
NAME_MAX = 80
NAME_BUCKET = 40
FOCUS_AFTER = 6           # linhas mantidas depois de cada linha relevante (preço, desconto…)
FOCUS_MIN_CHARS = 200


def _announce(text):
    import core.state as state
    try:
        if state.announce:
            state.announce(text)
    except Exception as e:
        log.debug(f"[HEADLESS] Aviso não entregue: {e}")


def _run_background(fn):
    threading.Thread(target=fn, name="jarvis-headless", daemon=True).start()


# ------------------------------------------------------------------ plano
def ask_plan_llm(request_text):
    """Pedido → dict {'objetivo', 'passos'} do modelo, ou None."""
    try:
        from core.llm import query_ollama
        raw = query_ollama([{"role": "user", "content": load_prompt("headless_plan.md", request=request_text)}],
                           format="json", temperature=0, timeout=settings.TIMEOUT_LLM)
        data = json.loads(raw or "{}")
    except Exception as e:
        log.debug(f"[HEADLESS] Modelo não planejou: {e}")
        return None
    return data if isinstance(data, dict) else None


def plan(request_text, ask_llm=ask_plan_llm):
    """(objetivo, passos, erro). Link na frase vira plano mínimo se o modelo falhar."""
    request_text = " ".join((request_text or "").split())
    data = ask_llm(request_text) if ask_llm else None
    goal = clean_goal(str((data or {}).get("objetivo") or "")) or request_text[:200]
    if data:
        steps, error = headless.validate_steps(data.get("passos"))
        if steps:
            return goal, steps, None
        log.info(f"[HEADLESS] Plano recusado: {error}")
    else:
        error = "não consegui montar os passos"
    url = next((u.rstrip(".,;)") for u in _URL_RE.findall(request_text)), None)
    if url and is_fetch_safe(url):
        return goal, [{"type": "goto", "url": url}, {"type": "extract"}], None
    return goal, None, error


def clean_goal(goal):
    """"o usuário quer saber o preço da RTX" → "preço da RTX" (o aviso fala com o usuário)."""
    goal = _GOAL_PREFIX_RE.sub("", " ".join((goal or "").split())).strip(" .")
    return (goal[:1].upper() + goal[1:])[:200] if goal else ""


# ------------------------------------------------------------------ resposta
def _terms(goal, site_host=""):
    host_words = set(re.split(r"[^a-z0-9]+", site_host.lower()))
    words = re.findall(r"[a-z0-9áàâãéêíóôõúç]+", (goal or "").lower())
    return [w for w in dict.fromkeys(words) if (len(w) >= 3 or w.isdigit()) and w not in _STOPWORDS
            and w not in host_words]


def focus_text(text, goal, site_host=""):
    """Só as linhas que citam o objetivo (ex.: "rtx" e "5060") + as FOCUS_AFTER seguintes
    (onde ficam preço e desconto). Tira da frente do modelo o produto patrocinado de outra
    coisa. Pouco texto sobrando → devolve o original."""
    terms = _terms(goal, site_host)
    if not terms:
        return text
    need = min(2, len(terms))
    lines = (text or "").splitlines()
    keep = set()
    for i, line in enumerate(lines):
        low = line.lower()
        if sum(1 for t in terms if t in low) >= need:
            keep.update(range(i, min(len(lines), i + FOCUS_AFTER + 1)))
    focused = "\n".join(lines[i] for i in sorted(keep))
    return focused if len(focused) >= FOCUS_MIN_CHARS else text


def ask_answer_llm(goal, result):
    try:
        from core.llm import query_ollama
        prompt = load_prompt("headless_answer.md", goal=goal, title=result.get("title") or "",
                             url=result.get("url") or "",
                             text=focus_text(result.get("text") or "", goal,
                                             urlsplit(result.get("url") or "").hostname or "")[:ANSWER_CHARS])
        return query_ollama([{"role": "user", "content": prompt}], temperature=0.3,
                            timeout=max(settings.TIMEOUT_LLM, 60))
    except Exception as e:
        log.warning(f"[HEADLESS] Modelo não respondeu: {e}")
        return None


def price_list(text, goal, site_host=""):
    """Pergunta de preço → [(produto, preço)] por regra, sem modelo: linha que cita o objetivo
    seguida (até FOCUS_AFTER linhas) de linhas que são só preço. Dois preços seguidos = o 1º é
    o antigo (riscado): vale o último. Ordem: o termo mais cedo no nome primeiro ("Placa de
    Vídeo RTX 5060…" antes de "Notebook…, SSD 512GB, RTX 5060"), depois a ordem da página.
    Vazio se a pergunta não é de preço ou nada casa."""
    if not _PRICE_GOAL_RE.search(goal or ""):
        return []
    terms = _terms(goal, site_host)
    if not terms:
        return []
    need = min(2, len(terms))
    lines = (text or "").splitlines()
    found, seen = [], set()
    for i, line in enumerate(lines):
        low = line.lower()
        if _PRICE_LINE_RE.match(line) or sum(1 for t in terms if t in low) < need:
            continue
        prices = []
        for nxt in lines[i + 1:i + 1 + FOCUS_AFTER]:
            if _PRICE_LINE_RE.match(nxt):
                prices.append(nxt.strip())
            elif prices or sum(1 for t in terms if t in nxt.lower()) >= need:
                break
        name = " ".join(line.split())
        if prices and name not in seen:
            seen.add(name)
            pos = min(name.lower().find(t) for t in terms if t in name.lower())
            found.append((pos // NAME_BUCKET, len(found), name, prices[-1]))   # faixas: empate = ordem da página
    found.sort(key=lambda item: (item[0], item[1]))
    return [(name if len(name) <= NAME_MAX else name[:NAME_MAX - 1].rstrip() + "…", price)
            for _pos, _order, name, price in found[:PRICE_ITEMS]]


def report(goal, result, ask_llm=ask_answer_llm):
    """Texto do aviso final (Markdown)."""
    if not result.get("ok"):
        return f"A tarefa em segundo plano (**{goal}**) parou no passo {result.get('done', 0) + 1}, Senhor: {result.get('error')}."
    if not (result.get("text") or "").strip():
        return f"Tarefa concluída (**{goal}**), mas a página não tinha texto legível, Senhor.\n\nPágina: {result.get('url')}"
    prices = price_list(result.get("text") or "", goal, urlsplit(result.get("url") or "").hostname or "")
    if prices:   # preço vem por regra: o modelo pequeno troca produto e preço antigo pelo atual
        answer = "\n".join([f"Encontrei {len(prices)} na página, Senhor:", ""]
                           + [f"- {name} — **{price}**" for name, price in prices])
    else:
        answer = (ask_llm(goal, result) if ask_llm else None) or "Não consegui resumir a página agora, Senhor."
    return f"**Tarefa em segundo plano concluída** — {goal}\n\n{answer.strip()}\n\nPágina: {result.get('url')}"


def _start(goal, steps, runner=None, answer_llm=ask_answer_llm, background=_run_background):
    def job():
        result = (runner or headless.run_task)(steps)
        _announce(report(goal, result, answer_llm))

    background(job)
    return f"Executando em segundo plano: {_flow(steps)}. Aviso quando terminar, Senhor."


def _flow(steps):
    return " → ".join(headless.describe(s) for s in steps)


# ------------------------------------------------------------------ entrada
def request(request_text, owner=None, plan_llm=ask_plan_llm, runner=None, answer_llm=ask_answer_llm,
            background=_run_background):
    """Planeja e dispara (ou pede confirmação). Devolve o texto para o usuário. Nunca levanta."""
    try:
        if runner is None:
            ok, why = headless.available()
            if not ok:
                return f"A navegação em segundo plano precisa do Microsoft Edge e do Playwright, Senhor — {why}."
            if headless.busy():
                return "Já há uma tarefa em segundo plano rodando, Senhor. Aguarde ela terminar."
        goal, steps, error = plan(request_text, plan_llm)
        if not steps:
            return f"Não montei essa tarefa, Senhor: {error}. Diga o site e o que trazer de lá."
        risky = headless.risky_steps(steps)
        if not risky:
            return _start(goal, steps, runner, answer_llm, background)
        lines = [f"Tarefa em segundo plano: **{goal}**", ""]
        for i, step in enumerate(steps):
            mark = " ⚠️ **envia algo**" if i in risky else ""
            lines.append(f"{i + 1}. {headless.describe(step)}{mark}")
        lines += ["", "Executo? (**sim** / **não**)"]
        question = "\n".join(lines)
        armed = pending.arm("HEADLESS_TASK", question,
                            lambda: _start(goal, steps, runner, answer_llm, background),
                            target=goal, on_decline=lambda: "Nada enviado, Senhor.",
                            timeout_s=CONFIRM_TIMEOUT_S, owner=owner)
        return question if armed else pending.BUSY_REPLY
    except Exception as e:
        log.error(f"[HEADLESS] Falha ao preparar a tarefa: {e}")
        return "Não consegui preparar essa tarefa agora, Senhor."
