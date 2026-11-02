# ⚠️ ACESSO SENSÍVEL: manipula janelas (foco, posição, monitor), brilho e gamma da tela
# via Win32 direto (ctypes) e PowerShell/WMI. Ver SECURITY.md.
import ctypes
import datetime
import json
import subprocess

import requests

from core import log
from core.config import settings
from core.prompts import load_prompt
from core.window_utils import (
    find_window_by_title,
    force_foreground,
    get_monitors,
    get_window_placement,
)

# --- CORREÇÃO DE DPI (CRUCIAL PARA ALINHAMENTO CORRETO) ---
try:
    # Tenta definir consciência de DPI por monitor (Windows 8.1+)
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # 2 = Process_Per_Monitor_DPI_Aware
except Exception:
    # Fallback para Windows mais antigo
    ctypes.windll.user32.SetProcessDPIAware()

# --- CONFIGURAÇÃO DA SKILL ---
INTENT = "SCREEN_CONTROL"
PROMPT_TEXT = load_prompt("skills/screen_control.md")

# --- ESTRUTURAS DO WINDOWS API (Ctypes) ---
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

class RAMP(ctypes.Structure):
    _fields_ = [("Red", ctypes.c_ushort * 256), ("Green", ctypes.c_ushort * 256), ("Blue", ctypes.c_ushort * 256)]

# --- CÉREBRO ESPECÍFICO (SCREEN EXPERT) ---
SCREEN_EXPERT_PROMPT = load_prompt("skills/screen_expert.md")

# --- HARDWARE: MONITORES & JANELAS ---
# get_monitors / find_window_by_title / get_window_placement / force_foreground
# agora vivem em core/window_utils.py (compartilhado com app_control.py).

def get_active_window_handle():
    return user32.GetForegroundWindow()

def _ask_ollama_screen(user_text, monitors_context):
    try:
        current_hour = datetime.datetime.now().hour
        prompt_with_context = load_prompt("skills/screen_expert.md", monitors_info=monitors_context, current_hour=str(current_hour))
        
        url = f"http://{settings.OLLAMA_HOST}/api/generate"
        payload = {
            "model": settings.OLLAMA_MODEL, "prompt": user_text, "system": prompt_with_context, 
            "stream": False, "format": "json", "options": {"temperature": 0.1}
        }
        res = requests.post(url, json=payload, timeout=5)
        res.raise_for_status()
        return res.json().get("response", "{}")
    except Exception as e:
        log.error(f"❌ [SCREEN] Erro IA: {e}")
        return None

# --- VISUAL HELPERS (Gamma & WMI) ---
def apply_gamma_ramp(brightness_level=1.0, warmth_level=0.0):
    """
    Versão Blindada: Força tipos inteiros estritos para evitar rejeição da API do Windows.
    """
    # Tenta obter o DC da tela inteira
    hdc = user32.GetDC(None)
    if not hdc:
        log.error("❌ [SCREEN] Falha ao obter Device Context (HDC).")
        return False

    ramp = RAMP()
    
    # Clamping de segurança (0.0 a 1.0)
    b_level = max(0.1, min(1.0, float(brightness_level)))
    w_level = max(0.0, min(1.0, float(warmth_level)))

    for i in range(256):
        # Base linear (0 a 65535)
        base_val = (i / 255.0) * 65535
        
        # Ajuste de Brilho
        val = base_val * b_level
        
        # Cálculos de cor (Protocolo Retina)
        r_val = val
        g_val = val * (1.0 - (w_level * 0.25)) # Reduz verde
        b_val = val * (1.0 - (w_level * 0.65)) # Reduz muito o azul

        # Garante que nunca passe de 65535 nem seja negativo
        # Converte explicitamente para int (Python às vezes passa float)
        ramp.Red[i]   = int(max(0, min(65535, r_val)))
        ramp.Green[i] = int(max(0, min(65535, g_val)))
        ramp.Blue[i]  = int(max(0, min(65535, b_val)))

    # Tenta aplicar
    success = gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp))
    
    # Se falhar, tenta pegar o erro para debug (opcional, mas útil)
    if not success:
        error_code = ctypes.GetLastError()
        log.error(f"❌ [SCREEN] SetDeviceGammaRamp falhou. Código de erro: {error_code}")
        # Dica: Erro 87 costuma ser 'Parâmetro Inválido' (Ramp mal formatado)
    
    user32.ReleaseDC(None, hdc)
    return bool(success)

def _try_wmi_brightness(target_percent):
    try:
        cmd = f"powershell -Command \"(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, {target_percent})\""
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return res.returncode == 0
    except: return False

LAST_BRIGHTNESS = 100

def set_brightness(level):
    global LAST_BRIGHTNESS
    target = LAST_BRIGHTNESS
    
    if isinstance(level, str):
        if level.startswith("+"): target += int(level[1:])
        elif level.startswith("-"): target -= int(level[1:])
        else: target = int(level)
    else: target = int(level)
    
    target = max(0, min(100, target))
    LAST_BRIGHTNESS = target
    
    hw_success = _try_wmi_brightness(target)
    sw_brightness = 1.0 if hw_success else (target / 100.0)
    apply_gamma_ramp(sw_brightness, 0.0)  # Sem ajuste de temperatura (Night Light cuida disso)
    
    return f"Brilho: {target}% ({'Hardware' if hw_success else 'Software'})."

# Variável global para saber se o modo retina está ativo
RETINA_STATE = False 

def _toggle_night_light(enable=True):
    """
    Ativa/Desativa o modo de proteção ocular manipulando a curva Gamma.
    Não altera a configuração nativa do Windows, mas o efeito visual é idêntico e imediato.
    """
    global RETINA_STATE
    global LAST_BRIGHTNESS
    
    # Converte o brilho salvo (0-100) para float (0.0-1.0)
    current_brightness = LAST_BRIGHTNESS / 100.0
    
    if enable:
        # Ativa: Mantém brilho atual, mas aplica 80% de "calor" (warmth)
        success = apply_gamma_ramp(current_brightness, warmth_level=0.8)
        if success:
            RETINA_STATE = True
            return True
    else:
        # Desativa: Mantém brilho atual, remove "calor" (0.0)
        success = apply_gamma_ramp(current_brightness, warmth_level=0.0)
        if success:
            RETINA_STATE = False
            return True
            
    return False

def apply_retina_protocol(mode="auto"):
    """Ativa ou desativa o Night Light do Windows para proteção ocular."""
    hour = datetime.datetime.now().hour
    is_night = hour >= 18 or hour < 6
    
    if mode == "off":
        success = _toggle_night_light(False)
        if success:
            return "Protocolo Retina OFF. Night Light desativado."
        else:
            return "Falha ao desativar Night Light. Verifique as permissões do sistema."

    if mode == "on" or (mode == "auto" and is_night):
        success = _toggle_night_light(True)
        if success:
            return f"Protocolo Retina ON ({'Noite detectada' if is_night else 'Ativação manual'}). Night Light ativado para proteção ocular."
        else:
            return "Falha ao ativar Night Light. Verifique as permissões do sistema."

    return "Período diurno detectado. Protocolo Retina não aplicado."

def move_window(target_monitor_idx, align, target_app_name=None):
    # 1. Identificar Janela
    hwnd = None
    label = "Janela Ativa"
    
    if target_app_name:
        hwnd = find_window_by_title(target_app_name)
        if hwnd: label = f"App '{target_app_name}'"
        else: return f"Não encontrei janela com '{target_app_name}'."
    else:
        hwnd = get_active_window_handle()
    
    if not hwnd: return "Nenhuma janela alvo."
    
    monitors = get_monitors()
    if not monitors: return "Sem monitores detectados."

    # 2. Identificar Monitor Atual da Janela
    win_rect = get_window_placement(hwnd)
    # Centro geométrico da janela
    cx = win_rect.left + (win_rect.right - win_rect.left) // 2
    cy = win_rect.top + (win_rect.bottom - win_rect.top) // 2
    
    current_idx = 0
    for i, m in enumerate(monitors):
        # Verifica se o centro da janela está dentro deste monitor
        if (m['x'] <= cx < m['x'] + m['width']) and (m['y'] <= cy < m['y'] + m['height']):
            current_idx = i
            break
            
    # 3. Definir Monitor de Destino
    new_idx = current_idx
    if target_monitor_idx == -1: 
        new_idx = (current_idx + 1) % len(monitors) # Ciclo (Loop)
    else:
        # Garante que o índice existe (ex: usuário pede monitor 9 mas só tem 2)
        target_adjusted = max(1, min(target_monitor_idx, len(monitors)))
        new_idx = target_adjusted - 1
    
    dest_m = monitors[new_idx]
    curr_m = monitors[current_idx]
    
    # Se já está no monitor certo e o align é manter, não faz nada
    if new_idx == current_idx and align == "maintain":
        return f"{label} já está no monitor correto."

    # 4. Cálculos Matemáticos (Jarvis Logic)
    is_maximized = user32.IsZoomed(hwnd)
    is_minimized = user32.IsIconic(hwnd)

    mx, my, mw, mh = dest_m['x'], dest_m['y'], dest_m['width'], dest_m['height']
    final_x, final_y, final_w, final_h = mx, my, mw, mh # Default: Tela cheia

    if align == "maximize" or (align == "maintain" and is_maximized):
        # Apenas joga para o outro monitor e maximiza
        # Pequeno truque: movemos a janela restaurada para o centro do novo monitor antes de maximizar
        if is_maximized: user32.ShowWindow(hwnd, 9) # Restore
        user32.MoveWindow(hwnd, mx, my, mw, mh, True)
        user32.ShowWindow(hwnd, 3) # Maximize
        return f"{label} maximizada no Monitor {new_idx+1}."
    
    elif align == "minimize":
        user32.ShowWindow(hwnd, 6) # Minimize
        return f"{label} minimizada."

    # Lógica de "Maintain" (Proporção Relativa)
    if align == "maintain":
        # Calcula porcentagem da posição atual
        rel_x = (win_rect.left - curr_m['x']) / curr_m['width']
        rel_y = (win_rect.top - curr_m['y']) / curr_m['height']
        rel_w = (win_rect.right - win_rect.left) / curr_m['width']
        rel_h = (win_rect.bottom - win_rect.top) / curr_m['height']
        
        # Aplica porcentagem no destino
        final_x = mx + (rel_x * mw)
        final_y = my + (rel_y * mh)
        final_w = rel_w * mw
        final_h = rel_h * mh

    # Lógica de Snapping (Esquerda/Direita/Centro)
    elif align == "left":
        final_w = mw // 2
        final_h = mh
        final_x = mx
        final_y = my
    elif align == "right":
        final_w = mw // 2
        final_h = mh
        final_x = mx + (mw // 2)
        final_y = my
    elif align == "center":
        final_w = int(mw * 0.6)
        final_h = int(mh * 0.7)
        final_x = mx + (mw - final_w) // 2
        final_y = my + (mh - final_h) // 2

    # 5. Execução do Movimento
    # Só restaura se estiver minimizada. Se estiver normal, apenas move (mais fluido)
    if is_minimized:
        user32.ShowWindow(hwnd, 9)

    user32.MoveWindow(hwnd, int(final_x), int(final_y), int(final_w), int(final_h), True)

    # Garante foco (contorna foreground-lock do Windows)
    force_foreground(hwnd)

    return f"{label} movida para Monitor {new_idx+1}."

# --- EXECUÇÃO PRINCIPAL ---
def execute(entity, command):
    log.info(f"👁️ [SCREEN] Cmd: {command}")
    
    monitors = get_monitors()
    ctx = f"{len(monitors)} monitores."
    
    ai_resp = _ask_ollama_screen(command, ctx)
    if not ai_resp: return "Erro neural."
    
    try:
        data = json.loads(ai_resp)
        act = data.get("action")
        target = data.get("target") # EX: "spotify"
        
        if act == "list_monitors": return f"Monitores: {len(monitors)}."
        elif act == "brightness": return set_brightness(data.get("value"))
        elif act == "retina_mode": 
            mode = data.get("value", "auto")
            if "desligar" in command.lower(): mode = "off"
            return apply_retina_protocol(mode)
        elif act == "move_window":
            return move_window(data.get("monitor", 0), data.get("align", "maintain"), target)
            
        return "Comando ignorado."
    except Exception as e:
        log.error(f"Erro Screen Exec: {e}")
        return "Falha crítica."
