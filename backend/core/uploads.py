"""Validação e gravação de anexos de chat (imagem/áudio) enviados pela TUI (/attach)."""
import base64
import mimetypes
import uuid
from pathlib import Path

from .config import settings
from .logger import log


def save_base64_upload(b64_data: str, mime_type: str, filename: str, kind: str):
    """Valida mime/tamanho, decodifica base64 e grava em DIR_UPLOADS/<kind>/.

    kind: "image" ou "audio". Retorna o Path absoluto gravado, ou None se
    o upload for rejeitado (mime não permitido ou excede MAX_UPLOAD_SIZE_MB).
    """
    allowed = settings.ALLOWED_IMAGE_MIME if kind == "image" else settings.ALLOWED_AUDIO_MIME
    if mime_type not in allowed:
        log.warning(f"Upload rejeitado — mime não permitido para '{kind}': {mime_type}")
        return None

    try:
        raw = base64.b64decode(b64_data)
    except Exception as e:
        log.warning(f"Upload rejeitado — base64 inválido: {e}")
        return None

    if len(raw) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        log.warning(f"Upload rejeitado — excede {settings.MAX_UPLOAD_SIZE_MB}MB ({len(raw)} bytes)")
        return None

    dest_dir = settings.DIR_UPLOADS / kind
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
    dest_path = dest_dir / safe_name
    dest_path.write_bytes(raw)
    return dest_path


def load_local_file(path):
    """Lê um arquivo local para anexar no chat (/attach).

    Retorna {"kind": "image"|"audio", "mime", "data" (base64), "name"}.
    Levanta ValueError com mensagem amigável se o arquivo não servir.
    """
    file_path = Path(str(path).strip().strip('"').strip("'")).expanduser()
    if not file_path.is_file():
        raise ValueError(f"Arquivo não encontrado: {file_path}")

    mime, _ = mimetypes.guess_type(file_path.name)
    if mime in settings.ALLOWED_IMAGE_MIME:
        kind = "image"
    elif mime in settings.ALLOWED_AUDIO_MIME or (mime or "").startswith("audio/"):
        kind = "audio"
        # mimetypes do Windows devolve variações (audio/x-wav, audio/wave...)
        if mime not in settings.ALLOWED_AUDIO_MIME:
            mime = "audio/wav" if file_path.suffix.lower() == ".wav" else mime
    else:
        raise ValueError(f"Tipo não suportado: {mime or file_path.suffix}. Use imagem ou áudio.")

    size = file_path.stat().st_size
    if size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValueError(f"Arquivo excede {settings.MAX_UPLOAD_SIZE_MB}MB.")

    data = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return {"kind": kind, "mime": mime, "data": data, "name": file_path.name}