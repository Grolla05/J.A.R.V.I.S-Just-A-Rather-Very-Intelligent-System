import ctypes
import difflib
import glob
import json
import os
import shutil
import subprocess

import requests

from core import log
from core.config import settings
from core.prompts import load_prompt

# --- CONFIGURAÇÃO DA SKILL ---
INTENT = "SYSTEM_CLEANUP"
PROMPT_TEXT = load_prompt("skills/system_clear.md")

# --- CÉREBRO ESPECÍFICO DA SKILL (CLEANUP EXPERT) ---
CLEANUP_DECISION_PROMPT = load_prompt("skills/system_clear_decision.md")

# --- CACHE E ALIASES ---
INSTALLED_APPS_CACHE = {}
ALIASES = {
    "zap": "whatsapp",
    "navegador": "opera",
    "browser": "opera",
    "vs": "visual studio code",
    "code": "visual studio code",
    "lol": "league of legends"
}

# --- FUNÇÃO LOCAL DE LLM ---
def _ask_ollama_cleanup_expert(user_text):
    url = f"http://{settings.OLLAMA_HOST}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": user_text,
        "system": CLEANUP_DECISION_PROMPT,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1}
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        return response.json().get("response", "{}")
    except Exception as e:
        log.error(f"❌ [CLEANUP] Erro no cérebro: {e}")
        return None

# --- HELPERS DE DESCOBERTA DE APPS (Baseado no app_control) ---
def get_installed_apps():
    global INSTALLED_APPS_CACHE
    if INSTALLED_APPS_CACHE: return INSTALLED_APPS_CACHE
    
    apps = {}
    # 1. PowerShell (Modern Apps) - Ótimo para pegar nomes oficiais
    try:
        cmd = 'powershell -Command "Get-StartApps | Select-Object Name | ConvertTo-Json -Compress"'
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if result.returncode == 0 and result.stdout.strip():
            raw = json.loads(result.stdout)
            data = raw if isinstance(raw, list) else [raw]
            for item in data:
                apps[item.get('Name', '').lower().strip()] = item.get('Name') # Guardamos o Nome Real como valor
    except: pass

    # 2. Filesystem (LNKs) - Fallback
    paths = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs")
    ]
    for path in paths:
        if not os.path.exists(path): continue
        for root, _, files in os.walk(path):
            for file in files:
                if file.lower().endswith(".lnk"):
                    clean_name = file[:-4].lower().strip()
                    if clean_name not in apps:
                        apps[clean_name] = clean_name # Valor é o nome (simplificado aqui)
    
    INSTALLED_APPS_CACHE = apps
    return apps

def find_best_match(user_query, apps_dict):
    clean_query = user_query.lower().strip()
    if clean_query in ALIASES: clean_query = ALIASES[clean_query]
    
    matches = difflib.get_close_matches(clean_query, apps_dict.keys(), n=1, cutoff=0.5)
    if matches:
        return apps_dict[matches[0]] # Retorna o Nome Real (Value do dict)
    return None

# --- AÇÕES DE LIMPEZA ---
def empty_recycle_bin():
    try:
        flags = 1 | 2 | 4 
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        return "Lixeira esvaziada. Detritos eliminados."
    except: return "A lixeira já parece estar limpa."

def clean_temp_files():
    temp_path = os.environ.get('TEMP')
    count = 0
    files = glob.glob(os.path.join(temp_path, "*"))
    for f in files:
        try:
            if os.path.isfile(f): os.remove(f)
            elif os.path.isdir(f): shutil.rmtree(f)
            count += 1
        except: pass
    return f"Limpeza de cache concluída. {count} itens removidos."

def uninstall_app(target_raw):
    """
    Tenta desinstalar usando Winget (Gerenciador de Pacotes do Windows).
    É o método mais autônomo e seguro via terminal hoje em dia.
    """
    apps = get_installed_apps()
    real_name = find_best_match(target_raw, apps)
    
    if not real_name:
        return f"Não encontrei o aplicativo '{target_raw}' instalado no sistema."

    # Comando Winget para desinstalar silenciosamente (se possível)
    # --accept-source-agreements evita bloqueio no primeiro uso
    log.info(f"🗑️ Tentando desinstalar: {real_name}")
    
    cmd = f'winget uninstall --name "{real_name}" --source winget --accept-source-agreements'
    
    # Executa em subprocesso para capturar output
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        
        if proc.returncode == 0:
            return f"Processo de desinstalação do {real_name} iniciado com sucesso."
        else:
            # Se falhar no winget (ex: app não é do winget), abrimos o painel antigo como fallback
            log.warning(f"Winget falhou: {proc.stderr}")
            subprocess.Popen("appwiz.cpl", shell=True)
            return f"Não consegui remover o {real_name} automaticamente. Abri o painel de controle para você finalizar."
            
    except Exception as e:
        return f"Erro ao tentar executar o protocolo de desinstalação: {e}"

# --- EXECUÇÃO PRINCIPAL ---
def execute(entity, command):
    ai_response = _ask_ollama_cleanup_expert(command)
    if not ai_response: return "Sistemas de limpeza indisponíveis."

    try:
        decision = json.loads(ai_response)
        action = decision.get("action")
        target = decision.get("target")

        log.info(f"🤖 Decisão: {action} | Alvo: {target}")

        if action == "recycle_bin":
            return empty_recycle_bin()
        elif action == "temp_files":
            return clean_temp_files()
        elif action == "uninstall_app" and target:
            return uninstall_app(target)
        else:
            return "Comando de limpeza não compreendido."

    except Exception as e:
        log.error(f"Erro Cleanup: {e}")
        return "Falha crítica no módulo de limpeza."
