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

import core.state as state

DEFAULT_TIMEOUT_S = 30

# Resultado de take()
OK, EMPTY, EXPIRED, REPLACED = "ok", "empty", "expired", "replaced"
# Resultado de parse_reply()
YES, NO = "yes", "no"

# Resposta padrão de quem não conseguiu armar (já há outra pergunta aberta).
BUSY_REPLY = "Há outra confirmação aberta, Senhor. Responda a ela primeiro."

_lock = threading.RLock()


def _expired(action, now):
    return now > (action.get("timeout") or 0)


def arm(kind, question, on_confirm, *, target=None, on_decline=None, timeout_s=DEFAULT_TIMEOUT_S,
        clock=time.time):
    """Arma a ação e devolve o id dela; None se já há outra pendente e válida."""
    with _lock:
        now = clock()
        current = state.pending_critical_action
        if current and not _expired(current, now):
            return None
        action_id = uuid.uuid4().hex[:8]
        state.pending_critical_action = {
            "id": action_id, "type": kind, "target": target, "question": question,
            "timeout": now + timeout_s, "on_confirm": on_confirm, "on_decline": on_decline,
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
          "bloquear", "bloqueie", "bloqueia"}
_FILLER = {"senhor", "jarvis", "por", "favor", "agora", "ja", "entao", "o", "a", "os", "as", "ele", "ela",
           "mesmo", "tudo", "la", "ai", "de", "do", "da", "e", "com", "certeza", "em", "frente", "pra", "para"}


def _plain_words(text):
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"\w+", text)


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
