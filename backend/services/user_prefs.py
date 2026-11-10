"""Preferências ajustáveis pela TUI (/config), persistidas na tabela `config`.

Cada preferência tem um padrão vindo do `.env` (via `settings`) ou fixo, e uma
lista de opções que o menu percorre com ◀ ▶. `get()` sempre devolve um valor
válido: se o banco tiver lixo, cai no padrão.
"""
from core import log, settings
from core.database import db

# Vozes neurais pt-BR do edge-tts
VOICES = ("pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaNeural")

_ONOFF = (False, True)  # ◀ desliga · ▶ liga


def _onoff_label(value):
    return "ligado" if value else "desligado"


# Aviso de saída (clima + trânsito + 1º compromisso): minutos desde 00:00; 0 = desligado
COMMUTE_TIMES = (0, 360, 390, 420, 450, 480, 510, 540, 570)


def _time_label(minutes):
    return "desligado" if not minutes else f"{minutes // 60:02d}:{minutes % 60:02d}"


# chave -> (rótulo, opções, padrão, formatação p/ exibir)
PREFS = {
    "tts_voice": ("Voz", VOICES, VOICES[0], lambda v: v.replace("pt-BR-", "").replace("Neural", "")),
    "tts_rate": ("Velocidade", (-20, -10, 0, 10, 20, 30), 10, lambda v: f"{v:+d}%"),
    "tts_volume": ("Volume", (20, 40, 60, 80, 100), 100, lambda v: f"{v}%"),
    "mic_threshold": ("Sensibilidade do mic", (0, 150, 300, 450, 600, 900, 1200),
                      None, lambda v: "automática" if v <= 0 else f"limiar {v}"),
    "attention_window": ("Janela de atenção", (15, 30, 60, 90, 120), 60, lambda v: f"{v} s"),
    "briefing_auto": ("Briefing no 1º boot do dia", _ONOFF, True, _onoff_label),
    "briefing_news": ("Manchetes no briefing", _ONOFF, False, _onoff_label),
    "clipboard_monitor": ("Monitor de clipboard", _ONOFF, False, _onoff_label),
    "commute_alert": ("Aviso de saída", COMMUTE_TIMES, 0, _time_label),
    "dnd_auto_meeting": ("Silenciar em reunião", _ONOFF, True, _onoff_label),
    "dnd_auto_fullscreen": ("Silenciar em tela cheia", _ONOFF, True, _onoff_label),
}

# Grupos do menu lateral (estilo RPG) -> chaves editáveis
GROUPS = {
    "VOZ": ("tts_voice", "tts_rate", "tts_volume"),
    "MICROFONE": ("mic_threshold", "attention_window"),
    "ROTINAS": ("briefing_auto", "briefing_news", "clipboard_monitor", "commute_alert",
                "dnd_auto_meeting", "dnd_auto_fullscreen"),
}


def _default(key):
    _label, options, default, _fmt = PREFS[key]
    if key == "mic_threshold":
        default = int(settings.MIC_ENERGY_THRESHOLD or 0)
    return default


def _db_key(key):
    return f"pref_{key}"


def get(key):
    """Valor atual da preferência (banco → padrão)."""
    options = PREFS[key][1]
    try:
        value = db.get_config(_db_key(key))
    except Exception as e:
        log.debug(f"Preferência '{key}' indisponível no banco: {e}")
        value = None
    if value in options:
        return value
    if key == "mic_threshold" and isinstance(value, int) and value >= 0:
        return value  # limiar vindo do .env pode não estar na lista
    return _default(key)


def set(key, value):  # noqa: A001 — API curta e explícita: user_prefs.set(...)
    if value not in PREFS[key][1]:
        raise ValueError(f"Valor inválido para {key}: {value!r}")
    db.save_config(_db_key(key), value)
    return value


def step(key, direction):
    """Anda uma opção para a direita (+1) ou esquerda (-1), sem dar a volta."""
    options = PREFS[key][1]
    current = get(key)
    index = options.index(current) if current in options else 0
    index = max(0, min(len(options) - 1, index + direction))
    return set(key, options[index])


def label(key):
    return PREFS[key][0]


def display(key, value=None):
    return PREFS[key][3](get(key) if value is None else value)


def level(key):
    """Posição 0..1 da opção atual (barra de blocos do menu)."""
    options = PREFS[key][1]
    current = get(key)
    if current not in options or len(options) < 2:
        return 0.0
    return options.index(current) / (len(options) - 1)
