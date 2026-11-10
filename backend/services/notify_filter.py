"""Filtro inteligente de interrupções — decide se um alerta fala agora, espera ou some.

Prioridade do alerta (`priority`):
- critical: disco CRÍTICO, bateria crítica, GPU superaquecendo (risco real)
- high:     disco com pouco espaço
- normal:   CPU/RAM altas e o resto (os alertas "barulhentos")

Contexto (`context`): Modo Apresentação (manual `state.presentation_active` ou
PowerPoint/PDF em tela cheia com a pref `presentation_auto`), Não Perturbe manual
(`state.dnd_active`), reunião agora na agenda (`google_calendar.is_busy`, pref
`dnd_auto_meeting`) e app em tela cheia (`window_utils.is_foreground_fullscreen`,
pref `dnd_auto_fullscreen`).

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

REASONS = {"presentation": "SILENT", "dnd": "DND", "meeting": "REUNIÃO", "fullscreen": "TELA CHEIA"}
_ORDER = ("presentation", "dnd", "meeting", "fullscreen")


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


def _presenting():
    try:
        from core.window_utils import is_presenting
        return is_presenting()
    except Exception as e:
        log.debug(f"Filtro: detecção de apresentação falhou: {e}")
        return False


def context(meeting_fn=_in_meeting, fullscreen_fn=_fullscreen, pref=_pref, presenting_fn=_presenting):
    """{'presentation', 'dnd', 'meeting', 'fullscreen'} — sinais automáticos só contam com a pref ligada.
    'presentation' aqui é só o automático; o manual entra em `quiet_reason`."""
    return {
        "presentation": bool(pref("presentation_auto") and presenting_fn()),
        "dnd": bool(state.dnd_active),
        "meeting": bool(pref("dnd_auto_meeting") and meeting_fn()),
        "fullscreen": bool(pref("dnd_auto_fullscreen") and fullscreen_fn()),
    }


def quiet_reason(ctx):
    """'SILENT' | 'DND' | 'REUNIÃO' | 'TELA CHEIA' | None — o primeiro silêncio ativo."""
    if state.presentation_active:
        return REASONS["presentation"]
    return next((REASONS[k] for k in _ORDER if ctx.get(k)), None)


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
    acaba (e nem o DND nem o modo apresentação manual estão ligados), devolve o
    resumo dos alertas guardados."""
    ctx = context() if ctx is None else ctx
    manual = ctx["dnd"] or state.presentation_active
    auto = None if manual else next((REASONS[k] for k in _ORDER if k != "dnd" and ctx.get(k)), None)
    was = state.auto_quiet
    state.auto_quiet = auto
    if was and not auto and not manual:
        from services.focus import backlog_summary
        label = "a apresentação" if was == REASONS["presentation"] else f"o modo {was.lower()}"
        summary = backlog_summary(state.dnd_backlog).replace("Durante o Não Perturbe", f"Durante {label}")
        state.dnd_backlog.clear()
        return summary
    return ""


def badge():
    """Selo da linha de status: '[SILENT]' (apresentação) ou silêncio automático ('☾ REUNIÃO')."""
    if state.presentation_active or state.auto_quiet == REASONS["presentation"]:
        return "[SILENT]"
    return f"☾ {state.auto_quiet}" if state.auto_quiet else ""
