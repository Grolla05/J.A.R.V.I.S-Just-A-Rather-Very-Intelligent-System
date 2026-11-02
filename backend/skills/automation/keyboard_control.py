import ctypes
import json
import subprocess
import time

import pyautogui
import requests

from core import log
from core.config import settings
from core.prompts import load_prompt

_state = {"pending_keyboard_action": None}

# --- CONFIGURAÇÃO DA SKILL ---
INTENT = "KEYBOARD_CONTROL"
PROMPT_TEXT = load_prompt("skills/keyboard_control.md")

# --- CÉREBRO ESPECÍFICO (KEYBOARD EXPERT) ---
KEYBOARD_EXPERT_PROMPT = load_prompt("skills/keyboard_expert.md")

# Configuração de segurança do PyAutoGUI
pyautogui.FAILSAFE = True  # Move mouse para o canto superior esquerdo para abortar
pyautogui.PAUSE = 0.5      # Pausa padrão entre ações

def get_active_window_title():
    """Obtém o título da janela que está em foco (Active Window)."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value or "Janela Desconhecida"
    except:
        return "Interface do Sistema"

def get_clipboard_text():
    """Lê o conteúdo atual da área de transferência via PowerShell."""
    try:
        # Usa PowerShell para evitar dependências extras e lidar bem com encoding
        cmd = ["powershell", "-NoProfile", "-Command", "Get-Clipboard"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        return result.stdout.strip()
    except Exception as e:
        log.error(f"❌ [KEYBOARD] Erro ao ler clipboard: {e}")
        return None

def _ask_ollama_keyboard_expert(user_text):
    """Consulta o LLM para determinar a combinação de teclas."""
    url = f"http://{settings.OLLAMA_HOST}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": user_text,
        "system": KEYBOARD_EXPERT_PROMPT,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1} # Precisão cirúrgica
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        return response.json().get("response", "{}")
    except Exception as e:
        log.error(f"❌ [KEYBOARD SKILL] Erro no cérebro: {e}")
        return None

def execute(entity, command_text):
    if not command_text:
        return "Nenhum comando de teclado detectado."

    # 0. Verificação de Confirmação Pendente
    pending_data = _state["pending_keyboard_action"]
    if pending_data:
        cmd_lower = command_text.lower()
        # Se for uma confirmação positiva
        if any(confirm in cmd_lower for confirm in ["sim", "pode", "prossiga", "confirmar", "afirmativo", "faz isso"]):
            decision = json.loads(pending_data)
            _state["pending_keyboard_action"] = None
            return _perform_action(decision)

        # Se for negativa ou outra coisa
        if any(neg in cmd_lower for neg in ["não", "cancela", "pare", "aborta", "esquece"]):
            _state["pending_keyboard_action"] = None
            return "Comando cancelado. Integridade do ambiente mantida, senhor."

    # 1. Consulta o especialista
    ai_response = _ask_ollama_keyboard_expert(command_text)
    if not ai_response:
        return "Erro ao processar as sequências de teclas."

    try:
        decision = json.loads(ai_response)
        is_dangerous = decision.get("is_dangerous", False)
        desc = decision.get("description", "executar este comando")

        # 2. Gatilho de Segurança
        if is_dangerous:
            _state["pending_keyboard_action"] = json.dumps(decision)
            return f"⚠️ Atenção, senhor. O comando solicitado irá {desc}. Deseja realmente prosseguir?"

        # 3. Execução Normal
        return _perform_action(decision)

    except json.JSONDecodeError:
        return "Erro de interpretação neural para o teclado."
    except Exception as e:
        log.error(f"Erro Keyboard Control: {e}")
        return f"Falha na interface de entrada: {e}"

def _perform_action(decision):
    """Executa a ação ou sequência de ações de teclado."""
    try:
        action = decision.get("action")
        active_window = get_active_window_title()

        # Caso seja uma sequência (Combo)
        if action == "sequence":
            steps = decision.get("steps", [])
            for step in steps:
                _perform_action(step)
                time.sleep(0.1) # Pequena pausa entre passos do combo
            return f"Combo '{decision.get('description', 'Produtividade')}' executado em '{active_window}'."

        keys = decision.get("keys", [])
        text_content = decision.get("text", "")

        log.info(f"⌨️ [KEYBOARD]: Ação: {action} | Teclas: {keys} | Janela: '{active_window}'")

        if action == "hotkey" and keys:
            is_closing = 'alt' in keys and 'f4' in keys
            is_copying = ('ctrl' in keys and 'c' in keys) or ('ctrl' in keys and 'x' in keys)
            
            pyautogui.hotkey(*keys)
            
            if is_closing:
                return f"Encerrando '{active_window}' conforme solicitado."
            
            if is_copying:
                time.sleep(0.2)
                copied_text = get_clipboard_text()
                if copied_text:
                    short_text = (copied_text[:40] + '...') if len(copied_text) > 40 else copied_text
                    return f"Texto capturado da janela '{active_window}': \"{short_text}\""
                return f"Cópia executada em '{active_window}', mas o clipboard está vazio."
            
            return f"Atalho executado em '{active_window}': {' + '.join(keys).upper()}"

        elif action == "press" and keys:
            for k in keys:
                pyautogui.press(k)
            return f"Comando '{keys[0].upper()}' enviado para '{active_window}'."

        elif action == "write" and text_content:
            pyautogui.write(text_content, interval=0.05)
            return f"Texto inserido na janela '{active_window}'."

        return "Operação de teclado não reconhecida."
    except Exception as e:
        log.error(f"Erro na execução física de teclado: {e}")
        return f"Erro de hardware: {e}"
