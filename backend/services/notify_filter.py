"""Filtro inteligente de interrupções — decide se um alerta fala agora, espera ou some.

Prioridade do alerta (`priority`):
- critical: disco CRÍTICO, bateria crítica, GPU superaquecendo (risco real)
- high:     disco com pouco espaço
- normal:   CPU/RAM altas e o resto (os alertas "barulhentos")

Contexto (`context`): Não Perturbe manual (`state.dnd_active`), reunião agora na
agenda (`google_calendar.is_busy`, pref `dnd_auto_meeting`) e app em tela cheia
(`window_utils.is_foreground_fullscreen`, pref `dnd_auto_fullscreen`).

Regra (`decide`): critical sempre passa; com qualquer silêncio ativo, high/normal
vão para o backlog (`services.focus.remember_alert`) e são resumidos quando o
silêncio acaba — pelo `FocusManager` (DND manual) ou por `poll_auto_quiet()`
(reunião/tela cheia, chamado no tick da telemetria da TUI).
"""
import re

import core.state as state
from core.logger import log

CRITICAL, HIGH, NORMAL = "critical", "high", "normal"
DELIVER, DEFER = "deliver", "defer"
_RANK = {NORMAL: 0, HIGH: 1, CRITICAL: 2}

_CRITICAL_RE = re.compile(r"disco \S+ cr[ií]tico|bateria cr[ií]tica|superaquec", re.I)
_HIGH_RE = re.compile(r"pouco espa[cç]o", re.I)

REASONS = {"dnd": "DND", "meeting": "REUNIÃO", "fullscreen": "TELA CHEIA"}


def priority(message):
    text = str(message or "")
    if _CRITICAL_RE.search(text):
        return CRITICAL
    if _HIGH_RE.search(text):
        return HIGH
    return NORMAL


def _pref(key):
    try:
        from services import user_prefs
        return user_prefs.get(key)
    except Exception as e:
        log.debug(f"Filtro: preferência '{key}' indisponível: {e}")
        return False


def _in_meeting():
    try:
        from core import google_calendar
        return google_calendar.is_busy()
    except Exception as e:
        log.debug(f"Filtro: agenda indisponível: {e}")
        return False


def _fullscreen():
    try:
        from core.window_utils import is_foreground_fullscreen
        return is_foreground_fullscreen()
    except Exception as e:
        log.debug(f"Filtro: detecção de tela cheia falhou: {e}")
        return False


def context(meeting_fn=_in_meeting, fullscreen_fn=_fullscreen, pref=_pref):
    """{'dnd', 'meeting', 'fullscreen'} — cada sinal só conta com a pref ligada."""
    return {
        "dnd": bool(state.dnd_active),
        "meeting": bool(pref("dnd_auto_meeting") and meeting_fn()),
        "fullscreen": bool(pref("dnd_auto_fullscreen") and fullscreen_fn()),
    }


def quiet_reason(ctx):
    """'DND' | 'REUNIÃO' | 'TELA CHEIA' | None — o primeiro silêncio ativo."""
    return next((REASONS[k] for k in ("dnd", "meeting", "fullscreen") if ctx.get(k)), None)


def decide(prio, ctx):
    if prio == CRITICAL or not quiet_reason(ctx):
        return DELIVER
    return DEFER


def evaluate(message, ctx=None):
    """(veredito, prioridade, motivo) para um alerta proativo."""
    ctx = context() if ctx is None else ctx
    prio = priority(message)
    return decide(prio, ctx), prio, quiet_reason(ctx)


def poll_auto_quiet(ctx=None):
    """Atualiza `state.auto_quiet` (reunião/tela cheia). Quando o silêncio automático
    acaba (e o DND manual não está ligado), devolve o resumo dos alertas guardados."""
    ctx = context() if ctx is None else ctx
    auto = None if ctx["dnd"] else quiet_reason({**ctx, "dnd": False})
    was = state.auto_quiet
    state.auto_quiet = auto
    if was and not auto and not state.dnd_active:
        from services.focus import backlog_summary
        summary = backlog_summary(state.dnd_backlog).replace("Durante o Não Perturbe",
                                                             f"Durante o modo {was.lower()}")
        state.dnd_backlog.clear()
        return summary
    return ""


def badge():
    """Selo da linha de status para o silêncio automático ('☾ REUNIÃO')."""
    return f"☾ {state.auto_quiet}" if state.auto_quiet else ""
