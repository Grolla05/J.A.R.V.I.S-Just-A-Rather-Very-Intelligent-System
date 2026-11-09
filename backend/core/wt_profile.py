"""Perfil "JARVIS" do Windows Terminal (logo do JARVIS na aba).

A linha de comando do `wt` não aceita ícone; ele vem de um perfil. Em vez de
mexer no settings.json do usuário, gravamos um *fragment* em
%LOCALAPPDATA%\\Microsoft\\Windows Terminal\\Fragments\\JARVIS\\jarvis.json, que o
WT mescla sozinho. O launcher (`core/launcher.py`) e o `jarvis.cmd` abrem a aba
com `-p JARVIS` quando o fragment existe.

Limitação do WT: o botão "+" e o menu ⌄ não podem ser escondidos por janela.

Leve de propósito (usado pelo agente residente): só importa `config` e `logger`.
"""
import json
import os
from pathlib import Path

from .config import settings
from .logger import log

PROFILE_NAME = "JARVIS"
PROFILE_GUID = "{6a2b1f3e-7c4d-4e8a-9b1f-4a5e2d7c9b30}"  # fixo: o WT guarda ajustes por guid
FRAGMENT_APP = "JARVIS"
FRAGMENT_FILE = "jarvis.json"


def fragment_path(local_appdata=None):
    """Caminho do fragment, ou None fora do Windows/sem LOCALAPPDATA."""
    base = local_appdata or os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    return Path(base) / "Microsoft" / "Windows Terminal" / "Fragments" / FRAGMENT_APP / FRAGMENT_FILE


def icon_path():
    """jarvis.ico: ao lado do jarvis.cmd (instalado) ou em installer/assets (dev)."""
    if settings.IS_INSTALLED:
        return settings.DIR_ROOT.parent / "jarvis.ico"
    return settings.DIR_ROOT / "installer" / "assets" / "jarvis.ico"


def build_fragment(icon, starting_directory):
    return {
        "profiles": [{
            "guid": PROFILE_GUID,
            "name": PROFILE_NAME,
            "icon": str(icon),
            "tabTitle": PROFILE_NAME,
            "suppressApplicationTitle": True,
            "startingDirectory": str(starting_directory),
        }]
    }


def ensure_profile(local_appdata=None):
    """Grava/atualiza o fragment (só se mudou). True se o perfil está disponível."""
    path = fragment_path(local_appdata)
    icon = icon_path()
    if path is None or not icon.exists():
        return False
    content = json.dumps(build_fragment(icon, settings.DIR_BACKEND), indent=2, ensure_ascii=False)
    try:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return True
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        log.info(f"Perfil '{PROFILE_NAME}' do Windows Terminal gravado em {path}")
        return True
    except OSError as e:
        log.debug(f"Fragment do Windows Terminal indisponível: {e}")
        return False
