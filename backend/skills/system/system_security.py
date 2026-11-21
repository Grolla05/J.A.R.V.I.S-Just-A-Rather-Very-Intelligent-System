# ⚠️ ACESSO SENSÍVEL: bloqueia a estação, suspende e desliga o Windows. Ver SECURITY.md.
import ctypes
import json
import subprocess
import threading
import time

from core import log, pending
from core.config import settings
from core.llm import query_ollama
from core.prompts import load_prompt

# --- CONFIGURAÇÃO DA SKILL ---
INTENT = "SYSTEM_SECURITY"
PROMPT_TEXT = load_prompt("skills/system_security.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("deslig*", "bloque*", "suspend*", "hibern*", "sentinela", "afk", "proteg*", "power down", "reinici*")

# --- CÉREBRO ESPECÍFICO DA SKILL ---
SECURITY_DECISION_PROMPT = load_prompt("skills/system_security_decision.md")

SHUTDOWN_DELAY_S = 15
POWER_DOWN_QUESTION = f"Desligar o computador em {SHUTDOWN_DELAY_S} segundos?"


# --- FUNÇÃO LOCAL DE LLM ---
def _ask_ollama_security(user_text):
    # core.llm normaliza OLLAMA_HOST e trata erro (devolve None).
    return query_ollama([{"role": "system", "content": SECURITY_DECISION_PROMPT},
                         {"role": "user", "content": user_text}],
                        format="json", temperature=0.1, timeout=settings.TIMEOUT_API)


# --- HELPERS DE HARDWARE ---
def _stop_media():
    """Envia o comando de parada de mídia para o sistema."""
    try:
        # VK_MEDIA_PLAY_PAUSE = 0xB3 (Mais universal para parar o que estiver tocando)
        ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)  # Press
        ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0)  # Release
        log.debug("🎵 Mídia interrompida via Sentinela.")
    except Exception:
        pass


def _delayed_lock(delay=2.0):
    """Bloqueia a tela após um pequeno delay para permitir que a fala inicial comece."""
    def lock():
        time.sleep(delay)
        ctypes.windll.user32.LockWorkStation()
        log.info("🔒 Estação bloqueada via Modo Sentinela.")

    threading.Thread(target=lock, daemon=True).start()


# --- AÇÕES DE SEGURANÇA ---
def sentry_mode():
    """Protocolo 'Proteger a Estação': Para mídia, avisa e bloqueia."""
    log.warning("🛡️ [SECURITY] ATIVANDO MODO SENTINELA")
    _stop_media()

    # Agenda o bloqueio para daqui a 3 segundos (tempo do J.A.R.V.I.S falar)
    _delayed_lock(delay=3.5)

    return "Protocolo Sentinela ativado. Interrompendo fluxos de mídia e protegendo perímetros da estação. Tenha um bom descanso, senhor."


def suspend_system():
    """Coloca o sistema em modo de suspensão (Sleep)."""
    try:
        log.info("💤 Iniciando suspensão do sistema...")
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=False)
        return "Entrando em modo de baixo consumo. Até breve, senhor."
    except Exception as e:
        log.error(f"Erro ao suspender: {e}")
        return "Não consegui suspender o sistema via comando."


def _shutdown():
    """Só roda depois do "sim" do usuário (ConfirmScreen ou voz), via core.pending."""
    log.warning("🚀 [SECURITY] Desligamento confirmado pelo usuário.")
    try:
        subprocess.run(["shutdown", "/s", "/t", str(SHUTDOWN_DELAY_S),
                        "/c", "J.A.R.V.I.S: Núcleo desenergizado."], check=False)
    except Exception as e:
        log.error(f"Erro ao desligar: {e}")
        return "Não consegui iniciar o desligamento, senhor."
    return (f"Iniciando sequência de desenergização total do núcleo em {SHUTDOWN_DELAY_S} segundos. "
            "Foi um prazer servi-lo, senhor. Sistemas offline.")


def power_down_protocol():
    """Desligar SEMPRE passa pela confirmação do usuário (GHSA-ph22), nunca por um
    campo do LLM. Lixeira e %TEMP% ficam com a skill SYSTEM_CLEANUP."""
    if pending.arm("POWER_DOWN", POWER_DOWN_QUESTION, _shutdown) is None:
        return pending.BUSY_REPLY
    return f"⚠️ {POWER_DOWN_QUESTION} Diga **sim** para confirmar."


_ACTIONS = {"sentry_mode": sentry_mode, "suspend": suspend_system, "power_down": power_down_protocol}


def _fallback(cmd_lower):
    """Sem resposta do modelo: palavras-chave. Na dúvida, não faz nada."""
    if any(x in cmd_lower for x in ["sentinela", "proteger", "vou sair"]):
        return sentry_mode()
    if any(x in cmd_lower for x in ["desligar", "desliga", "power down", "núcleo"]):
        return power_down_protocol()
    if any(x in cmd_lower for x in ["dormir", "suspender", "descansar"]):
        return suspend_system()
    return "Não compreendi o protocolo de segurança solicitado."


# --- EXECUÇÃO PRINCIPAL ---
def execute(entity, command):
    log.info(f"🛡️ [SECURITY] Analisando comando: '{command}'")
    ai_response = _ask_ollama_security(command)
    if not ai_response:
        return _fallback((command or "").lower())

    try:
        action = json.loads(ai_response).get("action")
    except (TypeError, ValueError, AttributeError) as e:
        log.error(f"Erro Security: {e}")
        return "Falha crítica no módulo de segurança física."

    log.info(f"🤖 Decisão de Segurança: {action}")
    handler = _ACTIONS.get(action)
    return handler() if handler else "Não compreendi o protocolo de segurança solicitado."
