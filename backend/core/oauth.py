"""OAuth 2.0 para apps de desktop: PKCE + callback num servidor efêmero do loopback.

Peças genéricas, sem provedor amarrado — `core/google_calendar.py` usa o fluxo
inteiro (`authorize`); `core/spotify.py` reaproveita o PKCE e a validade do token.

`authorize()` é bloqueante (até `timeout` segundos esperando o usuário clicar em
"Permitir"): quem chama da TUI roda num worker de thread. Nunca levanta exceção
por falha do usuário/rede — devolve None e registra o motivo no log.
"""
import base64
import hashlib
import secrets
import socket
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.logger import log

LOOPBACK_HOST = "127.0.0.1"
TOKEN_EXPIRY_MARGIN = 60  # s — renova com folga: request com 3 s de validade chega vencido

# Página que o navegador mostra depois do consentimento (visual do canvas: fundo
# #05080f, neon #00e5ff). HTML de página web, não prompt de LLM.
_PAGE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>J.A.R.V.I.S</title><style>
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#05080f;color:#c9d6ea;font:16px/1.6 Consolas,'JetBrains Mono',monospace}}
main{{border:4px double {color};padding:32px 40px;max-width:520px;background:#0b1220}}
h1{{margin:0 0 8px;font-size:20px;letter-spacing:3px;color:{color}}}
p{{margin:0}}
</style></head><body><main><h1>J.A.R.V.I.S &middot; {title}</h1><p>{text}</p></main></body></html>"""
_PAGE_OK = _PAGE.format(color="#00e5ff", title="CONECTADO",
                        text="Conta autorizada. Pode fechar esta aba e voltar ao terminal, Senhor.")
_PAGE_DENIED = _PAGE.format(color="#ff6b6b", title="NEGADO",
                            text="Autoriza&ccedil;&atilde;o negada. O JARVIS segue sem acesso a esta conta.")


def build_pkce_pair():
    """(code_verifier, code_challenge) do PKCE — RFC 7636: verifier de 43 a 128 chars,
    challenge = SHA-256 do verifier em base64url sem padding."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def token_expired(expires_at, now=None, margin=TOKEN_EXPIRY_MARGIN):
    """True se o access token já venceu (ou vence dentro da margem)."""
    if not isinstance(expires_at, (int, float)):
        return True
    reference = time.time() if now is None else now
    return reference >= (expires_at - margin)


def free_port(host=LOOPBACK_HOST):
    """Porta livre no loopback (o Google aceita qualquer porta em apps Desktop)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _handler_for(result):
    """Handler que grava a query do redirect em `result` (um dict por fluxo)."""

    class _Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if not params:  # favicon e afins: ignora
                self.send_response(204)
                self.end_headers()
                return
            result.update({k: (params.get(k) or [None])[0] for k in ("code", "state", "error")})
            body = _PAGE_OK if result.get("code") else _PAGE_DENIED
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, *_args):  # http.server escreve no stderr: corrompe a TUI
            return

    return _Callback


def wait_for_code(state, port, timeout, host=LOOPBACK_HOST, server_factory=HTTPServer, clock=time.monotonic):
    """Espera o redirect no loopback e devolve o `code` — ou None (tempo esgotado,
    recusa ou `state` divergente, que pode ser CSRF)."""
    result = {}
    try:
        server = server_factory((host, port), _handler_for(result))
    except OSError as e:
        log.error(f"OAuth: porta {port} indisponível para o callback: {e}")
        return None
    server.timeout = 1.0
    deadline = clock() + timeout
    try:
        while clock() < deadline and not result:
            server.handle_request()
    finally:
        server.server_close()
    if not result:
        log.warning(f"OAuth: ninguém autorizou em {timeout}s.")
        return None
    if result.get("error"):
        log.warning(f"OAuth: autorização recusada ({result['error']}).")
        return None
    if result.get("state") != state:
        log.error("OAuth: state do callback não confere. Autorização descartada.")
        return None
    return result.get("code")


def authorize(build_url, timeout, open_browser=webbrowser.open, wait=wait_for_code, port=None, path=""):
    """Fluxo completo até o code. `build_url(redirect_uri, challenge, state)` monta a URL
    de consentimento do provedor. Devolve `(code, verifier, redirect_uri)` ou None.

    `port`/`path` fixos para provedores que exigem o redirect exato cadastrado
    (Spotify: http://127.0.0.1:8888/callback); sem eles, porta livre (Google)."""
    port = port or free_port()
    redirect_uri = f"http://{LOOPBACK_HOST}:{port}{path}"
    verifier, challenge = build_pkce_pair()
    state = secrets.token_urlsafe(16)
    url = build_url(redirect_uri, challenge, state)
    log.info("OAuth: abrindo o navegador para autorizar…")
    try:
        open_browser(url)
    except Exception as e:  # sem navegador padrão: o usuário ainda pode abrir na mão
        log.warning(f"OAuth: não consegui abrir o navegador ({e}). URL: {url}")
    code = wait(state, port, timeout)
    return (code, verifier, redirect_uri) if code else None
