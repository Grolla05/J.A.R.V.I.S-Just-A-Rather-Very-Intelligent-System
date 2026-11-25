"""Download inteligente: "instala o 7-zip" / "baixa o instalador do vlc" pelo winget.

Busca no catálogo oficial (`core/winget.py`) → escolhe o pacote → **pede confirmação**
(nome, id e versão à vista) → instala/baixa numa thread daemon e anuncia o fim.
Sem pacote claro, lista as opções e não arma nada.
"""
import re
import threading
import unicodedata
from pathlib import Path

from core import pending, winget
from core.logger import log

INSTALL, DOWNLOAD = "install", "download"
CONFIRM_TIMEOUT_S = 60
_DOWNLOAD_RE = re.compile(r"\b(baix\w*|download\w*)\b")
_FILLER = re.compile(r"\b(instal\w*|baix\w*|download\w*|o|a|os|as|um|uma|de|do|da|pra|para|mim|me|por favor|"
                     r"jarvis|instalador|programa|app|aplicativo|software|ai|agora|no|na|meu|computador|pc)\b")


def _plain(text):
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def parse_command(command):
    """('install'|'download', nome do software) a partir da frase."""
    plain = _plain(command)
    action = DOWNLOAD if _DOWNLOAD_RE.search(plain) else INSTALL
    name = " ".join(_FILLER.sub(" ", plain).split()).strip(" ,.!?")
    return action, name


def _announce(text):
    import core.state as state
    try:
        state.announce(text)
    except Exception as e:
        log.debug(f"[WINGET] Aviso não entregue: {e}")


def _run_background(fn):
    threading.Thread(target=fn, name="jarvis-winget", daemon=True).start()


def _downloads():
    return Path.home() / "Downloads"


def _do(action, item):
    label = f"{item['name']} ({item['id']})"

    def job():
        if action == INSTALL:
            ok, out = winget.install(item["id"])
            _announce(f"{label} instalado, Senhor." if ok else f"A instalação de {label} falhou, Senhor: {out}")
        else:
            dest = _downloads()
            ok, out = winget.download(item["id"], dest)
            _announce(f"Instalador de {label} baixado em {dest}, Senhor." if ok
                      else f"O download de {label} falhou, Senhor: {out}")

    _run_background(job)
    verb = "Instalando" if action == INSTALL else "Baixando o instalador de"
    return f"{verb} {label}. Aviso quando terminar, Senhor."


def options_text(query, items):
    lines = [f"Não sei qual destes é o **{query}**, Senhor. Peça de novo com o nome exato:", ""]
    lines += [f"{i}. {it['name']} · `{it['id']}` · v{it['version']}" for i, it in enumerate(items, 1)]
    return "\n".join(lines)


def request(query, action=INSTALL, owner=None):
    """Busca e arma a confirmação. Devolve o texto para o usuário."""
    query = (query or "").strip()
    if not query:
        return "Qual programa, Senhor?"
    if not winget.available():
        return "O winget não está disponível neste Windows, Senhor. Instale o \"App Installer\" pela Microsoft Store."
    items = winget.search(query)
    if not items:
        return f"Não encontrei **{query}** no catálogo do winget, Senhor."
    item = winget.best_match(query, items)
    if not item:
        return options_text(query, items[:6])
    verb = "Instalar" if action == INSTALL else "Baixar o instalador de"
    where = "" if action == INSTALL else f" para {_downloads()}"
    question = (f"{verb} **{item['name']}** (`{item['id']}`, v{item['version']}){where} pelo winget? "
                "(**sim** / **não**)")
    armed = pending.arm("SOFTWARE_INSTALL", question, lambda a=action, it=item: _do(a, it), target=item["name"],
                        on_decline=lambda: "Nada instalado, Senhor.", timeout_s=CONFIRM_TIMEOUT_S, owner=owner)
    return question if armed else pending.BUSY_REPLY
