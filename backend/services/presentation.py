"""Modo Apresentação — silêncio total enquanto você apresenta.

Dois gatilhos:
- manual: `/silent`, skill PRESENTATION_MODE ("modo apresentação") → `state.presentation_active`;
- automático: PowerPoint/leitor de PDF em tela cheia (`window_utils.is_presenting`, pref
  `presentation_auto`) → o filtro de notificações põe `state.auto_quiet = "SILENT"`.

Com qualquer um ligado (`is_silent()`): alertas não-críticos vão para o backlog
(services/notify_filter.py), o TTS não fala nem com `force=True` (services/speak.py),
o ouvido não abre o microfone (services/listen.py) e a linha de status mostra `[SILENT]`.
Ao sair, os alertas guardados viram um resumo.
"""
import core.state as state

SILENT = "SILENT"


def is_silent():
    return bool(state.presentation_active or state.auto_quiet == SILENT)


def set_manual(on):
    """Liga/desliga o modo manual e devolve a fala do JARVIS (com o resumo ao desligar)."""
    if on:
        if state.presentation_active:
            return "O modo apresentação já está ligado, Senhor. Palco é seu."
        state.presentation_active = True
        return ("Modo apresentação ligado: microfone fechado, voz muda e alertas guardados. "
                "Só os críticos passam. Boa apresentação, Senhor.")
    if not state.presentation_active:
        return "O modo apresentação já está desligado, Senhor."
    state.presentation_active = False
    summary = ""
    if not (state.dnd_active or state.auto_quiet):
        from services.focus import backlog_summary
        summary = backlog_summary(state.dnd_backlog).replace("Durante o Não Perturbe",
                                                             "Durante a apresentação")
        state.dnd_backlog.clear()
    return ("Modo apresentação desligado. Voltei a ouvir, Senhor." + (f" {summary}" if summary else ""))


def toggle():
    return set_manual(not state.presentation_active)


def status():
    if state.presentation_active:
        return "Modo apresentação ligado (manual)."
    if state.auto_quiet == SILENT:
        return "Modo apresentação ligado: detectei uma apresentação em tela cheia."
    return "Modo apresentação desligado."
