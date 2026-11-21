"""OCR local pelo motor nativo do Windows (Windows.Media.Ocr): 0 VRAM, offline.

Usado pela skill SCREEN_READ: a tela vira texto aqui e o texto vai ao modelo
de texto (gemma2) — que lê código, erro, prova e documento melhor que um
modelo de visão pequeno. Os imports do `winrt` são tardios (não pesam no
boot nem no agente). `recognize()` nunca levanta: falha → "".

Idioma: `OCR_LANGUAGE` do .env → pt-BR → en-US → idiomas do perfil do Windows.
Sem pacote de OCR do idioma: Configurações → Hora e idioma → Idioma → pt-BR →
Opções → "Reconhecimento óptico de caracteres".
"""
import asyncio
import io

from core.config import settings
from core.logger import log

UPSCALE_BELOW_H = 900   # imagem mais baixa que isso é ampliada ×2 (fonte de IDE/terminal)
MAX_DIMENSION = 10000   # OcrEngine.MaxImageDimension
_FALLBACK_LANGS = ("pt-BR", "en-US")


# ------------------------------------------------------------ lógica pura
def should_upscale(height):
    return 0 < height < UPSCALE_BELOW_H


def target_size(width, height):
    """Tamanho final: ×2 se baixa, depois reduzido para caber em MAX_DIMENSION."""
    if should_upscale(height):
        width, height = width * 2, height * 2
    scale = min(1.0, MAX_DIMENSION / max(width, height, 1))
    return max(1, int(width * scale)), max(1, int(height * scale))


def language_order(preferred=""):
    """Idiomas a tentar, sem repetição: o do .env primeiro."""
    out = []
    for lang in ((preferred or "").strip(), *_FALLBACK_LANGS):
        if lang and lang not in out:
            out.append(lang)
    return out


SECRET_MIN_LEN = 20     # token sem prefixo conhecido só conta como segredo a partir disso
_TOKEN_STRIP = "\"'`()[]{}<>,;:."
_CODE_CHARS = set("().,\\'\"[]{}<>:;")  # chave/senha não tem isso; código e caminho têm


def is_secret_token(token):
    """Token de cara de chave/senha. Mais rígido que `clip_history.looks_secret`
    (feito para um clipboard de 1 token): na tela, 'NameError:' ou 'main.py:3'
    não podem sumir. Prefixo conhecido (sk-, ghp_…) basta; senão exige
    SECRET_MIN_LEN+ caracteres, dígito e as classes do `looks_secret`."""
    from services.clip_history import _SECRET_PREFIXES, looks_secret
    for part in token.split("="):  # CHAVE=valor
        part = part.strip(_TOKEN_STRIP)
        if len(part) >= 8 and part.startswith(_SECRET_PREFIXES):
            return True
        if (len(part) >= SECRET_MIN_LEN and any(c.isdigit() for c in part)
                and not any(c in _CODE_CHARS for c in part) and looks_secret(part)):
            return True
    return False


def mask_secrets(text):
    """Linhas com token de cara de senha/chave viram '[oculto]' (antes de ir ao
    modelo e de ficar no histórico da sessão)."""
    out = []
    for line in (text or "").splitlines():
        out.append("[oculto]" if any(is_secret_token(tok) for tok in line.split()) else line)
    return "\n".join(out)


# ------------------------------------------------------------------ WinRT
def _prepare(image):
    from PIL import Image
    image = image.convert("RGB")
    size = target_size(*image.size)
    if size != image.size:
        image = image.resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _engine(lang):
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine
    for tag in language_order(lang):
        try:
            language = Language(tag)
            if OcrEngine.is_language_supported(language):
                engine = OcrEngine.try_create_from_language(language)
                if engine:
                    return engine
        except Exception as e:
            log.debug(f"[OCR] Idioma {tag} indisponível: {e}")
    return OcrEngine.try_create_from_user_profile_languages()


async def _recognize_png(png, lang):
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = _engine(lang)
    if engine is None:
        log.warning("[OCR] Nenhum idioma de OCR instalado no Windows.")
        return ""
    result = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines)


def recognize(image, lang=None):
    """Texto da imagem PIL (linhas separadas por \\n); "" se falhar."""
    if image is None:
        return ""
    try:
        png = _prepare(image)
        lang = settings.OCR_LANGUAGE if lang is None else lang
        return asyncio.run(_recognize_png(png, lang)).strip()
    except Exception as e:
        log.warning(f"[OCR] Reconhecimento falhou: {e}")
        return ""
