"""Saúde dos subsistemas (Ollama, Obsidian, microfone, SQLite).

Checagens rápidas e sem efeito colateral, usadas pelo boot (`core/boot.py`) e
pela linha de status da TUI (polling a cada HEALTH_INTERVAL). Cada uma retorna
`(status, detalhe)` com status ∈ ok | warn | fail. Nada aqui abre o microfone
nem aquece o modelo: isso continua sendo papel do boot.
"""
import sqlite3
import threading
import time

from .config import settings
from .logger import log

OK, WARN, FAIL = "ok", "warn", "fail"
OBSIDIAN_SLOW_MS = 500

# Glifo por status: a forma muda junto com a cor, então dá pra ler até com NO_COLOR.
GLYPHS = {OK: "●", WARN: "◐", FAIL: "○"}

# PortAudio (Pa_Initialize/Pa_Terminate) não é thread-safe: o boot e o poll de
# saúde enumerando o microfone ao mesmo tempo derrubavam o processo com
# 0xC0000005. A enumeração roda uma vez só, sob lock, e o resultado fica em cache
# (reabrir o PyAudio a cada poll também podia atrapalhar o stream do Copilot).
_AUDIO_LOCK = threading.Lock()
_mic_cache = None


def check_ollama():
    from .ollama_server import is_ollama_running
    if is_ollama_running():
        return OK, f"servidor no ar · {settings.OLLAMA_MODEL}"
    return FAIL, "servidor offline · chat indisponível"


def check_obsidian():
    from .obsidian import obsidian
    start = time.monotonic()
    items = obsidian.list_dir("")
    ms = (time.monotonic() - start) * 1000
    if items is None:
        return WARN, "vault inacessível · RAG desligado"
    if ms > OBSIDIAN_SLOW_MS:
        return WARN, f"vault lento ({ms:.0f} ms) · {len(items)} itens na raiz"
    return OK, f"vault em {ms:.0f} ms · {len(items)} itens na raiz"


def check_database():
    conn = None
    try:
        conn = sqlite3.connect(settings.DB_PATH, timeout=2)
        conn.execute("SELECT 1").fetchone()
        return OK, f"{settings.DB_PATH.name} respondendo"
    except sqlite3.Error as e:
        return FAIL, f"SQLite indisponível ({type(e).__name__})"
    finally:
        if conn is not None:
            conn.close()


def check_microphone(refresh=False):
    global _mic_cache
    with _AUDIO_LOCK:
        if _mic_cache is None or refresh:
            _mic_cache = _probe_microphone()
        return _mic_cache


def _probe_microphone():
    try:
        import speech_recognition as sr
        names = sr.Microphone.list_microphone_names()  # não abre o dispositivo
    except Exception as e:
        return WARN, f"áudio indisponível ({type(e).__name__}) · voz fica off"
    index = settings.MIC_INDEX
    if index is None or not (0 <= int(index) < len(names)):
        return FAIL, f"microfone {index} ausente · voz fica off"
    return OK, f"mic {index}: {names[int(index)][:40]}"


# Rótulo curto (linha de status) -> (nome longo, checagem). Ordem = ordem na tela.
CHECKS = {
    "OLL": ("Ollama", check_ollama),
    "OBS": ("Obsidian", check_obsidian),
    "MIC": ("Microfone", check_microphone),
    "DB": ("SQLite", check_database),
}


def safe(check):
    """Roda uma checagem; exceção vira fail (uma peça quebrada não derruba as outras)."""
    try:
        return check()
    except Exception as e:
        log.debug(f"Health: checagem falhou: {e}")
        return FAIL, str(e)[:60] or type(e).__name__


def run_all(checks=None):
    """{"OLL": (status, detalhe), ...} na ordem de CHECKS."""
    return {key: safe(fn) for key, (_name, fn) in (checks or CHECKS).items()}


def status_line(result):
    """'OLL● OBS◐ MIC○ DB●' para a linha de status ('' sem resultado ainda)."""
    return " ".join(f"{key}{GLYPHS.get(status, GLYPHS[FAIL])}" for key, (status, _d) in result.items())


def newly_failed(before, after):
    """Rótulos que tinham leitura sem falha e agora falharam (a 1ª leitura não
    avisa: o boot já mostrou o que estava fora)."""
    return [key for key, (status, _d) in after.items()
            if status == FAIL and key in before and before[key][0] != FAIL]
