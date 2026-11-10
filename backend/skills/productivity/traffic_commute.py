"""Skill TRAFFIC — tempo entre os locais fixos cadastrados com `/rota` (core.traffic). Sem LLM.

O classificador decide QUANDO usar a skill; aqui a frase vira origem → destino:
- dois locais citados: "da faculdade pra casa" (marcas de/para definem o sentido);
- um local: é o destino ("quanto tempo até a escola?"), ou a origem se vier com
  "de/da/do/saindo"; o outro ponto é casa/trabalho pelo horário (core.traffic.direction);
- nenhum: casa ⇄ trabalho pelo horário, como antes;
- local citado pelo classificador mas não cadastrado: avisa como cadastrar.
"""
import re

from core import traffic
from core.prompts import load_prompt

INTENT = "TRAFFIC"
PROMPT_TEXT = load_prompt("skills/traffic.md")

_FROM_RE = re.compile(r"\b(de|da|do|desde|saindo d[aeo])\s*$")
_TO_RE = re.compile(r"\b(pra|para|ate|ao|a|pro|na|no|em)\s*(a|o)?\s*$")
_IGNORED_ENTITIES = {"", "null", "none", "transito", "transito agora", "rota"}


def mentions(text, tags):
    """[(posição, tag)] dos locais cadastrados citados na frase, em ordem."""
    plain = traffic._plain(text)
    found = {}
    for word in re.finditer(r"[a-z0-9]+", plain):
        tag = traffic.normalize_tag(word.group())
        if tag in tags:
            found.setdefault(tag, word.start())
    for tag in tags:  # locais de várias palavras ("casa da mae")
        label = traffic.tag_label(tag)
        pos = plain.find(label)
        if " " in label and pos >= 0:
            found.setdefault(tag, pos)
    return sorted((pos, tag) for tag, pos in found.items())


def _before(plain, pos):
    return plain[max(0, pos - 14):pos]


def decide(command, tags, now=None):
    """(origem, destino) ou None (casa ⇄ trabalho pelo horário)."""
    plain = traffic._plain(command)
    found = mentions(command, tags)
    home, work = traffic.direction(now)
    if len(found) >= 2:
        (pos_a, a), (pos_b, b) = found[0], found[1]
        if _TO_RE.search(_before(plain, pos_a)) and _FROM_RE.search(_before(plain, pos_b)):
            a, b = b, a
        return a, b
    if len(found) == 1:
        pos, tag = found[0]
        other = home if tag != home else work
        if _FROM_RE.search(_before(plain, pos)):
            return tag, other
        return other, tag
    return None


def execute(entity, command):
    places = traffic.list_places()
    tags = list(places)
    pair = decide(f"{command or ''} {entity or ''}", tags)
    if pair is None:
        # Classificador apontou um local (uma palavra) que não está cadastrado → explica como cadastrar
        # (só se a frase usar o nome como lugar: "até a academia", "da academia")
        word = traffic._plain(entity or "")
        unknown = traffic.normalize_tag(word)
        as_place = re.search(rf"\b(pra|para|ate|ao|pro|de|da|do|na|no)\s+(a\s+|o\s+)?{re.escape(word)}\b",
                             traffic._plain(command)) if word else None
        if as_place and word not in _IGNORED_ENTITIES and len(unknown) >= 3 and unknown not in tags:
            return traffic.trip_text(traffic.direction()[0], unknown)
        return traffic.commute_text()
    return traffic.trip_text(*pair)
