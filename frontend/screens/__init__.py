"""Telas cheias da TUI (empurradas por /comandos; Esc volta à conversa)."""
from frontend.screens.base import JarvisScreen
from frontend.screens.log import LogScreen
from frontend.screens.skills import SkillsScreen
from frontend.screens.status import StatusScreen

__all__ = ["JarvisScreen", "LogScreen", "SkillsScreen", "StatusScreen"]
