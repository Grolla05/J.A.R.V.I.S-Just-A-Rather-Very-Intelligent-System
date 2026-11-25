"""Conta Google genérica: OAuth Desktop (loopback + PKCE) + token no Cofre do Windows.

Cada integração cria a sua `GoogleAccount(escopos, nome_do_segredo)` — token próprio,
card próprio em /config → INTEGRAÇÕES. Assim pedir um escopo novo (ex.: Gmail) não
obriga a reconectar a Agenda. Usa o client PESSOAL do usuário (`GOOGLE_CLIENT_ID/SECRET`).

REST direto com `requests` (import tardio). Erros viram `error_cls` com texto amigável.
"""
import threading
import time
import urllib.parse

from core import oauth, secrets_store
from core.config import settings
from core.logger import log

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CONSOLE_URL = "https://console.cloud.google.com/apis/credentials"
TIMEOUT = 15

NOT_CONFIGURED = ("Falta a sua chave do Google, Senhor. Crie um client \"App para computador\" "
                  "no Google Cloud (passo a passo em docs/integracoes-oauth.md), preencha "
                  "`GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no .env e reinicie o JARVIS.")


class GoogleError(Exception):
    """Erro já traduzido para o usuário."""


def _requests():
    import requests
    return requests


class GoogleAccount:
    def __init__(self, scopes, secret_name, label, *, error_cls=GoogleError, not_connected=None,
                 account_probe=None):
        self.scopes = list(scopes)
        self.secret_name = secret_name
        self.label = label
        self.error_cls = error_cls
        self.not_connected = not_connected or f"{label} não está conectado, Senhor. Conecte em /config → INTEGRAÇÕES."
        self.account_probe = account_probe   # fn(token) -> e-mail da conta
        self._lock = threading.RLock()

    # ------------------------------------------------------------- estado
    def is_configured(self):
        return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)

    def _load(self):
        return secrets_store.get(self.secret_name) or {}

    def is_connected(self):
        return bool(self._load().get("refresh_token"))

    def account(self):
        return self._load().get("account")

    def build_authorize_url(self, redirect_uri, challenge, state):
        return AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account consent",
        })

    # -------------------------------------------------------------- token
    def _post_token(self, data):
        r = _requests().post(TOKEN_URL, data=data, timeout=TIMEOUT)
        if r.status_code >= 400:
            raise self.error_cls(f"Google recusou ({r.status_code}): {r.text[:200]}")
        return r.json()

    def _store(self, payload, previous=None):
        data = dict(previous or {})
        data.update({k: v for k, v in payload.items() if v is not None and k != "expires_in"})
        if "expires_in" in payload:
            data["expires_at"] = time.time() + float(payload["expires_in"])
        secrets_store.set(self.secret_name, data)
        return data

    def access_token(self):
        with self._lock:
            data = self._load()
            if not data.get("refresh_token"):
                raise self.error_cls(self.not_connected)
            if data.get("access_token") and not oauth.token_expired(data.get("expires_at")):
                return data["access_token"]
            try:
                payload = self._post_token({
                    "grant_type": "refresh_token",
                    "refresh_token": data["refresh_token"],
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                })
            except self.error_cls as e:
                if "invalid_grant" in str(e):
                    secrets_store.delete(self.secret_name)
                    raise self.error_cls(f"O Google revogou o acesso ao {self.label}. "
                                         "Reconecte em /config → INTEGRAÇÕES.") from e
                raise
            return self._store(payload, data)["access_token"]

    # --------------------------------------------------------------- HTTP
    def request(self, method, url, params=None, json=None):
        """Chamada autenticada. Devolve o JSON (ou {} em 204). Levanta `error_cls`."""
        token = self.access_token()
        try:
            r = _requests().request(method, url, params=params or {}, json=json,
                                    headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
        except Exception as e:
            raise self.error_cls(f"Não consegui falar com o {self.label} agora, Senhor.") from e
        if r.status_code == 401:
            raise self.error_cls(f"Sessão do {self.label} expirou. Reconecte em /config → INTEGRAÇÕES.")
        if r.status_code == 403 and "scope" in (r.text or "").lower():
            raise self.error_cls(f"O {self.label} precisa de permissão nova. Reconecte em /config → INTEGRAÇÕES.")
        if r.status_code >= 400:
            raise self.error_cls(f"{self.label} respondeu {r.status_code}: {(r.text or '')[:160]}")
        if r.status_code == 204:
            return {}
        try:
            return r.json() or {}
        except Exception:
            return {}

    # ------------------------------------------------------ conectar/sair
    def connect(self, authorize=oauth.authorize):
        """Bloqueante (abre o navegador e espera). Devolve o texto para o usuário."""
        if not self.is_configured():
            return NOT_CONFIGURED
        result = authorize(self.build_authorize_url, settings.GOOGLE_AUTH_TIMEOUT)
        if not result:
            return f"O {self.label} não foi autorizado (tempo esgotado ou acesso recusado)."
        code, verifier, redirect_uri = result
        email = None
        try:
            payload = self._post_token({
                "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
                "redirect_uri": redirect_uri, "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
            })
            if not payload.get("refresh_token"):
                return ("O Google não devolveu um refresh token. Remova o acesso do JARVIS na sua conta "
                        "Google e tente de novo.")
            data = self._store(payload)
            if self.account_probe:
                email = self.account_probe(data["access_token"])
                if email:
                    self._store({"account": email}, data)
        except self.error_cls as e:
            log.error(f"{self.label}: conexão falhou: {e}")
            return str(e)
        except Exception as e:
            log.error(f"{self.label}: conexão falhou: {e}")
            return "Não consegui falar com o Google agora, Senhor."
        log.info(f"{self.label} conectado.")
        return f"{self.label} conectado{f' ({email})' if email else ''}, Senhor."

    def disconnect(self):
        data = self._load()
        token = data.get("refresh_token") or data.get("access_token")
        if token:
            try:
                _requests().post(REVOKE_URL, params={"token": token}, timeout=TIMEOUT)
            except Exception as e:
                log.warning(f"{self.label}: revogação falhou (token apagado mesmo assim): {e}")
        secrets_store.delete(self.secret_name)
        return f"{self.label} desconectado."
