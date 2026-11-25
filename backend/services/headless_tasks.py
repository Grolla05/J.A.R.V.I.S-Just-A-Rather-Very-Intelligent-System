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

from core import headless, pending
from core.browser import is_fetch_safe
from core.config import settings
from core.logger import log
from core.prompts import load_prompt

CONFIRM_TIMEOUT_S = 60
ANSWER_CHARS = 6000
_URL_RE = re.compile(r"https?://[^\s<>\"']+")


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
    goal = " ".join(str((data or {}).get("objetivo") or "").split())[:200] or request_text[:200]
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


# ------------------------------------------------------------------ resposta
def ask_answer_llm(goal, result):
    try:
        from core.llm import query_ollama
        prompt = load_prompt("headless_answer.md", goal=goal, title=result.get("title") or "",
                             url=result.get("url") or "", text=(result.get("text") or "")[:ANSWER_CHARS])
        return query_ollama([{"role": "user", "content": prompt}], temperature=0.3,
                            timeout=max(settings.TIMEOUT_LLM, 60))
    except Exception as e:
        log.warning(f"[HEADLESS] Modelo não respondeu: {e}")
        return None


def report(goal, result, ask_llm=ask_answer_llm):
    """Texto do aviso final (Markdown)."""
    if not result.get("ok"):
        return f"A tarefa em segundo plano (**{goal}**) parou no passo {result.get('done', 0) + 1}, Senhor: {result.get('error')}."
    if not (result.get("text") or "").strip():
        return f"Tarefa concluída (**{goal}**), mas a página não tinha texto legível, Senhor.\n\nPágina: {result.get('url')}"
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
