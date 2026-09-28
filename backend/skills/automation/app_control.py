import difflib
import json
import os
import subprocess

import psutil
import requests  # Conexão direta

from core import log
from core.config import settings
from core.prompts import load_prompt
from core.window_utils import find_window_by_pid, force_foreground

# --- CONFIGURAÇÃO DA SKILL ---
INTENT = "APP_CONTROL"
PROMPT_TEXT = load_prompt("skills/app_control.md")

# --- CÉREBRO ESPECÍFICO DA SKILL (APP EXPERT) ---
APP_DECISION_PROMPT = load_prompt("skills/app_decision.md")

# --- CACHE GLOBAL ---
INSTALLED_APPS_CACHE = {}

# --- ALIASES MANUAIS ---
ALIASES = {
    "zap": "whatsapp",
    "navegador": "opera gx",  # Ou chrome, conforme preferência
    "vs code": "visual studio code",
    "code": "visual studio code",
    "lol": "league of legends",
    "calculadora": "calculator",
    "calc": "calculator",
    "opera": "opera gx",
    "browser": "opera gx"
}

# --- MAPEAMENTO DE PROCESSOS ---
PROCESS_MAP = {
    "calculadora": ["CalculatorApp", "Calculator"],
    "spotify": ["Spotify"],
    "chrome": ["chrome"],
    "opera": ["opera"],
    "firefox": ["firefox"],
    "calculator": ["CalculatorApp", "Calculator"],
    "code": ["Code"],
    "visual studio code": ["Code"]
}

# --- FUNÇÃO LOCAL DE LLM ---
def _ask_ollama_app_expert(user_text):
    """Consulta o LLM para decidir o que fazer com o app."""
    url = f"http://{settings.OLLAMA_HOST}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": user_text,
        "system": APP_DECISION_PROMPT,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1} # Precisão máxima
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json().get("response", "{}")
    except Exception as e:
        log.error(f"❌ [APP SKILL] Erro no cérebro (Timeout/Conexão): {e}")
        return None

# --- HELPERS DE SISTEMA (MANTIDOS IGUAIS PELA EFICIÊNCIA) ---
def get_installed_apps():
    global INSTALLED_APPS_CACHE
    if INSTALLED_APPS_CACHE: return INSTALLED_APPS_CACHE
    log.info("📂 [SKILL] Indexando softwares...")
    apps = {}
    
    # 1. PowerShell (Modern Apps)
    try:
        cmd = 'powershell -Command "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"'
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if result.returncode == 0 and result.stdout.strip():
            raw = json.loads(result.stdout)
            data = raw if isinstance(raw, list) else [raw]
            for item in data:
                apps[item.get('Name', '').lower().strip()] = item.get('AppID')
    except: pass

    # 2. Filesystem (LNKs)
    paths = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs")
    ]
    for path in paths:
        if not os.path.exists(path): continue
        for root, _, files in os.walk(path):
            for file in files:
                if file.lower().endswith(".lnk"):
                    apps[file[:-4].lower().strip()] = os.path.join(root, file)
    
    INSTALLED_APPS_CACHE = apps
    return apps

def find_best_match(user_query, apps_dict):
    clean_query = user_query.lower().strip()
    # Alias Check
    if clean_query in ALIASES:
        clean_query = ALIASES[clean_query]
    
    # Fuzzy Match - Aumentado para 0.6 para evitar abrir apps errados (como 'peak' em vez de 'opera')
    matches = difflib.get_close_matches(clean_query, apps_dict.keys(), n=1, cutoff=0.6)
    if matches:
        return matches[0], apps_dict[matches[0]]
    return None, None

def find_active_processes(target_name):
    target_clean = target_name.lower()
    if target_clean in ALIASES: target_clean = ALIASES[target_clean]

    found_procs = []
    # Busca na lista manual ou usa o próprio nome
    targets_to_check = PROCESS_MAP.get(target_clean, [target_clean])
    
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            p_name = proc.info['name'].lower()
            if any(t.lower() in p_name for t in targets_to_check):
                found_procs.append(proc)
        except: continue
    return found_procs

def focus_window(pid):
    # Tentativa 1 (principal): Win32 direto. Trata janela minimizada (IsIconic + SW_RESTORE)
    # e contorna a restrição de foreground-lock do Windows via AttachThreadInput.
    try:
        hwnd = find_window_by_pid(pid)
        if hwnd:
            if force_foreground(hwnd):
                return True
        else:
            # Normal em apps multi-processo (Electron: VS Code, Spotify, Discord...):
            # a maioria dos PIDs são processos auxiliares (renderer, GPU, etc.) sem janela própria.
            # execute() itera todos os PIDs do app até achar o que tem janela — isso não é falha.
            log.debug(f"[APP SKILL] Nenhuma janela visível para PID {pid} (provável processo auxiliar).")
    except Exception as e:
        log.warning(f"⚠️ [APP SKILL] Foco Win32 falhou para PID {pid}: {e}")

    # Tentativa 2 (fallback): AppActivate via PowerShell. Cobre casos raros onde o processo
    # não expõe uma janela top-level enumerável diretamente (ex: apps hospedados por
    # ApplicationFrameHost). Nota: AppActivate pode retornar "sucesso" mesmo só piscando a
    # taskbar sem realmente trazer a janela pra frente — por isso não é mais a tentativa principal.
    cmd = f"""
    $p = Get-Process -Id {pid} -ErrorAction SilentlyContinue
    if ($p -and $p.MainWindowTitle) {{
        $w = New-Object -ComObject WScript.Shell
        $w.AppActivate($p.MainWindowTitle)
        return "OK"
    }}
    return "NO"
    """
    try:
        res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, timeout=5).stdout.strip()
        return "OK" in res
    except Exception as e:
        log.warning(f"⚠️ [APP SKILL] AppActivate falhou para PID {pid}: {e}")

    return False

# --- EXECUÇÃO PRINCIPAL ---
def execute(entity, command_text=""):
    if not command_text:
        return "Aguardando designação do software, senhor."

    # Cérebro: Define Ação e Alvo
    ai_response = _ask_ollama_app_expert(command_text)
    if not ai_response:
        return "Falha na conexão com os processadores neurais. Não posso gerenciar apps agora."

    try:
        decision = json.loads(ai_response)
        action = decision.get("action")
        target_raw = decision.get("target")

        log.info(f"🤖 Decisão: {action} | Alvo: {target_raw}")
        
        if not target_raw:
            return "Comando incompleto. O alvo do software não foi identificado."

        # Execução Baseada na Decisão
        # --- AÇÃO: FOCAR ---
        if action == "focus":
            procs = find_active_processes(target_raw)
            if not procs:
                return f"Varredura completa. O {target_raw} não consta nos processos ativos."
            
            for proc in procs:
                if focus_window(proc.info['pid']):
                    return f"Redirecionando interface do {target_raw} para a tela principal."

            log.warning(f"⚠️ [APP SKILL] Falha ao focar '{target_raw}': nenhum dos {len(procs)} processo(s) tinha janela focável.")
            return f"O {target_raw} está operando em segundo plano, mas a interface gráfica não responde."

        # --- AÇÃO: FECHAR ---
        elif action == "close":
            procs = find_active_processes(target_raw)
            if procs:
                count = 0
                for proc in procs:
                    try: 
                        proc.terminate()
                        count += 1
                    except: pass
                # Resposta técnica e satisfatória
                return f"Encerrando {count} instâncias do {target_raw}. Memória liberada."
            else:
                return f"Não há processos ativos do {target_raw} para terminar."

        # --- AÇÃO: ABRIR (OPEN) ---
        elif action == "open":
            # Primeiro verifica se já existe
            existing = find_active_processes(target_raw)
            if existing:
                # Tenta focar em vez de abrir duplicado
                if focus_window(existing[0].info['pid']):
                    return f"O {target_raw} já está ativo. Trazendo para o primeiro plano para evitar redundância."
            
            # Se não, abre
            apps = get_installed_apps()
            real_name, app_path = find_best_match(target_raw, apps)
            
            if app_path:
                try:
                    log.info(f"🚀 Iniciando: {real_name}")
                    # Usamos subprocess.DEVNULL para silenciar logs internos dos apps (Notion, Spotify, etc)
                    if "!" in app_path or app_path.startswith("{"):
                        subprocess.Popen(f'explorer.exe shell:AppsFolder\\{app_path}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        os.startfile(app_path)
                    return f"Inicializando sequência de abertura do {real_name}."
                except:
                    return f"Erro ao tentar executar o binário do {real_name}."
            
            # Tentativa desesperada (Comando direto)
            try:
                subprocess.Popen(target_raw, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Protocolo padrão falhou. Tentando execução direta via shell para {target_raw}."
            except:
                return f"Busca negativa. O software {target_raw} não foi localizado no índice do sistema."

    except json.JSONDecodeError:
        return "Erro de sintaxe na resposta da IA. Requer diagnóstico."
    except Exception as e:
        log.error(f"Erro App Control: {e}")
        return "Detectada falha crítica no subsistema de gerenciamento de processos."

    return "Comando de software fora dos parâmetros conhecidos."