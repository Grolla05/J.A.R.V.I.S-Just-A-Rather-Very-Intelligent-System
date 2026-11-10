import asyncio
import os
import re
import threading
import uuid

import core.state as state
from core import log, settings

# --- CONFIGURAÇÕES ---
VOICE_ONLINE = "pt-BR-AntonioNeural"

# --- SINALIZADOR DE ÁUDIO ---
# Esse cadeado impede que duas threads falem ao mesmo tempo
speech_lock = threading.Lock()

# Motores de áudio são inicializados sob demanda: pyttsx3/pygame custam RAM e
# tempo de boot, e na TUI a voz começa desligada.
_engine_offline = None
_mixer_ready = False


def _get_offline_engine():
    global _engine_offline
    if _engine_offline is None:
        import pyttsx3
        _engine_offline = pyttsx3.init()
        _engine_offline.setProperty('rate', settings.SPEECH_RATE)
    return _engine_offline


def _ensure_mixer():
    global _mixer_ready
    if not _mixer_ready:
        import pygame
        try:
            pygame.mixer.init()
            _mixer_ready = True
        except Exception:
            log.critical("Erro ao iniciar sistema de áudio.")
    return _mixer_ready


def _show(text):
    """Exibe a fala na interface (TUI) em vez de escrever direto no stdout,
    que corromperia a tela do terminal."""
    if callable(state.announce):
        try:
            state.announce(text)
            return
        except Exception as e:
            log.debug(f"announce falhou: {e}")
    log.info(f"[J.A.R.V.I.S]: {text}")


def _treat_text(text):
    SLANG_MAP = {
        r"\bvc\b": "você",
        r"\btmj\b": "tamo junto",
        r"\bpq\b": "porque",
        r"\badd\b": "adicionar",
        r"\bmsg\b": "mensagem",
        r"\bobs\b": "observação",
    }
    text = re.sub(r'[^\w\s,.?!áéíóúàãõâêôçÁÉÍÓÚÀÃÕÂÊÔÇ]', '', text)
    for slang, expansion in SLANG_MAP.items():
        text = re.sub(slang, expansion, text, flags=re.IGNORECASE)
    return text.strip()

def _voice_prefs():
    """Voz, velocidade (+N%) e volume (0..1) escolhidos no /config da TUI."""
    try:
        from services import user_prefs
        return (user_prefs.get("tts_voice"), f"{user_prefs.get('tts_rate'):+d}%",
                user_prefs.get("tts_volume") / 100)
    except Exception as e:
        log.debug(f"Preferências de voz indisponíveis: {e}")
        return VOICE_ONLINE, "+10%", 1.0


async def _generate_audio_online(text, file_path):
    import edge_tts
    clean_text = _treat_text(text)
    voice, rate, _volume = _voice_prefs()
    communicate = edge_tts.Communicate(clean_text, voice, rate=rate)
    await communicate.save(file_path)

def speak_online(text, on_play=None):
    filename_path = settings.DIR_SOUNDS / f"audio_{uuid.uuid4().hex}.mp3"
    filename_str = str(filename_path)

    try:
        if not _ensure_mixer():
            raise Exception("Mixer de áudio indisponível.")
        import pygame

        # 1. Gera o arquivo de áudio
        asyncio.run(_generate_audio_online(text, filename_str))

        # 2. Se o arquivo não existe ou é vazio (0 bytes), força erro para ir pro offline
        if not os.path.exists(filename_str) or os.path.getsize(filename_str) < 100:
            raise Exception("Arquivo de áudio gerado vazio ou corrompido.")

        # 3. Toca o áudio
        pygame.mixer.music.load(filename_str)
        pygame.mixer.music.set_volume(_voice_prefs()[2])

        if on_play:
            on_play()

        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        pygame.mixer.music.unload()

        if os.path.exists(filename_str):
            try: os.remove(filename_str)
            except OSError: pass
        return True

    except Exception as e:
        log.warning(f"Falha na voz online ({e}). Tentando offline...")
        if os.path.exists(filename_str):
            try: os.remove(filename_str)
            except OSError: pass
        return False

def speak_offline(text):
    log.info("[MODO OFFLINE] Ativando voz de backup...")
    engine = _get_offline_engine()
    engine.say(_treat_text(text))
    engine.runAndWait()

def speak(text, play_callback=None, show=True, force=False):
    """
    Função Thread-Safe com Callback de início de reprodução.
    Com a voz desligada (state.voice_enabled=False) só exibe o texto.
    show=False quando quem chama já exibe a resposta (ex: loop de voz da TUI).
    force=True fala mesmo com a voz desligada (ex: briefing) — só o TTS; o
    microfone continua fechado. Com o Modo Apresentação nada é falado.
    """
    if show:
        _show(text)
    from services.presentation import is_silent
    if is_silent() or not (state.voice_enabled or force):  # modo apresentação cala até o force
        if play_callback: play_callback()
        return
    with speech_lock:
        if not speak_online(text, on_play=play_callback):
            if play_callback: play_callback()
            speak_offline(text)

if __name__ == "__main__":
    state.voice_enabled = True
    speak("Teste de áudio com bloqueio de thread.")
