"""Telas da TUI além da conversa (empurradas por /comandos, boot e saída)."""
from frontend.screens.base import JarvisScreen
from frontend.screens.boot import BootScreen
from frontend.screens.house_party import HousePartyScreen, is_trigger
from frontend.screens.log import LogScreen
from frontend.screens.settings import SettingsScreen
from frontend.screens.shutdown import ShutdownScreen
from frontend.screens.skills import SkillsScreen
from frontend.screens.status import StatusScreen
from frontend.screens.vault import VaultScreen

__all__ = [
    "BootScreen", "HousePartyScreen", "JarvisScreen", "LogScreen", "SettingsScreen",
    "ShutdownScreen", "SkillsScreen", "StatusScreen", "VaultScreen", "is_trigger",
]
