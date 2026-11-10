"""Atualização automática do JARVIS instalado — só no logon do Windows.

O agente residente sobe com o Windows com `--logon` (valor `JARVIS` em
HKCU\\...\\Run). Só nessa hora ele chama `check_and_update()`: compara o
VERSION instalado com o último Release do GitHub (`UPDATE_REPO`) e, se houver
versão nova, baixa o `JARVIS-Setup.exe`, confere o SHA-256 publicado pelo
GitHub (`digest` do asset) e roda o setup em silêncio com `/UPDATE`. O agente
então se fecha (o pythonw dele trava os arquivos do runtime) e o setup o
reabre ao terminar. Abrir pela bandeja, Win+J ou menu Iniciar não verifica.

Em modo dev (sem JARVIS_DATA_DIR) não faz nada: ali quem atualiza é o git.
Liga/desliga em /config → SISTEMA (registro HKCU\\Software\\JARVIS\\AutoUpdate);
o padrão vem de AUTO_UPDATE no .env. Leve: só `config`, `logger` e `requests`
(o agente não carrega o pacote `core` inteiro).
"""
import hashlib
import json
import re
import subprocess

from .config import settings
from .logger import log

API_URL = "https://api.github.com/repos/{repo}/releases/latest"
ASSET_NAME = "JARVIS-Setup.exe"
SETUP_ARGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SKIPOLLAMA", "/UPDATE")
RETRY_DELAYS = (15, 45, 90, 180)  # logo após o logon a rede pode não estar pronta
HTTP_TIMEOUT = 20
MAX_ASSET_BYTES = 1024 ** 3
CHUNK = 1024 * 1024
MARKER_NAME = "pending_update.json"
TITLE = "J.A.R.V.I.S — atualização"

REG_KEY = r"Software\JARVIS"
REG_VALUE = "AutoUpdate"

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


class UpdateError(Exception):
    """Release inválido ou download que não confere."""


# ------------------------------------------------------------------ versões
def parse_version(text):
    """'v1.2.3' / '1.2.3' -> (1, 2, 3); qualquer outra coisa -> None."""
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", (text or "").strip())
    return tuple(int(n) for n in m.groups()) if m else None


def is_newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


# ------------------------------------------------------------ liga/desliga
def _winreg():
    try:
        import winreg
        return winreg
    except ImportError:  # pragma: no cover - só Windows
        return None


def is_enabled():
    reg = _winreg()
    if reg is not None:
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, REG_KEY) as key:
                value, _kind = reg.QueryValueEx(key, REG_VALUE)
                return bool(value)
        except OSError:
            pass
    return bool(settings.AUTO_UPDATE)


def set_enabled(on):
    reg = _winreg()
    if reg is None:
        return False
    try:
        with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, REG_KEY, 0, reg.KEY_SET_VALUE) as key:
            reg.SetValueEx(key, REG_VALUE, 0, reg.REG_DWORD, 1 if on else 0)
        log.info(f"Atualização automática {'ligada' if on else 'desligada'}.")
        return True
    except OSError as e:
        log.error(f"Falha ao gravar a atualização automática: {e}")
        return False


# ------------------------------------------------------------------ GitHub
def _requests():
    import requests
    return requests


def fetch_latest(get=None, repo=None):
    """Último Release: {"version", "url", "size", "sha256"} ou None (sem
    setup/tag válida). Erro de rede sobe como requests.RequestException."""
    repo = repo or settings.UPDATE_REPO
    get = get or _requests().get
    resp = get(API_URL.format(repo=repo), timeout=HTTP_TIMEOUT,
               headers={"Accept": "application/vnd.github+json", "User-Agent": "JARVIS-updater"})
    if resp.status_code == 404:
        return None  # repositório sem Release ainda
    resp.raise_for_status()
    data = resp.json()
    tag = str(data.get("tag_name", ""))
    if data.get("draft") or data.get("prerelease") or not parse_version(tag):
        return None
    for asset in data.get("assets") or ():
        if asset.get("name") != ASSET_NAME:
            continue
        url = str(asset.get("browser_download_url", ""))
        if not url.startswith(f"https://github.com/{repo}/releases/download/"):
            raise UpdateError(f"URL do setup fora do repositório: {url[:80]}")
        digest = str(asset.get("digest") or "")
        if not digest.startswith("sha256:"):
            raise UpdateError("release sem SHA-256 do setup (digest)")
        return {"version": tag.lstrip("v"), "url": url, "size": int(asset.get("size") or 0),
                "sha256": digest.split(":", 1)[1].lower()}
    return None


def updates_dir():
    return settings.DIR_DATA / "updates"


def download(release, dest_dir=None, get=None):
    """Baixa o setup e confere tamanho + SHA-256. Devolve o Path; se não
    conferir, apaga o arquivo e levanta UpdateError."""
    dest_dir = dest_dir or updates_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"JARVIS-Setup-{release['version']}.exe"
    get = get or _requests().get
    sha = hashlib.sha256()
    total = 0
    try:
        with get(release["url"], stream=True, timeout=HTTP_TIMEOUT,
                 headers={"User-Agent": "JARVIS-updater"}) as resp:
            resp.raise_for_status()
            with open(path, "wb") as fh:
                for chunk in resp.iter_content(CHUNK):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_ASSET_BYTES:
                        raise UpdateError("setup maior que o limite")
                    sha.update(chunk)
                    fh.write(chunk)
        if release.get("size") and total != release["size"]:
            raise UpdateError(f"tamanho não confere ({total} != {release['size']})")
        if sha.hexdigest() != release["sha256"]:
            raise UpdateError("SHA-256 do setup não confere")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def cleanup(dest_dir=None):
    """Apaga setups baixados em logons anteriores."""
    dest_dir = dest_dir or updates_dir()
    for old in dest_dir.glob("JARVIS-Setup-*.exe") if dest_dir.is_dir() else ():
        try:
            old.unlink()
        except OSError as e:
            log.debug(f"Setup antigo preso ({old.name}): {e}")


def launch_setup(path, popen=None):
    popen = popen or subprocess.Popen
    popen([str(path), *SETUP_ARGS], cwd=str(path.parent),
          creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, close_fds=True)


# --------------------------------------------------- aviso pós-atualização
def _marker_path():
    return updates_dir() / MARKER_NAME


def announce_result(notify):
    """Depois do setup reabrir o agente: avisa se a versão nova entrou."""
    marker = _marker_path()
    if not marker.exists():
        return None
    try:
        target = json.loads(marker.read_text(encoding="utf-8")).get("version", "")
    except (OSError, ValueError):
        target = ""
    marker.unlink(missing_ok=True)
    current = parse_version(settings.VERSION)
    wanted = parse_version(target)
    if wanted and current and current >= wanted:
        notify(f"Atualizado para a versão {settings.VERSION}, Senhor.", TITLE)
        log.info(f"✅ Atualização para v{settings.VERSION} concluída.")
        return "updated"
    log.warning(f"Atualização para v{target} não concluiu (instalada: v{settings.VERSION}).")
    return "not-updated"


# ------------------------------------------------------------------ fluxo
def check_and_update(notify, tui_open, sleep, get=None, popen=None):
    """Verifica e, se precisar, dispara o setup. Devolve o status; com
    'installing' quem chamou deve encerrar o agente."""
    if not settings.IS_INSTALLED:
        return "dev"
    if not is_enabled():
        return "disabled"
    current = settings.VERSION
    if not parse_version(current):
        log.warning(f"VERSION inválido ({current!r}): atualização automática ignorada.")
        return "unknown-version"
    cleanup()
    requests = _requests()
    release = None
    for delay in (0, *RETRY_DELAYS):
        if delay:
            sleep(delay)
        try:
            release = fetch_latest(get)
            break
        except requests.RequestException as e:
            log.debug(f"Atualização: GitHub indisponível ({e}); tentando de novo.")
        except (UpdateError, ValueError) as e:
            log.warning(f"Atualização: release inválido ({e}).")
            return "failed"
    else:
        log.info("Atualização: sem rede depois das tentativas; fica para o próximo logon.")
        return "offline"
    if not release:
        return "no-release"
    if not is_newer(release["version"], current):
        log.info(f"Atualização: v{current} já é a mais recente.")
        return "up-to-date"
    if tui_open():
        log.info(f"Atualização v{release['version']} adiada: a TUI está aberta.")
        return "deferred"
    notify(f"Baixando a versão {release['version']} (instalada: {current})…", TITLE)
    try:
        path = download(release, get=get)
    except (UpdateError, requests.RequestException, OSError) as e:
        log.warning(f"Atualização: download falhou ({e}).")
        notify("Não consegui baixar a atualização. Tento no próximo logon.", TITLE)
        return "failed"
    try:
        _marker_path().write_text(json.dumps({"version": release["version"], "from": current}),
                                  encoding="utf-8")
        launch_setup(path, popen)
    except OSError as e:
        log.warning(f"Atualização: não consegui abrir o setup ({e}).")
        _marker_path().unlink(missing_ok=True)
        return "failed"
    log.info(f"🔄 Instalando v{release['version']} (era v{current}); o agente fecha e o setup o reabre.")
    notify(f"Instalando a versão {release['version']}. Volto em instantes.", TITLE)
    return "installing"
