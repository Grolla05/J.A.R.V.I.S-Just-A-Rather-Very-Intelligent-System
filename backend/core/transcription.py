"""Transcrição de áudio local via faster-whisper (sem SaaS, sem custo por chamada)."""
from .config import settings
from .logger import log

_model = None  # singleton lazy — carregar no import travaria o boot


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        log.info(f"🎙️ Carregando modelo Whisper '{settings.WHISPER_MODEL_SIZE}' ({settings.WHISPER_DEVICE})...")
        _model = WhisperModel(
            settings.WHISPER_MODEL_SIZE,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
        )
        log.info("✅ Modelo Whisper carregado.")
    return _model


def transcribe_audio_file(file_path: str, language: str = "pt"):
    """Transcreve um arquivo de áudio local e retorna o texto (ou None em erro)."""
    try:
        model = _get_model()
        segments, _info = model.transcribe(file_path, language=language, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text or None
    except Exception as e:
        log.error(f"Erro na transcrição de áudio '{file_path}': {e}")
        return None
