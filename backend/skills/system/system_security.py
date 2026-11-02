import ctypes
import glob
import json
import os
import shutil
import threading
import time

import requests

from core import log
from core.config import settings
from core.prompts import load_prompt

_state = {"awaiting_power_down": False}

# --- CONFIGURAÇÃO DA SKILL ---
INTENT = "SYSTEM_SECURITY"
PROMPT_TEXT = load_prompt("skills/system_security.md")

# --- CÉREBRO ESPECÍFICO DA SKILL ---
SECURITY_DECISION_PROMPT = load_prompt("skills/system_security_decision.md")

# --- FUNÇÃO LOCAL DE LLM ---
def _ask_ollama_security(user_text):
    url = f"http://{settings.OLLAMA_HOST}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": user_text,
        "system": SECURITY_DECISION_PROMPT,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1}
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        return response.json().get("response", "{}")
    except Exception as e:
        log.error(f"❌ [SECURITY] Erro no cérebro: {e}")
        return None

# --- HELPERS DE HARDWARE ---
def _stop_media():
    """Envia o comando de parada de mídia para o sistema."""
    try:
        # VK_MEDIA_PLAY_PAUSE = 0xB3 (Mais universal para parar o que estiver tocando)
        ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0) # Press
        ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0) # Release
        log.debug("🎵 Mídia interrompida via Sentinela.")
    except:
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

def _empty_recycle_bin():
    """Esvazia a lixeira do Windows sem pedir confirmação."""
    try:
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 1 | 2 | 4)
        return True
    except:
        return False

def _clean_temp_files():
    """Remove arquivos temporários do usuário."""
    temp_path = os.environ.get('TEMP')
    if not temp_path: return 0
    
    count = 0
    files = glob.glob(os.path.join(temp_path, "*"))
    for f in files:
        try:
            if os.path.isfile(f):
                os.remove(f)
            elif os.path.isdir(f):
                shutil.rmtree(f)
            count += 1
        except:
            continue
    return count

def suspend_system():
    """Coloca o sistema em modo de suspensão (Sleep)."""
    try:
        log.info("💤 Iniciando suspensão do sistema...")
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        return "Entrando em modo de baixo consumo. Até breve, senhor."
    except Exception as e:
        log.error(f"Erro ao suspender: {e}")
        return "Não consegui suspender o sistema via comando."

def lock_workstation():
    """Bloqueia a estação de trabalho imediatamente sem parar a mídia."""
    ctypes.windll.user32.LockWorkStation()
    log.info("🔒 Estação bloqueada.")
    return "Estação bloqueada, senhor."

def power_down_protocol(is_confirmed=False):
    """Protocolo Robusto de Desligamento: Limpeza -> Despedida -> Shutdown."""
    
    if not is_confirmed:
        _state["awaiting_power_down"] = True
        return "⚠️ O Protocolo de Desenergização do Núcleo é irreversível. Deseja realmente prosseguir com o encerramento total?"

    log.warning("🚀 [SECURITY] INICIANDO PROTOCOLO: DESENERGIZAR O NÚCLEO")
    _state["awaiting_power_down"] = False

    log.info("🧹 [SECURITY] Limpando detritos e arquivos temporários...")
    _empty_recycle_bin()
    removed_count = _clean_temp_files()
    
    log.info("👋 [SECURITY] Despedindo e enviando comando de shutdown.")
    os.system(f"shutdown /s /t 15 /c \"J.A.R.V.I.S: Núcleo desenergizado. Limpeza concluída ({removed_count} itens).\"")
    
    return f"Limpeza concluída. Foram eliminados {removed_count} detritos do sistema. Iniciando sequência de desenergização total do núcleo em 15 segundos. Foi um prazer servi-lo, senhor. Sistemas offline."

# --- EXECUÇÃO PRINCIPAL ---
def execute(entity, command):
    log.info(f"🛡️ [SECURITY] Analisando comando: '{command}'")

    pending_confirmation = _state["awaiting_power_down"]
    cmd_lower = command.lower()

    if pending_confirmation:
        if any(confirm in cmd_lower for confirm in ["sim", "pode", "prossiga", "confirmar", "go", "afirmativo"]):
            return power_down_protocol(is_confirmed=True)
        elif any(neg in cmd_lower for neg in ["não", "cancela", "pare", "aborta"]):
            _state["awaiting_power_down"] = False
            return "Protocolo de desenergização abortado pelo usuário. Sistemas mantidos online."

    ai_response = _ask_ollama_security(command)
    
    if not ai_response:
        if any(x in cmd_lower for x in ["sentinela", "proteger", "sair"]):
            return sentry_mode()
        if any(x in cmd_lower for x in ["desligar", "encerrar", "núcleo", "power down"]):
            return power_down_protocol(is_confirmed=False)
        if any(x in cmd_lower for x in ["dormir", "suspender", "descansar"]):
            return suspend_system()
        return lock_workstation()

    try:
        decision = json.loads(ai_response)
        action = decision.get("action")
        confirmed = decision.get("confirmed", False)

        log.info(f"🤖 Decisão de Segurança: {action} (Confirmado: {confirmed})")

        if action == "sentry_mode":
            return sentry_mode()
        elif action == "suspend":
            return suspend_system()
        elif action == "power_down":
            return power_down_protocol(is_confirmed=confirmed)
        else:
            return "Não compreendi o protocolo de segurança solicitado."

    except Exception as e:
        log.error(f"Erro Security: {e}")
        return "Falha crítica no módulo de segurança física."
