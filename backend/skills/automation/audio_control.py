import json
import time
from ctypes import POINTER, cast

import requests  # Adicionado para fazer a requisição direta
from comtypes import CLSCTX_ALL, CoInitialize, CoUninitialize
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from core import log
from core.config import settings  # Para pegar o IP e Modelo definidos no config
from core.prompts import load_prompt

# --- CONFIGURAÇÃO PARA O ROTEADOR ---
INTENT = "AUDIO_CONTROL"

PROMPT_TEXT = load_prompt("skills/audio_control.md")

# --- CÉREBRO ESPECÍFICO DA SKILL (ATUALIZADO) ---
AUDIO_DECISION_PROMPT = load_prompt("skills/audio_decision.md")

# --- FUNÇÃO LOCAL DE LLM (O CÉREBRO ISOLADO) ---
def _ask_ollama_audio_expert(user_text):
    """
    Função privada que conecta ao Ollama especificamente para esta skill.
    Isso isola a lógica de decisão dentro deste arquivo.
    """
    url = f"http://{settings.OLLAMA_HOST}/api/generate"
    
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": user_text,
        "system": AUDIO_DECISION_PROMPT,
        "stream": False,
        "format": "json", # Força resposta em JSON nativo do Ollama
        "options": {
            "temperature": 0.1, # Muito baixo para ser preciso/matemático
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        return response.json().get("response", "{}")
    except Exception as e:
        log.error(f"❌ [AUDIO SKILL] Erro ao consultar IA Local: {e}")
        return None

# --- HELPERS DE ÁUDIO (PYCAW) ---
def get_audio_interface():
    """
    Recupera a interface de áudio. 
    ATENÇÃO: Não chama CoInitialize aqui, usa o da função execute.
    """
    try:
        devices = AudioUtilities.GetDeviceEnumerator()
        interface = devices.GetDefaultAudioEndpoint(0, 1)
        volume = interface.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(volume, POINTER(IAudioEndpointVolume))
    except Exception as e:
        log.error(f"Erro driver de áudio: {e}")
        return None

def smooth_set_volume(target_vol):
    """
    Define volume absoluto de forma segura.
    Substitui a antiga set_volume_absolute que causava crash.
    """
    interface = get_audio_interface()
    if not interface: return False

    try:
        current = interface.GetMasterVolumeLevelScalar()
        target = max(0.0, min(1.0, target_vol / 100.0))
        
        # Evita overhead se a mudança for minúscula
        if abs(current - target) < 0.05:
            interface.SetMasterVolumeLevelScalar(target, None)
            return True

        # Transição suave protegida
        steps = 5
        step_val = (target - current) / steps
        
        for _ in range(steps):
            current += step_val
            safe_val = max(0.0, min(1.0, current))
            try:
                interface.SetMasterVolumeLevelScalar(safe_val, None)
            except: 
                break # Se falhar no meio, para o loop mas não crasha o app
            time.sleep(0.02)
            
        interface.SetMasterVolumeLevelScalar(target, None)
        return True
    except Exception as e:
        log.error(f"Erro na transição: {e}")
        return False

def change_volume_relative_safe(delta):
    """Versão segura de change_volume_relative"""
    interface = get_audio_interface()
    if not interface: return 0

    try:
        current = interface.GetMasterVolumeLevelScalar()
        new_val = max(0.0, min(1.0, current + (delta / 100.0)))
        interface.SetMasterVolumeLevelScalar(new_val, None)
        return int(new_val * 100)
    except:
        return 0

def toggle_mute_safe(force_mode=None):
    interface = get_audio_interface()
    if not interface: return

    try:
        curr = interface.GetMute()
        if force_mode is None:
            interface.SetMute(not curr, None)
        elif curr != force_mode:
            interface.SetMute(force_mode, None)
    except: pass

# --- EXECUÇÃO PRINCIPAL ---
def execute(entity, command_text=""):
    try:
        CoInitialize()
    except:
        pass

    if not command_text:
        return "Estou aguardando suas ordens, senhor."

    # Chamada direta à IA Local
    ai_response_str = _ask_ollama_audio_expert(command_text)
    
    if not ai_response_str:
        return "Senhor, perdi a conexão com meus processadores neurais."

    try:
        # Parsing da decisão
        decision = json.loads(ai_response_str)
        action = decision.get("action")
        value = decision.get("value")
        
        log.info(f"🤖 Decisão: {action} | Valor: {value}")

        # Execução Física com Personalidade
        if action == "set" and value is not None:
            smooth_set_volume(value)
            if value >= 100:
                return "Potência máxima estabelecida. Cuidado com os ouvidos, senhor."
            return f"Nível de saída calibrado para {value}%, senhor."

        elif action == "increase":
            val = value if value else 15
            final = change_volume_relative_safe(val)
            return f"Amplificando níveis de áudio para {final}%."

        elif action == "decrease":
            val = value if value else 15
            final = change_volume_relative_safe(-val)
            return f"Reduzindo a saída para {final}%, conforme solicitado."

        elif action == "mute":
            toggle_mute_safe(force_mode=True)
            return "Modo silencioso ativado. Cortando canais de áudio."

        elif action == "unmute":
            toggle_mute_safe(force_mode=False)
            return "Canais de som restaurados, senhor."
            
        elif action == "info":
            interface = get_audio_interface()
            curr = int(interface.GetMasterVolumeLevelScalar() * 100) if interface else 0
            return f"Os diagnósticos indicam que o volume atual está em {curr}%."

    except json.JSONDecodeError:
        log.error(f"Erro ao ler JSON da IA: {ai_response_str}")
        return "Houve uma falha na interpretação dos dados recebidos, senhor."
    except Exception as e:
        log.error(f"Erro na execução de áudio: {e}")
        return "Detectei uma anomalia no subsistema de hardware de áudio."

    finally:
        # LIMPEZA OBRIGATÓRIA
        try:
            CoUninitialize()
        except:
            pass
    return "O comando não consta em meus protocolos de áudio."