"""Validação e gravação de anexos de chat enviados pela TUI (/attach ou arquivo arrastado).

- Imagem e áudio: `load_local_file` (base64; imagem vai ao modelo, áudio vira texto).
- Documento (texto, código, PDF): `load_document` devolve o **texto** — vai junto
  da mensagem como contexto (`prompts/file_context.md`), nunca vira skill.
  Segredos têm a linha trocada por "[oculto]"; arquivos sensíveis (.env, chaves)
  são recusados.
"""
import base64
import mimetypes
import uuid
from pathlib import Path

from .config import settings
from .logger import log

DOC_TEXT_MAX = 12000         # caracteres do documento enviados ao modelo (cabe no contexto local)
PDF_MAX_PAGES = 40
_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".html", ".htm",
    ".css", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".sql", ".tex", ".srt", ".vtt",
    ".py", ".pyw", ".ipynb", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".java", ".kt", ".kts", ".go", ".rs", ".rb", ".php", ".lua",
    ".r", ".swift", ".dart", ".scala", ".sh", ".bash", ".ps1", ".psm1", ".bat", ".cmd", ".gradle", ".dockerfile",
}
DOC_EXTS = _TEXT_EXTS | {".pdf"}
# Nunca anexar: o conteúdo é segredo por natureza
_SENSITIVE_NAMES = {".env", "id_rsa", "id_ed25519", "id_ecdsa", "credentials.json", "token.json", ".netrc", ".pgpass"}
_SENSITIVE_EXTS = {".pem", ".key", ".pfx", ".p12", ".kdbx", ".ppk"}


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
        raise ValueError(f"Tipo não suportado: {mime or file_path.suffix}. Use imagem, áudio, texto, código ou PDF.")

    size = file_path.stat().st_size
    if size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValueError(f"Arquivo excede {settings.MAX_UPLOAD_SIZE_MB}MB.")

    data = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return {"kind": kind, "mime": mime, "data": data, "name": file_path.name}

def is_document(path):
    """Extensão de documento que dá para ler como texto (ou PDF)."""
    name = Path(str(path)).name.lower()
    return Path(name).suffix in DOC_EXTS or name in ("dockerfile", "makefile", "readme")


def _is_sensitive(file_path):
    name = file_path.name.lower()
    return (name in _SENSITIVE_NAMES or name.startswith(".env.") or file_path.suffix.lower() in _SENSITIVE_EXTS)


def _pdf_text(file_path):
    from pypdf import PdfReader
    reader = PdfReader(str(file_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise ValueError("PDF protegido por senha.") from None
    pages = []
    for i, page in enumerate(reader.pages):
        if i >= PDF_MAX_PAGES:
            pages.append(f"[… mais {len(reader.pages) - PDF_MAX_PAGES} páginas não lidas]")
            break
        pages.append(page.extract_text() or "")
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    if not text.strip():
        raise ValueError("Esse PDF não tem texto (é imagem escaneada). Mande a página como imagem.")
    return text


def _plain_text(file_path):
    raw = file_path.read_bytes()
    if b"\x00" in raw[:4096]:
        raise ValueError(f"{file_path.name} não é um arquivo de texto.")
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Não consegui ler {file_path.name} como texto.")


def load_document(path, max_chars=DOC_TEXT_MAX):
    """Texto de um documento para anexar ao prompt.

    Retorna {"kind": "document", "name", "content", "truncated", "chars"}.
    Levanta ValueError com mensagem amigável se o arquivo não servir.
    """
    from .ocr import mask_secrets
    file_path = Path(str(path).strip().strip('"').strip("'")).expanduser()
    if not file_path.is_file():
        raise ValueError(f"Arquivo não encontrado: {file_path}")
    if _is_sensitive(file_path):
        raise ValueError(f"{file_path.name} guarda segredos (senhas/chaves); não envio ao modelo.")
    if file_path.stat().st_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValueError(f"Arquivo excede {settings.MAX_UPLOAD_SIZE_MB}MB.")
    try:
        text = _pdf_text(file_path) if file_path.suffix.lower() == ".pdf" else _plain_text(file_path)
    except ValueError:
        raise
    except Exception as e:
        log.warning(f"Documento ilegível ({file_path.name}): {e}")
        raise ValueError(f"Não consegui ler {file_path.name}.") from None
    text = mask_secrets(text.replace("\r\n", "\n")).strip()
    if not text:
        raise ValueError(f"{file_path.name} está vazio.")
    truncated = len(text) > max_chars
    return {"kind": "document", "name": file_path.name, "content": text[:max_chars],
            "truncated": truncated, "chars": len(text)}


def load_any(path):
    """/attach e arquivo arrastado: documento → load_document; imagem/áudio → load_local_file."""
    if _is_sensitive(Path(str(path).strip().strip('"').strip("'"))):
        raise ValueError(f"{Path(str(path)).name} guarda segredos (senhas/chaves); não envio ao modelo.")
    if is_document(path):
        return load_document(path)
    return load_local_file(path)
