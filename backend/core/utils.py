"""Utilitários compartilhados do core."""
import re
import time
import unicodedata
from collections import OrderedDict


class TTLCache:
    """Cache LRU com expiração por tempo (TTL).

    - LRU: ao exceder `maxsize`, descarta a entrada usada há mais tempo.
    - TTL: entradas vencidas são tratadas como ausentes (e removidas no acesso).

    Genérico e sem dependências pesadas — usado p/ memoizar classify_intent.
    `time_fn` é injetável para facilitar testes determinísticos.
    """

    def __init__(self, maxsize=64, ttl=30, time_fn=time.time):
        self.maxsize = maxsize
        self.ttl = ttl
        self._time = time_fn
        self._store = OrderedDict()  # key -> (value, expiry_ts)

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if self._time() >= expiry:
            # Vencida: remove e trata como miss
            del self._store[key]
            return None
        self._store.move_to_end(key)  # marca como recém-usada (LRU)
        return value

    def set(self, key, value):
        self._store[key] = (value, self._time() + self.ttl)
        self._store.move_to_end(key)
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)  # remove a mais antiga

    def clear(self):
        self._store.clear()


def plain(text):
    """Minúsculas e sem acentos (NFKD) — base para casar palavras-chave."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def word_regex(words):
    """Regex que casa qualquer termo de `words` como palavra inteira (sobre `plain`).

    Termos mais longos primeiro, para "quem sou" vencer "quem". Ex.: "age" não
    casa com "agenda", "meta" não casa com "metade".
    """
    terms = sorted({plain(w) for w in words if w}, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b")
