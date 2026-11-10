"""Integrações com contas externas — fonte dos cards de /config → INTEGRAÇÕES.

Cada `Integration` sabe dizer seu estado e conectar/desconectar. Estados:

- `on`     conectado (detalhe = conta ou fonte)
- `wait`   conexão em andamento (navegador aberto, esperando o usuário)
- `off`    pronto para conectar
- `setup`  falta configuração no .env (Enter mostra como fazer)

`connect`/`disconnect` são bloqueantes (OAuth espera o navegador): a TUI chama
em worker de thread. Devolvem o texto para mostrar ao usuário; nunca levantam.
"""
import threading
import webbrowser
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.logger import log

ON, WAIT, OFF, SETUP = "on", "wait", "off", "setup"
BADGES = {ON: "CONECTADO", WAIT: "AGUARDANDO", OFF: "DESCONECTADO", SETUP: "CONFIGURAR"}

_waiting = set()
_lock = threading.Lock()


@dataclass
class Integration:
    id: str
    name: str
    desc: str
    status: Callable[[], tuple]                 # -> (estado, detalhe)
    connect: Callable[[], str]
    disconnect: Optional[Callable[[], str]] = None
    connect_label: str = "Conectar"
    extra: dict = field(default_factory=dict)


def _open(url):
    try:
        webbrowser.open(url)
    except Exception as e:
        log.warning(f"Integrações: não consegui abrir o navegador: {e}")


def _already(name, account):
    """Conta já guardada: não abre o login de novo."""
    who = f" ({account})" if account else ""
    return f"{name} já está conectado{who}, Senhor. Para trocar de conta, Del e conecte de novo."


# ------------------------------------------------------------------ GitHub
GITHUB_TOKENS_URL = "https://github.com/settings/tokens"


def _github_status():
    from core import github_client
    if not github_client.is_configured():
        return SETUP, "sem GITHUB_TOKEN no .env"
    return ON, "token do .env (GITHUB_TOKEN)"


def _github_connect():
    from core import github_client
    if github_client.is_configured():
        return "O GitHub já usa o GITHUB_TOKEN do .env, Senhor. Para trocar, edite o .env e reinicie."
    _open(GITHUB_TOKENS_URL)
    return ("Abri a página de tokens do GitHub. Gere um token (escopo `repo`), coloque em "
            "`GITHUB_TOKEN` no .env e reinicie o JARVIS.")


# ----------------------------------------------------------------- Spotify
SPOTIFY_DASHBOARD_URL = "https://developer.spotify.com/dashboard"

def _spotify_status():
    from core.spotify import spotify
    if not spotify.is_configured():
        return SETUP, "falta SPOTIFY_CLIENT_ID no .env"
    if spotify.is_authorized():
        account = spotify.account()
        return ON, f"conta: {account}" if account else "conta conectada"
    return OFF, "entre com sua conta"


def _spotify_connect():
    import core.spotify as sp
    if not sp.spotify.is_configured():
        _open(SPOTIFY_DASHBOARD_URL)
        return ("Falta a sua chave do Spotify, Senhor. Abri o painel de desenvolvedor: crie um app com o "
                "redirect `http://127.0.0.1:8888/callback`, preencha `SPOTIFY_CLIENT_ID` no .env e reinicie "
                "(passo a passo em docs/integracoes-oauth.md).")
    if sp.spotify.is_authorized():
        return _already("Spotify", sp.spotify.account())
    if not sp.start_authorization(blocking=True):
        return "O Spotify não foi autorizado (tempo esgotado ou acesso recusado)."
    account = sp.spotify.account()
    return f"Spotify conectado{f' ({account})' if account else ''}, Senhor."


def _spotify_disconnect():
    import core.spotify as sp
    return "Spotify desconectado." if sp.disconnect() else "Não consegui apagar o token do Spotify."


# ----------------------------------------------------------- Google Agenda
def _calendar_status():
    from core import google_calendar as gc
    if not gc.is_configured():
        return SETUP, "falta GOOGLE_CLIENT_ID no .env"
    if gc.is_connected():
        return ON, f"conta: {gc.account()}" if gc.account() else "conta conectada"
    return OFF, "entre com sua conta"


def _calendar_connect():
    from core import google_calendar as gc
    if not gc.is_configured():
        _open(gc.CONSOLE_URL)
        return gc.NOT_CONFIGURED
    if gc.is_connected():
        return _already("Google Agenda", gc.account())
    return gc.connect()


def _calendar_disconnect():
    from core import google_calendar as gc
    return gc.disconnect()


# ---------------------------------------------------------------- Trânsito
def _traffic_status():
    from core import traffic
    if not traffic.has_places():
        return SETUP, "use /rota casa|trabalho"
    if traffic.source_name() == "TomTom":
        return ON, "TomTom · trânsito ao vivo"
    return ON, "OSRM grátis · TomTom opcional"


def _traffic_connect():
    from core import traffic
    if not traffic.has_places():
        return traffic.NO_PLACES
    if traffic.source_name() == "OSRM":
        _open(traffic.TOMTOM_SIGNUP_URL)
        return ("Rota definida (OSRM, sem trânsito ao vivo). Para trânsito real, crie uma chave grátis "
                "no TomTom, coloque em `TOMTOM_API_KEY` no .env e reinicie.")
    return "Trânsito ao vivo pelo TomTom já está ativo, Senhor."


def _traffic_disconnect():
    from core import traffic
    traffic.clear_places()
    return "Endereços de casa e trabalho apagados."


# --------------------------------------------------------------- registro
def _build():
    return [
        Integration("google_calendar", "Google Agenda", "Agenda no briefing e por voz.",
                    _calendar_status, _calendar_connect, _calendar_disconnect),
        Integration("github", "GitHub", "PRs, issues e CI (/gh).",
                    _github_status, _github_connect, connect_label="Como configurar"),
        Integration("spotify", "Spotify", "Música pela skill de mídia.",
                    _spotify_status, _spotify_connect, _spotify_disconnect),
        Integration("traffic", "Trânsito", "Casa ⇄ trabalho no briefing.",
                    _traffic_status, _traffic_connect, _traffic_disconnect, connect_label="Trânsito ao vivo"),
    ]


_registry = []


def all_integrations():
    if not _registry:
        _registry.extend(_build())
    return list(_registry)


def get(integration_id):
    return next((i for i in all_integrations() if i.id == integration_id), None)


def state_of(integration):
    """(estado, detalhe) — com o `wait` da conexão em andamento por cima."""
    with _lock:
        if integration.id in _waiting:
            return WAIT, "aguardando o navegador"
    try:
        return integration.status()
    except Exception as e:
        log.warning(f"Integração '{integration.id}': status falhou: {e}")
        return SETUP, "indisponível (veja o /log)"


def is_waiting(integration_id):
    with _lock:
        return integration_id in _waiting


def connect(integration_id, on_started=None):
    """Bloqueante. Marca `wait` enquanto roda (e avisa `on_started()` logo depois,
    para a TUI pintar o card como AGUARDANDO). Devolve o texto para o usuário."""
    integration = get(integration_id)
    if integration is None:
        return "Integração desconhecida."
    with _lock:
        if integration_id in _waiting:
            return f"{integration.name}: já estou esperando a autorização no navegador."
        _waiting.add(integration_id)
    try:
        if on_started is not None:
            on_started()
        return integration.connect()
    except Exception as e:
        log.error(f"Integração '{integration_id}': conexão falhou: {e}")
        return f"Não consegui conectar o {integration.name}: {e}"
    finally:
        with _lock:
            _waiting.discard(integration_id)


def disconnect(integration_id):
    integration = get(integration_id)
    if integration is None:
        return "Integração desconhecida."
    if integration.disconnect is None:
        return f"{integration.name} não tem o que desconectar por aqui."
    try:
        return integration.disconnect()
    except Exception as e:
        log.error(f"Integração '{integration_id}': desconexão falhou: {e}")
        return f"Não consegui desconectar o {integration.name}: {e}"
