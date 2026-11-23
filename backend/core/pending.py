"""Ação crítica pendente — a única porta de entrada de `state.pending_critical_action`.

Uma ação de cada vez (encerrar processo, criar issue, desligar…), com prazo. Quem
arma é uma skill ou uma rotina de fundo (alerta de hardware, vigia de rede); quem
resolve é o `ConfirmScreen` da TUI ou a próxima frase do usuário, via
`services.brain.confirm_pending_action`.

Regras (Security Advisories GHSA-x47w e GHSA-48jx):
- `arm()` nunca sobrescreve uma pendência ainda válida: devolve None e quem chamou
  decide (anunciar sem pergunta, tentar depois, avisar o usuário). Sem isso, um
  alerta trocava a ação e o "sim" dado a uma pergunta executava outra.
- Toda pendência tem `id`. Quem abriu a pergunta confirma aquele id; se ela foi
  trocada no meio do caminho, `take()` responde REPLACED e nada é executado.
- `parse_reply()` só aceita como "sim" uma frase feita SÓ de vocabulário de
  confirmação. "pode me dizer o clima?" não aprova nada.

O dict continua morando em `state.pending_critical_action` (testes antigos o
atribuem direto; dicts sem `id` seguem funcionando como antes).
"""
import re
import threading
import time
import unicodedata
import uuid
from contextlib import contextmanager

import core.state as state

DEFAULT_TIMEOUT_S = 30

# Dono padrão: a TUI/voz deste processo. A ponte Telegram/Discord usa "canal:usuário".
LOCAL = "local"

# Resultado de take()
OK, EMPTY, EXPIRED, REPLACED = "ok", "empty", "expired", "replaced"
# Resultado de parse_reply()
YES, NO = "yes", "no"

# Resposta padrão de quem não conseguiu armar (já há outra pergunta aberta).
BUSY_REPLY = "Há outra confirmação aberta, Senhor. Responda a ela primeiro."

_lock = threading.RLock()
_ctx = threading.local()   # dono de quem está rodando a skill nesta thread


def current_owner():
    return getattr(_ctx, "owner", LOCAL)


@contextmanager
def owner_scope(owner):
    """Tudo o que for armado dentro do bloco (pela skill) fica com este dono."""
    previous = current_owner()
    _ctx.owner = owner or LOCAL
    try:
        yield
    finally:
        _ctx.owner = previous


def _expired(action, now):
    return now > (action.get("timeout") or 0)


def arm(kind, question, on_confirm, *, target=None, on_decline=None, timeout_s=DEFAULT_TIMEOUT_S,
        clock=time.time, owner=None, on_other=None):
    """Arma a ação e devolve o id dela; None se já há outra pendente e válida.

    `owner`: só uma resposta do mesmo dono resolve a pendência (um "sim" no Telegram
    nunca aprova o que foi armado para outra pessoa/canal).
    `on_other(frase)`: chamado quando a resposta não é sim nem não (ex.: "deixa mais
    formal" diante de um rascunho de e-mail) — pode re-armar e devolver o texto."""
    with _lock:
        now = clock()
        current = state.pending_critical_action
        if current and not _expired(current, now):
            return None
        action_id = uuid.uuid4().hex[:8]
        state.pending_critical_action = {
            "id": action_id, "type": kind, "target": target, "question": question,
            "timeout": now + timeout_s, "on_confirm": on_confirm, "on_decline": on_decline,
            "owner": owner or current_owner(), "on_other": on_other,
        }
        return action_id


def active(clock=time.time):
    """A pendência válida, ou None (a vencida é descartada aqui)."""
    with _lock:
        current = state.pending_critical_action
        if not current:
            return None
        if _expired(current, clock()):
            state.pending_critical_action = None
            return None
        return current


def take(pending_id=None, clock=time.time):
    """Retira a pendência de forma atômica → (ação | None, OK | EMPTY | EXPIRED | REPLACED).

    Com `pending_id`, só retira se for a mesma pendência; se outra tomou o lugar,
    ela fica intacta e o resultado é REPLACED."""
    with _lock:
        current = state.pending_critical_action
        if not current:
            return None, EMPTY
        if pending_id is not None and current.get("id") != pending_id:
            return None, REPLACED
        state.pending_critical_action = None
        if _expired(current, clock()):
            return None, EXPIRED
        return current, OK


# --------------------------------------------------------------- resposta do usuário
_DENY = {"nao", "mantenha", "manter", "mantem", "deixa", "deixe", "cancela", "cancele", "cancelar",
         "aborta", "aborte", "abortar", "negativo", "nunca"}
_AFFIRM = {"sim", "s", "pode", "ok", "okay", "confirmo", "confirma", "confirmado", "autorizo", "autorizado",
           "claro", "afirmativo", "positivo", "isso", "manda", "vai", "faca", "faz", "certo", "beleza"}
_VERBS = {"encerrar", "encerre", "encerra", "fechar", "feche", "fecha", "matar", "mate", "mata",
          "finalizar", "finalize", "finaliza", "terminar", "termine", "termina", "criar", "crie", "cria",
          "prosseguir", "prossiga", "prossegue", "seguir", "siga", "segue", "continuar", "continue",
          "continua", "desligar", "desligue", "desliga", "executar", "execute", "executa",
          "bloquear", "bloqueie", "bloqueia", "mandar", "mande", "enviar", "envie", "envia", "aplicar",
          "aplique", "aplica", "organizar", "organize", "organiza", "instalar", "instale", "instala",
          "baixar", "baixe", "baixa"}
_FILLER = {"senhor", "jarvis", "por", "favor", "agora", "ja", "entao", "o", "a", "os", "as", "ele", "ela",
           "mesmo", "tudo", "la", "ai", "de", "do", "da", "e", "com", "certeza", "em", "frente", "pra", "para"}


def _plain_words(text):
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"\w+", text)


def is_pure_denial(text):
    """Frase feita só de negação/enchimento ("não", "não, cancela") — sem pedido de ajuste."""
    words = _plain_words(text)
    return bool(words) and all(w in _DENY or w in _FILLER for w in words)


def parse_reply(text, target=None):
    """YES, NO ou None (a frase não é uma resposta → a pendência é descartada).

    - qualquer negação vence ("não, pode manter" = NO);
    - pergunta (com "?") nunca é aprovação;
    - YES só se todas as palavras forem confirmação, verbo de ação, enchimento ou
      parte do alvo ("sim, pode encerrar o chrome") e houver ao menos uma
      confirmação ou verbo. "pode tocar música" não aprova.
    """
    words = _plain_words(text)
    if not words:
        return None
    if any(w in _DENY for w in words):
        return NO
    if "?" in (text or ""):
        return None
    allowed = _AFFIRM | _VERBS | _FILLER | set(_plain_words(target or ""))
    if all(w in allowed for w in words) and any(w in _AFFIRM or w in _VERBS for w in words):
        return YES
    return None
