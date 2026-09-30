"""Validação e gravação de anexos de chat (imagem/áudio) enviados pelo frontend."""
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


def read_upload_as_data_url(relative_path: str):
    """Relê um anexo salvo (path relativo a DIR_UPLOADS) e retorna como data URL
    base64, para reconstruir o preview de imagem ao reabrir uma sessão antiga.
    Retorna None se o arquivo não existir mais (ex: pasta uploads/ foi apagada)."""
    full_path = settings.DIR_UPLOADS / relative_path
    if not full_path.exists():
        log.warning(f"Anexo referenciado não encontrado em disco: {full_path}")
        return None
    mime, _ = mimetypes.guess_type(full_path.name)
    mime = mime or "application/octet-stream"
    raw = full_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"
