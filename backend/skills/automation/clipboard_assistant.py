"""Skill CLIPBOARD — explica, traduz ou resume o que está no clipboard (core.clipboard)."""
import re

from core import clipboard
from core.prompts import load_prompt

INTENT = "CLIPBOARD"
PROMPT_TEXT = load_prompt("skills/clipboard.md")

_VERBS = (("tradu", "translate"), ("resum", "summarize"), ("explic", "explain"))


def requested_action(entity, command):
    text = f"{entity or ''} {command or ''}".lower()
    for stem, action in _VERBS:
        if re.search(rf"\b{stem}", text):
            return action
    return None


def execute(entity, command):
    text = clipboard.read()
    action = requested_action(entity, command) or clipboard.resolve_action(clipboard.classify(text))
    return clipboard.act(action, text)
