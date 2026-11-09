"""Pomodoro + Não Perturbe (DND).

As ações (start/stop/skip/dnd_on/dnd_off) só devolvem o texto de confirmação —
quem chama mostra/fala. Só o que acontece sozinho (troca de fase, fim do DND
com prazo) é anunciado daqui.

Pomodoro: foco → pausa curta → foco … → pausa longa depois de N focos (padrão
25/5, 4 ciclos + 15; ver POMODORO_* no .env). As fases de foco ligam o Não
Perturbe; as pausas desligam. Cada troca de fase é anunciada (texto na TUI e
fala, se a voz estiver ligada) — esses avisos passam mesmo com o DND ligado.

Não Perturbe: silencia os toasts de todos os apps do Windows
(core.notifications) e os alertas proativos do JARVIS (core.alerts guarda no
`state.dnd_backlog`). Ao desligar, o valor anterior dos toasts volta e os
alertas guardados são resumidos. O valor anterior também fica no banco
(`dnd_restore`): se o app cair com o DND ligado, o próximo boot restaura.

Sem I/O no import: o banco e a fala só são tocados quando algo é ligado.
"""
import math
import threading
import time

import core.state as state
from core.config import settings
from core.logger import log

IDLE, FOCUS, SHORT_BREAK, LONG_BREAK = "idle", "focus", "short_break", "long_break"
RESTORE_KEY = "dnd_restore"
BACKLOG_MAX = 20
SUMMARY_ITEMS = 3


def _timer(seconds, fn):
    t = threading.Timer(seconds, fn)
    t.daemon = True
    t.start()
    return t


def _announce(text):
    # Import tardio: sem mic/pygame/pyttsx3 no boot. Ouvido pausado enquanto
    # fala, para o JARVIS não ouvir a si mesmo (mesmo padrão de core/alerts.py).
    from services.listen import ear_pause, ear_resume
    from services.speak import speak
    ear_pause()
    try:
        speak(text)
    finally:
        ear_resume()


class _DbStore:
    """config do SQLite com import tardio ('' = chave apagada)."""

    def get(self, key):
        from core.database import db
        return db.get_config(key)

    def set(self, key, value):
        from core.database import db
        db.save_config(key, value)


class _Toasts:
    def get(self):
        from core.notifications import get_toasts_enabled
        return get_toasts_enabled()

    def set(self, enabled):
        from core.notifications import set_toasts_enabled
        return set_toasts_enabled(enabled)


def remember_alert(message):
    """Guarda um alerta proativo enquanto o DND está ligado (chamado por core.alerts)."""
    clean = " ".join(str(message).replace("*", "").split())[:160]
    state.dnd_backlog.append(clean)
    del state.dnd_backlog[:-BACKLOG_MAX]


def backlog_summary(items):
    """'Durante o Não Perturbe: 3 alertas. Último: …' ('' sem alertas)."""
    if not items:
        return ""
    count = len(items)
    noun = "alerta" if count == 1 else "alertas"
    recent = "; ".join(items[-SUMMARY_ITEMS:])
    return f"Durante o Não Perturbe chegaram {count} {noun} do sistema: {recent}"


class FocusManager:
    def __init__(self, clock=time.monotonic, timer_factory=_timer, toasts=None, store=None, announce=None):
        self._clock = clock
        self._timer_factory = timer_factory
        self._toasts = toasts if toasts is not None else _Toasts()
        self._store = store if store is not None else _DbStore()
        self._announce = announce or _announce
        self._lock = threading.RLock()
        self._timer = None
        self._dnd_timer = None
        self.phase = IDLE
        self.ends_at = 0.0
        self.cycle = 0
        self.cycles = settings.POMODORO_CYCLES
        self.focus_min = settings.POMODORO_FOCUS_MIN
        self.dnd_ends_at = None  # DND manual com prazo

    # ------------------------------------------------------------- pomodoro
    def start(self, focus_min=None, cycles=None):
        with self._lock:
            self._cancel(self._timer)
            self.focus_min = max(1, int(focus_min or settings.POMODORO_FOCUS_MIN))
            self.cycles = max(1, int(cycles or settings.POMODORO_CYCLES))
            self.cycle = 1
            self._enter(FOCUS)
        return (f"Pomodoro iniciado: {self.focus_min} minutos de foco, foco 1 de {self.cycles}. "
                "Notificações silenciadas, Senhor.")

    def stop(self):
        """Encerra Pomodoro e DND manual; devolve o texto de confirmação."""
        with self._lock:
            was_running = self.phase != IDLE
            self._cancel(self._timer)
            self._cancel(self._dnd_timer)
            self._timer = self._dnd_timer = None
            self.phase, self.cycle, self.dnd_ends_at = IDLE, 0, None
            summary = self._set_dnd(False)
        text = "Foco encerrado, Senhor." if was_running else "Nenhum foco em andamento."
        return text + (f" {summary}" if summary else "")

    def skip(self):
        """Pula para a próxima fase."""
        with self._lock:
            if self.phase == IDLE:
                return False
            self._cancel(self._timer)
        self._phase_done()
        return True

    def _enter(self, phase):
        minutes = {FOCUS: self.focus_min,
                   SHORT_BREAK: settings.POMODORO_SHORT_BREAK_MIN,
                   LONG_BREAK: settings.POMODORO_LONG_BREAK_MIN}[phase]
        self.phase = phase
        self.ends_at = self._clock() + minutes * 60
        self._timer = self._timer_factory(minutes * 60, self._phase_done)
        return self._set_dnd(phase == FOCUS)

    def _phase_done(self):
        with self._lock:
            phase = self.phase
            if phase == FOCUS:
                if self.cycle >= self.cycles:
                    summary = self._enter(LONG_BREAK)
                    text = f"Ciclo completo, Senhor. Pausa longa de {settings.POMODORO_LONG_BREAK_MIN} minutos."
                else:
                    summary = self._enter(SHORT_BREAK)
                    text = f"Foco {self.cycle} de {self.cycles} concluído. Pausa de {settings.POMODORO_SHORT_BREAK_MIN} minutos."
            elif phase == SHORT_BREAK:
                self.cycle += 1
                summary = self._enter(FOCUS)
                text = f"Fim da pausa. Foco {self.cycle} de {self.cycles}: {self.focus_min} minutos."
            elif phase == LONG_BREAK:
                self.phase, self.cycle, self._timer = IDLE, 0, None
                summary, text = "", "Pomodoro concluído. Bom trabalho, Senhor."
            else:
                return
        self._say(text + (f" {summary}" if summary else ""))

    # ------------------------------------------------------------------ DND
    def dnd_on(self, minutes=None):
        """Não Perturbe manual (sem Pomodoro). minutes=None = até desligar."""
        with self._lock:
            self._cancel(self._dnd_timer)
            self._dnd_timer = None
            self.dnd_ends_at = None
            if minutes:
                self.dnd_ends_at = self._clock() + int(minutes) * 60
                self._dnd_timer = self._timer_factory(int(minutes) * 60, self._dnd_expired)
            self._set_dnd(True)
        prazo = f" por {int(minutes)} minutos" if minutes else ""
        return f"Não Perturbe ativado{prazo}. Notificações e alertas silenciados."

    def dnd_off(self):
        with self._lock:
            self._cancel(self._dnd_timer)
            self._dnd_timer, self.dnd_ends_at = None, None
            summary = self._set_dnd(False)
        return "Não Perturbe desativado." + (f" {summary}" if summary else "")

    def _dnd_expired(self):
        with self._lock:
            if self.phase == FOCUS:  # o Pomodoro assumiu o DND
                self._dnd_timer = self.dnd_ends_at = None
                return
        self._say(self.dnd_off())

    def _set_dnd(self, on):
        """Liga/desliga o DND guardando o valor anterior dos toasts. Retorna o
        resumo dos alertas guardados quando desliga ('' se nada mudou)."""
        if on == state.dnd_active:
            return ""
        if on:
            previous = self._toasts.get()
            self._store.set(RESTORE_KEY, "1" if previous in (True, None) else "0")
            self._toasts.set(False)
            state.dnd_backlog.clear()
            state.dnd_active = True
            log.info("🔕 Não Perturbe ligado.")
            return ""
        state.dnd_active = False
        self._restore_toasts()
        summary = backlog_summary(state.dnd_backlog)
        state.dnd_backlog.clear()
        log.info("🔔 Não Perturbe desligado.")
        return summary

    def _restore_toasts(self):
        saved = self._store.get(RESTORE_KEY)
        if saved in ("", None):
            return False
        self._toasts.set(str(saved) == "1")
        self._store.set(RESTORE_KEY, "")
        return True

    def restore_after_crash(self):
        """No boot: o app caiu com o DND ligado? Devolve os toasts como estavam."""
        with self._lock:
            if state.dnd_active:
                return False
            restored = self._restore_toasts()
        if restored:
            log.info("🔔 Notificações restauradas (o JARVIS fechou com o Não Perturbe ligado).")
        return restored

    # --------------------------------------------------------------- leitura
    def _left_min(self, ends_at):
        return max(0, math.ceil((ends_at - self._clock()) / 60))

    def status(self):
        with self._lock:
            return {
                "phase": self.phase,
                "remaining_min": self._left_min(self.ends_at) if self.phase != IDLE else 0,
                "cycle": self.cycle,
                "cycles": self.cycles,
                "dnd": state.dnd_active,
                "dnd_remaining_min": self._left_min(self.dnd_ends_at) if self.dnd_ends_at else None,
            }

    def badge(self):
        """Selo da linha de status: '◷ FOCO 24m 1/4', '☕ PAUSA 4m', '☾ DND 30m' ou ''."""
        st = self.status()
        if st["phase"] == FOCUS:
            return f"◷ FOCO {st['remaining_min']}m {st['cycle']}/{st['cycles']}"
        if st["phase"] in (SHORT_BREAK, LONG_BREAK):
            return f"☕ PAUSA {st['remaining_min']}m"
        if st["dnd"]:
            left = st["dnd_remaining_min"]
            return f"☾ DND {left}m" if left else "☾ DND"
        return ""

    def describe(self):
        """Resposta falada/escrita para 'quanto falta?'."""
        st = self.status()
        if st["phase"] == FOCUS:
            return f"Foco {st['cycle']} de {st['cycles']}: faltam {st['remaining_min']} minutos."
        if st["phase"] in (SHORT_BREAK, LONG_BREAK):
            return f"Pausa: faltam {st['remaining_min']} minutos."
        if st["dnd"]:
            left = st["dnd_remaining_min"]
            return f"Não Perturbe ligado{f', faltam {left} minutos' if left else ''}."
        return "Nenhum foco em andamento."

    def apply(self, action, minutes=None):
        """Despacha uma ação (skill FOCUS_MODE, /focus, /dnd, palette) e devolve o texto."""
        if action == "start":
            return self.start(focus_min=minutes)
        if action == "stop":
            return self.stop()
        if action == "skip":
            return "Fase pulada." if self.skip() else "Não há foco em andamento para pular."
        if action == "status":
            return self.describe()
        if action == "dnd_on":
            return self.dnd_on(minutes)
        if action == "dnd_off":
            return self.dnd_off()
        if action == "dnd_toggle":
            return self.dnd_off() if state.dnd_active else self.dnd_on(minutes)
        return "Não entendi o que fazer com o foco."

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _cancel(timer):
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

    def _say(self, text):
        try:
            self._announce(text)
        except Exception as e:
            log.debug(f"Foco: anúncio falhou: {e}")


focus = FocusManager()
