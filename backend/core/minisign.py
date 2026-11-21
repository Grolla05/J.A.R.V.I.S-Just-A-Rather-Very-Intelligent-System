"""Assinatura Minisign (Ed25519) do instalador — gerar chave, assinar e verificar.

Formato compatível com o `minisign` oficial (https://jedisct1.github.io/minisign/):
- chave pública: base64( b"Ed" + key_id[8] + chave[32] )
- assinatura (`.minisig`), 4 linhas:
    untrusted comment: <texto livre>
    base64( b"ED" + key_id[8] + Ed25519(BLAKE2b-512(arquivo))[64] )
    trusted comment: <texto>
    base64( Ed25519(assinatura[64] + trusted comment)[64] )

A chave secreta do CI (`MINISIGN_SECRET_KEY`) é só nossa: base64( key_id[8] +
semente Ed25519[32] ), sem a cifra scrypt do formato oficial — ela vive num
secret do GitHub e nunca toca o disco do usuário.

Sem dependência do pacote `core` (o agente residente e `installer/sign_release.py`
importam este arquivo sozinho). `cryptography` é importado só na hora do uso.
"""
import base64
import hashlib
import os

PUBKEY_ALG = b"Ed"
PREHASH_ALG = b"ED"   # assinatura sobre o BLAKE2b-512 do arquivo
LEGACY_ALG = b"Ed"    # assinatura sobre o arquivo cru (minisign antigo)
CHUNK = 1024 * 1024


class SignatureError(Exception):
    """Assinatura ausente, malformada, de outra chave ou que não confere."""


def _ed25519():
    from cryptography.hazmat.primitives.asymmetric import ed25519
    return ed25519


def _raw_public(private_key):
    from cryptography.hazmat.primitives import serialization
    return private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _b64decode(text, what):
    try:
        return base64.b64decode(text.strip(), validate=True)
    except (ValueError, TypeError) as e:
        raise SignatureError(f"{what} não é base64 válido") from e


def blake2b_file(path):
    h = hashlib.blake2b(digest_size=64)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.digest()


# ------------------------------------------------------------------ chaves
def generate_keypair():
    """(chave secreta do CI, chave pública minisign), ambas em base64."""
    seed = os.urandom(32)
    key_id = os.urandom(8)
    private = _ed25519().Ed25519PrivateKey.from_private_bytes(seed)
    public = base64.b64encode(PUBKEY_ALG + key_id + _raw_public(private)).decode()
    secret = base64.b64encode(key_id + seed).decode()
    return secret, public


def parse_public_key(text):
    """(key_id, chave Ed25519). Aceita a linha base64 ou o arquivo .pub inteiro."""
    lines = [ln for ln in str(text or "").strip().splitlines() if ln and not ln.startswith("untrusted comment:")]
    if not lines:
        raise SignatureError("chave pública vazia")
    raw = _b64decode(lines[-1], "chave pública")
    if len(raw) != 42 or raw[:2] != PUBKEY_ALG:
        raise SignatureError("chave pública em formato desconhecido")
    return raw[2:10], _ed25519().Ed25519PublicKey.from_public_bytes(raw[10:])


def _parse_secret(text):
    raw = _b64decode(text, "chave secreta")
    if len(raw) != 40:
        raise SignatureError("chave secreta em formato desconhecido")
    return raw[:8], _ed25519().Ed25519PrivateKey.from_private_bytes(raw[8:])


# ------------------------------------------------------------------ assinar
def sign_file(path, secret, trusted_comment=None, untrusted_comment="assinatura do J.A.R.V.I.S"):
    """Conteúdo do `.minisig` (texto) para o arquivo `path`."""
    key_id, private = _parse_secret(secret)
    trusted = trusted_comment or f"file:{os.path.basename(path)}\thashed"
    if "\n" in trusted or "\r" in trusted:
        raise SignatureError("trusted comment não pode ter quebra de linha")
    signature = private.sign(blake2b_file(path))
    global_sig = private.sign(signature + trusted.encode("utf-8"))
    return (f"untrusted comment: {untrusted_comment}\n"
            f"{base64.b64encode(PREHASH_ALG + key_id + signature).decode()}\n"
            f"trusted comment: {trusted}\n"
            f"{base64.b64encode(global_sig).decode()}\n")


# ------------------------------------------------------------------ verificar
def verify_file(path, sig_text, public_key):
    """Confere `path` contra o `.minisig`. Devolve o trusted comment; levanta
    SignatureError se a assinatura for de outra chave ou não conferir."""
    from cryptography.exceptions import InvalidSignature

    key_id, public = parse_public_key(public_key)
    lines = str(sig_text or "").replace("\r\n", "\n").split("\n")
    if len(lines) < 4 or not lines[0].startswith("untrusted comment:") \
            or not lines[2].startswith("trusted comment: "):
        raise SignatureError("assinatura malformada")
    raw = _b64decode(lines[1], "assinatura")
    if len(raw) != 74:
        raise SignatureError("assinatura com tamanho inválido")
    alg, sig_key_id, signature = raw[:2], raw[2:10], raw[10:]
    if sig_key_id != key_id:
        raise SignatureError("assinatura feita com outra chave")
    if alg == PREHASH_ALG:
        message = blake2b_file(path)
    elif alg == LEGACY_ALG:
        with open(path, "rb") as fh:
            message = fh.read()
    else:
        raise SignatureError("algoritmo de assinatura desconhecido")
    trusted = lines[2][len("trusted comment: "):]
    global_sig = _b64decode(lines[3], "assinatura global")
    try:
        public.verify(signature, message)
        public.verify(global_sig, signature + trusted.encode("utf-8"))
    except InvalidSignature as e:
        raise SignatureError("assinatura não confere") from e
    return trusted
