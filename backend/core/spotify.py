"""Subsistema Spotify do J.A.R.V.I.S.

Três camadas, de baixo pra cima:

1. AUTENTICAÇÃO (OAuth 2.0 PKCE, `core/oauth.py`) — sem client_secret. O
   Client ID é PESSOAL: cada usuário cria o próprio app (SPOTIFY_CLIENT_ID no .env).
   O navegador abre no login do Spotify (show_dialog) para escolher a conta.
   O refresh token fica no Cofre do Windows (`core/secrets_store.py`): conecta
   uma vez e segue conectado; só pede login de novo se o acesso for revogado.
2. WEB API — busca, playlists do usuário, dispositivos e controle de player.
   Exige conta Premium para os endpoints `/v1/me/player/*`.
3. BOOTSTRAP LOCAL (Win32) — abre o app, acha o HWND e força o play.
   Não é legado: `PUT /v1/me/player/play` devolve 404 NO_ACTIVE_DEVICE quando
   o Spotify desktop está fechado, e é esta camada que acorda o dispositivo.

O cliente é um singleton (`spotify`), no mesmo molde de `core.obsidian`.
"""
import ctypes
import json
import re
import socket
import threading
import time
import urllib.parse

import requests

from . import secrets_store
from .config import settings
from .logger import log
from .oauth import build_pkce_pair, token_expired
from .utils import TTLCache

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

# Renova o token com folga: um request que sai com 3s de validade chega expirado.
TOKEN_EXPIRY_MARGIN = 60

# Whitelist de URIs. Fecha injeção de shell no `cmd /c start` da camada local.
SPOTIFY_URI_PATTERN = re.compile(r"spotify:(playlist|album|track):[A-Za-z0-9]+")

# As playlists do usuário mudam pouco — evita repaginar 50 itens a cada comando.
_playlist_cache = TTLCache(maxsize=1, ttl=300)

# Serializa refresh/gravação: a thread de voz e a de chat podem colidir.
_token_lock = threading.RLock()

# Impede que dois "toque X" seguidos abram duas abas de autorização.
_auth_in_progress = threading.Event()


# ============================================================================
# 1. PKCE — HELPERS PUROS
# ============================================================================
# PKCE e validade do token vivem em core/oauth.py (compartilhados com o Google Agenda).
_build_pkce_pair = build_pkce_pair


def _token_is_expired(expires_at, now=None, margin=TOKEN_EXPIRY_MARGIN):
    """True se o access token já venceu (ou vence dentro da margem)."""
    return token_expired(expires_at, now=now, margin=margin)


def _sanitize_spotify_uri(uri):
    """Normaliza e valida uma URI do Spotify.

    Retorna '' se a URI for inválida — impede interpolação arbitrária no shell
    quando ela desce para o `cmd /c start` da camada local.
    """
    if not isinstance(uri, str):
        return ""

    clean = uri.strip()

    # Remove o sufixo ':play' legado (truque antigo que os clients atuais ignoram)
    if clean.endswith(":play"):
        clean = clean[:-len(":play")]

    return clean if SPOTIFY_URI_PATTERN.fullmatch(clean) else ""


def _pick_device(devices, hostname=None):
    """Escolhe em qual dispositivo tocar.

    Precedência: o que já está ativo > este PC pelo nome > qualquer Computer >
    qualquer coisa. Retorna None se a lista estiver vazia.
    """
    if not devices:
        return None

    for device in devices:
        if device.get("is_active"):
            return device

    if hostname:
        alvo = hostname.strip().lower()
        for device in devices:
            if (device.get("name") or "").strip().lower() == alvo:
                return device

    for device in devices:
        if device.get("type") == "Computer":
            return device

    return devices[0]


# ============================================================================
# 2. PERSISTÊNCIA DO TOKEN
# ============================================================================
SECRET_NAME = "spotify"


def _load_token():
    """Token salvo no Cofre do Windows. Migra o `spotify_token.json` antigo na 1ª
    leitura (e apaga o arquivo). Retorna {} se não houver."""
    data = secrets_store.get(SECRET_NAME)
    if data:
        return data
    path = settings.SPOTIFY_TOKEN_PATH
    try:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.warning(f"⚠️ Token antigo do Spotify ilegível ({e}). Reautorização necessária.")
        return {}
    if not isinstance(data, dict):
        return {}
    if secrets_store.set(SECRET_NAME, data):
        try:
            path.unlink()
            log.info("🔐 Token do Spotify migrado para o Cofre do Windows.")
        except OSError:
            pass
    return data


def _save_token(payload, previous=None):
    """Grava o token, preservando o refresh token quando o Spotify não manda um novo.

    No fluxo PKCE o Spotify ROTACIONA o refresh_token a cada renovação — mas nem
    sempre devolve um. Sobrescrever com None mata a sessão em 1 hora. Fica no Cofre
    do Windows: a conta segue conectada entre reinícios, sem pedir login de novo.
    """
    with _token_lock:
        base = dict(_load_token() if previous is None else previous)
        base.update({k: v for k, v in payload.items() if v is not None})

        if "expires_in" in payload:
            base["expires_at"] = time.time() + float(payload["expires_in"])
            base.pop("expires_in", None)

        if not secrets_store.set(SECRET_NAME, base):
            log.error("❌ Não consegui guardar o token do Spotify.")
        return base


# ============================================================================
# 3. FLUXO DE AUTORIZAÇÃO (PKCE)
# ============================================================================
def _build_authorize_url(redirect_uri, challenge, state):
    """URL de consentimento do Spotify. `show_dialog=true` sempre mostra a tela de
    login/consentimento — dá para entrar com outra conta em vez de reaproveitar a
    sessão do navegador."""
    query = urllib.parse.urlencode({
        "client_id": settings.SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
        "scope": settings.SPOTIFY_SCOPES,
        "show_dialog": "true",
    })
    return f"{AUTH_URL}?{query}"


def _redirect_parts():
    """(porta, caminho) do SPOTIFY_REDIRECT_URI — o Spotify exige o redirect exato
    cadastrado no app (http://127.0.0.1:8888/callback)."""
    parsed = urllib.parse.urlparse(settings.SPOTIFY_REDIRECT_URI)
    return parsed.port or 8888, parsed.path or ""


def _exchange_code(code, verifier, redirect_uri=None):
    """Troca o authorization code pelo par de tokens."""
    try:
        r = requests.post(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or settings.SPOTIFY_REDIRECT_URI,
            "client_id": settings.SPOTIFY_CLIENT_ID,
            "code_verifier": verifier,
        }, timeout=settings.TIMEOUT_SPOTIFY)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.error(f"❌ Falha ao trocar o código do Spotify por um token: {e}")
        return None


def _refresh(refresh_token):
    """Renova o access token. Devolve o dict de token atualizado ou None."""
    try:
        r = requests.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.SPOTIFY_CLIENT_ID,
        }, timeout=settings.TIMEOUT_SPOTIFY)
        if r.status_code == 400 and "invalid_grant" in r.text:
            # Acesso revogado pelo usuário (ou app removido): só um login novo resolve.
            log.warning("⚠️ O Spotify revogou o acesso do JARVIS. Reconecte em /config → INTEGRAÇÕES.")
            disconnect()
            return None
        r.raise_for_status()
        payload = r.json()
    except requests.RequestException as e:
        # Rede/servidor: mantém o token, tenta de novo no próximo uso.
        log.warning(f"⚠️ Não consegui renovar o token do Spotify: {e}")
        return None

    log.debug("🔑 Token do Spotify renovado.")
    return _save_token(payload)


def _fetch_account(access_token):
    """Nome da conta (display_name, ou id) para mostrar no card. None se falhar."""
    try:
        r = requests.get(f"{API_BASE}/me", headers={"Authorization": f"Bearer {access_token}"},
                         timeout=settings.TIMEOUT_SPOTIFY)
        if r.status_code != 200:
            return None
        me = r.json()
        return me.get("display_name") or me.get("id")
    except requests.RequestException as e:
        log.debug(f"Spotify: /me indisponível: {e}")
        return None


def _run_auth_flow(authorize=None):
    """Executa o consentimento de ponta a ponta. Bloqueante — rode numa thread."""
    from .oauth import authorize as default_authorize
    authorize = authorize or default_authorize
    if not settings.SPOTIFY_CLIENT_ID:
        log.error("❌ SPOTIFY_CLIENT_ID vazio no .env (ver docs/integracoes-oauth.md).")
        return False

    if _auth_in_progress.is_set():
        log.debug("Autorização do Spotify já em andamento — ignorando pedido duplicado.")
        return False

    _auth_in_progress.set()
    try:
        port, path = _redirect_parts()
        result = authorize(_build_authorize_url, settings.SPOTIFY_AUTH_TIMEOUT, port=port, path=path)
        if not result:
            return False
        code, verifier, redirect_uri = result

        payload = _exchange_code(code, verifier, redirect_uri)
        if not payload:
            return False

        token = _save_token(payload, previous={})  # conta nova: não herda o token antigo
        account = _fetch_account(token.get("access_token"))
        if account:
            _save_token({"account": account}, previous=token)
        log.info("✅ Spotify autorizado.")
        return True
    finally:
        _auth_in_progress.clear()


def disconnect():
    """Apaga o token salvo (o próximo uso pede autorização de novo)."""
    with _token_lock:
        secrets_store.delete(SECRET_NAME)
        try:
            settings.SPOTIFY_TOKEN_PATH.unlink(missing_ok=True)  # resto da versão antiga
        except OSError as e:
            log.error(f"Não consegui apagar o token antigo do Spotify: {e}")
            return False
    return True


def start_authorization(blocking=False):
    """Dispara o consentimento. Por padrão em thread daemon — o loop de voz
    não pode ficar 120s parado esperando o usuário clicar em 'Agree'."""
    if blocking:
        return _run_auth_flow()
    threading.Thread(target=_run_auth_flow, daemon=True).start()
    return None


# ============================================================================
# 4. CLIENTE DA WEB API
# ============================================================================
class SpotifyClient:
    """Wrapper fino da Web API. Nunca levanta exceção: erro vira log + None."""

    def is_configured(self):
        return bool(settings.SPOTIFY_CLIENT_ID)

    def is_authorized(self):
        token = _load_token()
        return bool(token.get("access_token") or token.get("refresh_token"))

    def account(self):
        """Conta conectada (nome no Spotify) ou None."""
        return _load_token().get("account")

    def _access_token(self):
        """Devolve um access token válido, renovando quando necessário."""
        with _token_lock:
            token = _load_token()
            if not token:
                return None
            if not _token_is_expired(token.get("expires_at")):
                return token.get("access_token")

            refresh_token = token.get("refresh_token")
            if not refresh_token:
                return None
            renewed = _refresh(refresh_token)
            return (renewed or {}).get("access_token")

    def _req(self, method, path, _retry=True, **kwargs):
        """Request autenticado. 401 renova o token e tenta uma única vez mais."""
        access = self._access_token()
        if not access:
            log.warning("⚠️ Spotify sem autorização válida.")
            return None

        try:
            r = requests.request(
                method, f"{API_BASE}{path}",
                headers={"Authorization": f"Bearer {access}",
                         "Content-Type": "application/json"},
                timeout=settings.TIMEOUT_SPOTIFY,
                **kwargs
            )
        except requests.RequestException as e:
            log.warning(f"Spotify inacessível: {e}")
            return None

        if r.status_code == 401 and _retry:
            token = _load_token()
            if token.get("refresh_token") and _refresh(token["refresh_token"]):
                return self._req(method, path, _retry=False, **kwargs)
            return None

        if r.status_code == 403:
            # Praticamente sempre "Premium required" nos endpoints de player.
            log.warning(f"⚠️ Spotify recusou {method} {path} (403 — a conta precisa ser Premium).")
            return None

        if r.status_code == 404:
            # NO_ACTIVE_DEVICE cai aqui. O chamador resolve com ensure_device_ready().
            log.debug(f"Spotify 404 em {method} {path} (provável dispositivo inativo).")
            return None

        if r.status_code >= 400:
            log.warning(f"⚠️ Spotify respondeu {r.status_code} em {method} {path}.")
            return None

        return r

    @staticmethod
    def _json(response):
        """204 e corpo vazio são respostas normais nos endpoints de player."""
        if response is None or response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    # --- Busca -------------------------------------------------------------
    def search(self, query, kind="track", limit=5):
        """Busca no catálogo. `kind` é 'track', 'playlist', 'album'..."""
        if not query:
            return []
        params = urllib.parse.urlencode({
            "q": query, "type": kind, "limit": limit,
            "market": settings.SPOTIFY_MARKET,
        })
        data = self._json(self._req("GET", f"/search?{params}"))
        if not data:
            return []
        # A API pluraliza a chave: track -> tracks, playlist -> playlists.
        itens = (data.get(f"{kind}s") or {}).get("items") or []
        # Playlists removidas voltam como None dentro da lista. Filtra.
        return [i for i in itens if i]

    def my_playlists(self, force=False):
        """Playlists do usuário (paginado). Cacheado por 5 min."""
        if not force:
            cached = _playlist_cache.get("all")
            if cached is not None:
                return cached

        playlists, offset = [], 0
        while offset < 500:  # teto de segurança: 10 páginas
            data = self._json(self._req("GET", f"/me/playlists?limit=50&offset={offset}"))
            if not data:
                break
            itens = [i for i in (data.get("items") or []) if i]
            playlists.extend(itens)
            if not data.get("next"):
                break
            offset += 50

        _playlist_cache.set("all", playlists)
        return playlists

    # --- Dispositivos ------------------------------------------------------
    def devices(self):
        data = self._json(self._req("GET", "/me/player/devices"))
        return (data or {}).get("devices") or []

    def transfer_playback(self, device_id, play=True):
        r = self._req("PUT", "/me/player",
                      json={"device_ids": [device_id], "play": play})
        return r is not None

    # --- Controle de reprodução -------------------------------------------
    def play(self, uris=None, context_uri=None, device_id=None):
        """Toca faixas soltas (`uris`) ou um contexto (playlist/álbum)."""
        body = {}
        if uris:
            body["uris"] = list(uris)
        elif context_uri:
            body["context_uri"] = context_uri

        path = "/me/player/play"
        if device_id:
            path += f"?device_id={urllib.parse.quote(device_id)}"

        # Sem corpo, /play apenas retoma o que estava pausado.
        r = self._req("PUT", path, json=body) if body else self._req("PUT", path)
        return r is not None

    def pause(self):
        return self._req("PUT", "/me/player/pause") is not None

    def next_track(self):
        return self._req("POST", "/me/player/next") is not None

    def previous_track(self):
        return self._req("POST", "/me/player/previous") is not None

    def queue(self, uri):
        clean = _sanitize_spotify_uri(uri)
        if not clean:
            return False
        return self._req("POST", f"/me/player/queue?uri={urllib.parse.quote(clean)}") is not None

    def now_playing(self):
        """Estado atual do player. None quando não há nada tocando."""
        return self._json(self._req("GET", "/me/player/currently-playing"))


spotify = SpotifyClient()


# ============================================================================
# 5. BOOTSTRAP LOCAL (Windows API)
# ============================================================================
SW_MAXIMIZE = 3
VK_MENU = 0x12               # ALT — usado para destravar o SetForegroundWindow
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 2

# Títulos que o Spotify usa quando NÃO há reprodução ativa.
# Tocando, o título vira "Artista - Faixa".
SPOTIFY_IDLE_TITLES = {"spotify", "spotify premium", "spotify free"}
SPOTIFY_PROCESS_NAME = "spotify.exe"

SPOTIFY_WINDOW_TIMEOUT = 15.0   # s — espera máxima pela janela aparecer
SPOTIFY_POLL_INTERVAL = 0.5     # s — polling em vez de sleep fixo
SPOTIFY_PLAY_SETTLE = 1.2       # s — espera antes de reler o título
SPOTIFY_DEVICE_TIMEOUT = 12.0   # s — espera até o app registrar-se como device


def _is_playing_title(title):
    """True se o título da janela indica que há reprodução ativa."""
    if not isinstance(title, str):
        return False
    normalized = title.strip().lower()
    return bool(normalized) and normalized not in SPOTIFY_IDLE_TITLES


def _get_window_title(hwnd):
    """Lê o título de uma janela via Win32."""
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value


def _find_spotify_window():
    """Busca o HWND da janela principal do Spotify pelo PID do processo.

    Buscar por título não serve: tocando, o título é 'Artista - Faixa' e não
    contém a palavra 'Spotify'.
    """
    import psutil  # lazy: o skill_loader importa este módulo no boot

    pids = set()
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            if (proc.info['name'] or "").lower() == SPOTIFY_PROCESS_NAME:
                pids.add(proc.info['pid'])
        except Exception:
            pass

    if not pids:
        return None

    user32 = ctypes.windll.user32
    found_hwnd = None

    def _enum_cb(hwnd, lParam):
        nonlocal found_hwnd
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # O Spotify (Chromium) cria várias janelas fantasma invisíveis / sem título.
        if pid.value in pids and user32.IsWindowVisible(hwnd) and _get_window_title(hwnd):
            found_hwnd = hwnd
            return False  # Para a enumeração
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong, ctypes.c_long)(_enum_cb), 0)
    return found_hwnd


def _wait_for_spotify_window(timeout=SPOTIFY_WINDOW_TIMEOUT):
    """Espera ativa pela janela do Spotify. Substitui o sleep fixo."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = _find_spotify_window()
        if hwnd:
            return hwnd
        time.sleep(SPOTIFY_POLL_INTERVAL)
    return None


def _focus_and_maximize(hwnd):
    """Maximiza a janela e traz para o primeiro plano. Nunca levanta exceção."""
    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, SW_MAXIMIZE)

        # O Windows recusa SetForegroundWindow quando o processo chamador não está
        # em foreground. Um toque em ALT libera a chamada.
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.SetForegroundWindow(hwnd)

        log.debug("🪟 Spotify maximizado e em foco.")
        return True
    except Exception as e:
        log.warning(f"⚠️ Não consegui maximizar o Spotify: {e}")
        return False


def _send_media_play():
    """Envia a tecla de mídia Play/Pause global (fallback)."""
    try:
        user32 = ctypes.windll.user32
        hwcode = user32.MapVirtualKeyA(VK_MEDIA_PLAY_PAUSE, 0)
        user32.keybd_event(VK_MEDIA_PLAY_PAUSE, hwcode, 0, 0)
        user32.keybd_event(VK_MEDIA_PLAY_PAUSE, hwcode, KEYEVENTF_KEYUP, 0)
    except Exception as e:
        log.warning(f"⚠️ Falha ao enviar tecla de mídia: {e}")


def _ensure_playing(hwnd):
    """Garante que há reprodução ativa, SEM pausar o que já estava tocando.

    A tecla de play é um toggle — mandá-la às cegas pausa a música.
    """
    if _is_playing_title(_get_window_title(hwnd)):
        log.debug("🎧 Spotify já está reproduzindo — nada a fazer.")
        return True

    # Tentativa 1: Space na janela focada (toca o contexto aberto)
    try:
        import pyautogui  # lazy: evita custo de import no boot da skill
        _focus_and_maximize(hwnd)
        pyautogui.press('space')
    except Exception as e:
        log.warning(f"⚠️ Falha ao enviar Space para o Spotify: {e}")

    time.sleep(SPOTIFY_PLAY_SETTLE)
    if _is_playing_title(_get_window_title(hwnd)):
        return True

    # Tentativa 2: tecla de mídia global
    log.debug("Space não pegou. Enviando sinal de Play via hardware...")
    _send_media_play()
    time.sleep(SPOTIFY_PLAY_SETTLE)

    if _is_playing_title(_get_window_title(hwnd)):
        return True

    log.warning("⚠️ Spotify aberto na playlist, mas a reprodução não iniciou.")
    return False


def start_uri(uri):
    """Abre uma URI no app local, maximiza a janela e garante o play.

    Caminho de fallback quando a Web API não está disponível (sem autorização,
    sem Premium ou sem internet do lado da API). Nunca levanta exceção.
    """
    import subprocess

    clean_uri = _sanitize_spotify_uri(uri)
    if not clean_uri:
        log.error(f"❌ [SPOTIFY] URI inválida: {uri!r}")
        return False

    try:
        # 'start' exige um argumento de título antes da URI — daí a string vazia.
        subprocess.Popen(
            ["cmd", "/c", "start", "", clean_uri],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception as e:
        log.error(f"❌ [SPOTIFY] Falha ao abrir a URI: {e}")
        return False

    hwnd = _wait_for_spotify_window()
    if not hwnd:
        log.warning(f"⚠️ Janela do Spotify não apareceu em {SPOTIFY_WINDOW_TIMEOUT}s.")
        return False

    _focus_and_maximize(hwnd)
    return _ensure_playing(hwnd)


def launch_app():
    """Abre o Spotify reusando a skill APP_CONTROL. Não espera a janela."""
    try:
        from core.skill_loader import manager
        if "APP_CONTROL" in manager.skills:
            manager.skills["APP_CONTROL"].execute("spotify", "abrir spotify")
            return True
    except Exception as e:
        log.warning(f"⚠️ Não consegui abrir o Spotify pelo APP_CONTROL: {e}")
    return False


def ensure_device_ready():
    """Garante que existe um dispositivo ativo para a Web API comandar.

    Sem isso, o primeiro comando do dia sempre morre em 404 NO_ACTIVE_DEVICE
    porque o Spotify desktop nem sequer está aberto.

    Retorna o device_id pronto para uso, ou None.
    """
    device = _pick_device(spotify.devices(), socket.gethostname())
    if device and device.get("is_active"):
        return device.get("id")

    if device:
        # Existe, mas está dormindo. Basta transferir a sessão para ele.
        if spotify.transfer_playback(device["id"], play=False):
            return device["id"]
        return device.get("id")

    # Nenhum dispositivo: o app está fechado. Abre e espera ele se registrar.
    log.info("🔌 Nenhum dispositivo Spotify ativo. Abrindo o aplicativo...")
    launch_app()
    _wait_for_spotify_window()

    deadline = time.monotonic() + SPOTIFY_DEVICE_TIMEOUT
    while time.monotonic() < deadline:
        device = _pick_device(spotify.devices(), socket.gethostname())
        if device:
            spotify.transfer_playback(device["id"], play=False)
            return device.get("id")
        time.sleep(SPOTIFY_POLL_INTERVAL)

    log.warning("⚠️ O Spotify abriu mas não se registrou como dispositivo.")
    return None
