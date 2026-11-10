"""Google Agenda — leitura dos eventos (briefing, skill CALENDAR, filtro de notificações).

Autenticação: OAuth 2.0 de app Desktop (loopback + PKCE, `core/oauth.py`) com o
client PESSOAL que o usuário cria no Google Cloud (`GOOGLE_CLIENT_ID/SECRET` no
.env — docs/integracoes-oauth.md). O navegador abre na
tela "Escolha uma conta" (`prompt=select_account consent`). Escopo só de leitura.
O refresh token mora no Cofre do Windows (`core/secrets_store.py`).

REST direto com `requests` (sem google-api-python-client: custo de boot e ~20 MB).
Funções públicas nunca levantam: falha vira log + None/texto amigável.
"""
import datetime
import threading
import time
import unicodedata
import urllib.parse

from core import oauth, secrets_store
from core.config import settings
from core.logger import log

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API_BASE = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CONSOLE_URL = "https://console.cloud.google.com/apis/credentials"
SECRET_NAME = "google_calendar"
TIMEOUT = 8
BUSY_TTL = 60  # s — o filtro de notificações pergunta a cada alerta
MAX_EVENTS = 15

NOT_CONFIGURED = ("Falta a sua chave do Google, Senhor. Crie um client \"App para computador\" "
                  "no Google Cloud (passo a passo em docs/integracoes-oauth.md), preencha "
                  "`GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no .env e reinicie o JARVIS.")
NOT_CONNECTED = "A agenda não está conectada, Senhor. Conecte em /config → INTEGRAÇÕES."

_token_lock = threading.RLock()
_busy_cache = {"at": 0.0, "value": False}


class CalendarError(Exception):
    """Erro já traduzido para o usuário."""


# ------------------------------------------------------------------ HTTP
def _requests():
    import requests
    return requests


def _post(url, data):
    r = _requests().post(url, data=data, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise CalendarError(f"Google recusou ({r.status_code}): {r.text[:200]}")
    return r.json()


def _get(url, token, params=None):
    r = _requests().get(url, params=params or {}, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if r.status_code == 401:
        raise CalendarError("Sessão do Google expirou. Reconecte em /config → INTEGRAÇÕES.")
    if r.status_code >= 400:
        raise CalendarError(f"Google Agenda respondeu {r.status_code}.")
    return r.json()


# ------------------------------------------------------------------ token
def is_configured():
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def _load():
    return secrets_store.get(SECRET_NAME) or {}


def is_connected():
    return bool(_load().get("refresh_token"))


def account():
    return _load().get("account")


def build_authorize_url(redirect_uri, challenge, state):
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",   # devolve refresh token
        "prompt": "select_account consent",  # escolhe a conta + garante o refresh token
    })


def _store(payload, previous=None):
    data = dict(previous or {})
    data.update({k: v for k, v in payload.items() if v is not None and k != "expires_in"})
    if "expires_in" in payload:
        data["expires_at"] = time.time() + float(payload["expires_in"])
    secrets_store.set(SECRET_NAME, data)
    return data


def _access_token():
    with _token_lock:
        data = _load()
        if not data.get("refresh_token"):
            raise CalendarError(NOT_CONNECTED)
        if data.get("access_token") and not oauth.token_expired(data.get("expires_at")):
            return data["access_token"]
        try:
            payload = _post(TOKEN_URL, {
                "grant_type": "refresh_token",
                "refresh_token": data["refresh_token"],
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
            })
        except CalendarError as e:
            if "invalid_grant" in str(e):
                # Acesso revogado (ou token expirado): só um login novo resolve.
                secrets_store.delete(SECRET_NAME)
                raise CalendarError("O Google revogou o acesso à agenda. Reconecte em /config → INTEGRAÇÕES.")
            raise  # rede/servidor: mantém o token e tenta no próximo uso
        return _store(payload, data)["access_token"]


def connect(authorize=oauth.authorize):
    """Bloqueante (abre o navegador e espera). Devolve o texto para o usuário."""
    if not is_configured():
        return NOT_CONFIGURED
    result = authorize(build_authorize_url, settings.GOOGLE_AUTH_TIMEOUT)
    if not result:
        return "A agenda não foi autorizada (tempo esgotado ou acesso recusado)."
    code, verifier, redirect_uri = result
    try:
        payload = _post(TOKEN_URL, {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
        })
        if not payload.get("refresh_token"):
            return "O Google não devolveu um refresh token. Remova o acesso do JARVIS na sua conta Google e tente de novo."
        data = _store(payload)
        email = _get(f"{API_BASE}/calendars/primary", data["access_token"]).get("id")
        if email:
            _store({"account": email}, data)
    except CalendarError as e:
        log.error(f"Google Agenda: conexão falhou: {e}")
        return str(e)
    except Exception as e:
        log.error(f"Google Agenda: conexão falhou: {e}")
        return "Não consegui falar com o Google agora, Senhor."
    log.info("📅 Google Agenda conectado.")
    return f"Google Agenda conectado{f' ({email})' if email else ''}, Senhor."


def disconnect():
    data = _load()
    token = data.get("refresh_token") or data.get("access_token")
    if token:
        try:
            _requests().post(REVOKE_URL, params={"token": token}, timeout=TIMEOUT)
        except Exception as e:
            log.warning(f"Google Agenda: revogação falhou (token apagado mesmo assim): {e}")
    secrets_store.delete(SECRET_NAME)
    _busy_cache.update(at=0.0, value=False)
    return "Google Agenda desconectado."


# ----------------------------------------------------------------- eventos
def _local_bounds(day):
    start = datetime.datetime.combine(day, datetime.time.min).astimezone()
    return start, start + datetime.timedelta(days=1)


def parse_event(item):
    """Item da API → {'title', 'start', 'end', 'all_day'} com horários locais ingênuos."""
    def when(field):
        value = item.get(field) or {}
        if value.get("dateTime"):
            dt = datetime.datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
            return dt.astimezone().replace(tzinfo=None), False
        if value.get("date"):
            return datetime.datetime.fromisoformat(value["date"]), True
        return None, False

    start, all_day = when("start")
    end, _ = when("end")
    return {"title": (item.get("summary") or "(sem título)").strip(), "start": start, "end": end,
            "all_day": all_day}


def events(day=None):
    """Eventos do dia (agenda principal), em ordem. Levanta CalendarError."""
    day = day or datetime.date.today()
    start, end = _local_bounds(day)
    data = _get(f"{API_BASE}/calendars/primary/events", _access_token(), {
        "timeMin": start.isoformat(), "timeMax": end.isoformat(),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": MAX_EVENTS,
    })
    return [parse_event(i) for i in data.get("items", []) if i.get("status") != "cancelled"]


def format_events(items, label="hoje"):
    """Lista curta em texto: '3 eventos hoje: 09:00 Daily · 14:00 Dentista · dia inteiro: Feriado'."""
    if not items:
        return f"Agenda livre {label}."
    parts = [("dia inteiro: " if e["all_day"] or not e["start"] else e["start"].strftime("%H:%M ")) + e["title"]
             for e in items]
    noun = "evento" if len(items) == 1 else "eventos"
    return f"{len(items)} {noun} {label}: " + " · ".join(parts)


def summary(day=None, label="hoje"):
    """Linha para o briefing — None se a agenda não estiver conectada ou falhar."""
    if not (is_configured() and is_connected()):
        return None
    try:
        return format_events(events(day), label)
    except Exception as e:
        log.warning(f"Google Agenda indisponível no briefing: {e}")
        return None


def next_event(now=None, items=None):
    """Próximo evento com horário que ainda não começou (hoje)."""
    now = now or datetime.datetime.now()
    items = events(now.date()) if items is None else items
    return next((e for e in items if not e["all_day"] and e["start"] and e["start"] >= now), None)


def busy_now(items, now):
    """True se há um evento com horário acontecendo agora (dia inteiro não conta)."""
    return any(not e["all_day"] and e["start"] and e["end"] and e["start"] <= now < e["end"] for e in items)


def is_busy(now=None, clock=time.monotonic):
    """Em reunião agora? Cache de BUSY_TTL s; sem agenda/erro = False."""
    if not (is_configured() and is_connected()):
        return False
    if clock() - _busy_cache["at"] < BUSY_TTL:
        return _busy_cache["value"]
    now = now or datetime.datetime.now()
    try:
        value = busy_now(events(now.date()), now)
    except Exception as e:
        log.debug(f"Google Agenda: is_busy falhou: {e}")
        value = False
    _busy_cache.update(at=clock(), value=value)
    return value


# ------------------------------------------------------------ dia pedido
WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")
_WEEKDAY_WORDS = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}


def _plain(text):
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def resolve_day(text, today=None):
    """('hoje'|'amanhã'|...) → (date, rótulo) ou ('next', None) para "próxima reunião"."""
    today = today or datetime.date.today()
    low = _plain(text)
    if "proxim" in low and ("reuniao" in low or "compromisso" in low or "evento" in low):
        return "next", None
    if "depois de amanha" in low:
        return today + datetime.timedelta(days=2), "depois de amanhã"
    if "amanha" in low:
        return today + datetime.timedelta(days=1), "amanhã"
    for name, weekday in _WEEKDAY_WORDS.items():
        if name in low:
            delta = (weekday - today.weekday()) % 7
            label = "hoje" if delta == 0 else f"na {name}" if weekday < 5 else f"no {name}"
            label = label.replace("sabado", "sábado").replace("terca", "terça")
            return today + datetime.timedelta(days=delta), label
    return today, "hoje"
