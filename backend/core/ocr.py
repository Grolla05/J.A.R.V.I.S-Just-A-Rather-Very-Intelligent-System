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

UPSCALE_BELOW_H = 400   # só imagem bem pequena é ampliada ×2 (medido: em janela normal ampliar piora)
MAX_DIMENSION = 10000   # OcrEngine.MaxImageDimension
_FALLBACK_LANGS = ("pt-BR", "en-US")
DIGITS_LANG = "en-US"   # 2ª leitura: o motor inglês lê dígitos de fonte de código bem melhor


# ------------------------------------------------------------ lógica pura
def should_upscale(height):
    return 0 < height < UPSCALE_BELOW_H


def target_size(width, height):
    """Tamanho final: ×2 se baixa, depois reduzido para caber em MAX_DIMENSION."""
    if should_upscale(height):
        width, height = width * 2, height * 2
    scale = min(1.0, MAX_DIMENSION / max(width, height, 1))
    return max(1, int(width * scale)), max(1, int(height * scale))


def _digits(tokens):
    return sum(c.isdigit() for tok in tokens for c in tok)


def merge_line(primary, english):
    """Uma linha: palavras do motor principal, exceto trechos em que os dois
    lados têm dígitos e divergem — aí vale o inglês ('8a'→'80', '438'→'430').
    Se só o inglês tem dígito, não troca (evita 'linha' → '1inha')."""
    import difflib
    a, b = primary.split(), english.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        left, right = a[i1:i2], b[j1:j2]
        if op == "replace" and _digits(left) and _digits(right) >= _digits(left):
            out.extend(right)
        else:
            out.extend(left)
    return " ".join(out)


def merge_readings(primary, english):
    """Mescla duas leituras da mesma imagem linha a linha (pareadas pelo difflib).
    Linhas sem par ficam como o motor principal leu."""
    import difflib
    p_lines, e_lines = primary.splitlines(), english.splitlines()
    out = list(p_lines)
    matcher = difflib.SequenceMatcher(a=p_lines, b=e_lines, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "replace" and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                out[i1 + k] = merge_line(p_lines[i1 + k], e_lines[j1 + k])
    return "\n".join(out)


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


def _engine_exact(tag):
    """Motor de um idioma específico, ou None se não instalado."""
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine
    try:
        language = Language(tag)
        if OcrEngine.is_language_supported(language):
            return OcrEngine.try_create_from_language(language)
    except Exception as e:
        log.debug(f"[OCR] Idioma {tag} indisponível: {e}")
    return None


async def _decode(png):
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
    return await decoder.get_software_bitmap_async()


async def _read(engine, bitmap):
    result = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines)


async def _recognize_png(png, lang):
    """Leitura no idioma principal; se ele não for inglês, também em en-US, e
    as duas são mescladas (`merge_readings`): o motor pt-BR acerta acentos mas
    erra dígitos de fontes de código ('80' → '8a', '430' → '438')."""
    bitmap = await _decode(png)
    engine = _engine(lang)
    if engine is None:
        log.warning("[OCR] Nenhum idioma de OCR instalado no Windows.")
        return ""
    primary = await _read(engine, bitmap)
    if str(engine.recognizer_language.language_tag).lower().startswith("en"):
        return primary
    english = _engine_exact(DIGITS_LANG)
    if english is None:
        return primary
    return merge_readings(primary, await _read(english, bitmap))


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
