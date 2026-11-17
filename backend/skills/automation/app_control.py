# ⚠️ ACESSO SENSÍVEL: abre, fecha e força foco em processos/janelas do sistema operacional
# via psutil + PowerShell/Win32 (subprocess, ctypes). Ver SECURITY.md.
import difflib
import json
import os
import re
import shutil
import subprocess

import psutil

from core import log, pending, processes
from core.config import settings
from core.llm import query_ollama
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
    "visual studio code": ["Code"],
    "opera gx": ["opera"],
    "whatsapp": ["WhatsApp"],
}

# Alvo de "fechar" com menos letras que isso é recusado ("s", "e"… pegariam metade do PC).
MIN_TARGET_LEN = 3
# Fallback de "abrir" por nome de programa no PATH: só letras, números, espaço, . + -
_SAFE_COMMAND = re.compile(r"[\w .+-]{2,60}")

# --- FUNÇÃO LOCAL DE LLM ---
def _ask_ollama_app_expert(user_text):
    """Consulta o LLM para decidir o que fazer com o app."""
    # core.llm normaliza OLLAMA_HOST e trata erro (devolve None).
    return query_ollama([{"role": "system", "content": APP_DECISION_PROMPT},
                         {"role": "user", "content": user_text}],
                        format="json", temperature=0.1, timeout=settings.TIMEOUT_API)

# --- HELPERS DE SISTEMA (MANTIDOS IGUAIS PELA EFICIÊNCIA) ---
def get_installed_apps():
    global INSTALLED_APPS_CACHE
    if INSTALLED_APPS_CACHE: return INSTALLED_APPS_CACHE
    log.info("📂 [SKILL] Indexando softwares...")
    apps = {}
    
    # 1. PowerShell (Modern Apps)
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"]
        result = subprocess.run(cmd, capture_output=True, text=True)
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

def _resolve_target(target_name):
    """Alvo do LLM → (nome limpo, nomes de executável aceitos, conhecido?)."""
    target_clean = processes.stem(target_name)
    if target_clean in ALIASES:
        target_clean = ALIASES[target_clean]
    known = target_clean in PROCESS_MAP
    names = PROCESS_MAP.get(target_clean, [target_clean])
    return target_clean, {processes.stem(n) for n in names}, known


def find_active_processes(target_name):
    """Processos cujo executável tem EXATAMENTE o nome do alvo (sem .exe, sem
    maiúsculas). Nunca devolve processos protegidos (sistema, o próprio JARVIS).
    Antes era substring: "fechar code" pegava tudo com "code" no nome (GHSA-p7rm)."""
    _, names, _ = _resolve_target(target_name)
    found_procs = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            p_name = proc.info['name'] or ""
            if processes.stem(p_name) in names and not processes.is_protected(p_name, proc.info['pid']):
                found_procs.append(proc)
        except Exception:
            continue
    return found_procs


def _snapshot(procs):
    """[(pid, nome, create_time)] — o que exatamente será encerrado após o "sim"."""
    snap = []
    for proc in procs:
        try:
            snap.append((proc.info['pid'], proc.info['name'], proc.create_time()))
        except Exception:
            continue
    return snap


def _terminate_snapshot(snapshot, label):
    closed = sum(1 for pid, name, created in snapshot
                 if processes.terminate_if_same(pid, name, created) == "ok")
    if not closed:
        return f"Nenhuma instância do {label} foi encerrada (já tinham fechado ou exigem administrador)."
    return f"Encerrando {closed} instâncias do {label}. Memória liberada."


def _valid_close_target(target_raw):
    return len(processes.stem(target_raw)) >= MIN_TARGET_LEN


def close_now(target_raw):
    """Encerra o alvo sem perguntar — só para quando o usuário JÁ confirmou
    (ex.: alerta de consumo crítico respondido com "sim")."""
    if not target_raw or not _valid_close_target(target_raw):
        return "Alvo inválido para encerrar, senhor."
    procs = find_active_processes(target_raw)
    if not procs:
        return f"Não há processos ativos do {target_raw} para terminar."
    return _terminate_snapshot(_snapshot(procs), target_raw)


def _close(target_raw):
    """Ação "fechar": app conhecido com um único executável fecha direto; nome
    desconhecido ou vários executáveis diferentes pedem confirmação."""
    if not _valid_close_target(target_raw):
        return f"O alvo '{target_raw}' é curto demais para eu encerrar com segurança, senhor."
    procs = find_active_processes(target_raw)
    if not procs:
        return f"Não há processos ativos do {target_raw} para terminar."
    snapshot = _snapshot(procs)
    _, _, known = _resolve_target(target_raw)
    exe_names = sorted({name for _, name, _ in snapshot})
    if known and len(exe_names) == 1:
        return _terminate_snapshot(snapshot, target_raw)
    question = (f"Encerrar {len(snapshot)} processo(s) de {', '.join(exe_names)}? "
                f"Não reconheço '{target_raw}' como um app da minha lista.")
    armed = pending.arm("APP_CLOSE", question, lambda: _terminate_snapshot(snapshot, target_raw),
                        target=target_raw)
    if armed is None:
        return pending.BUSY_REPLY
    return f"{question} Diga **sim** para confirmar."


def _safe_command_name(target_raw):
    """Nome simples de programa (ex.: 'notepad'): sem caminho, aspas nem &|;<>."""
    return bool(_SAFE_COMMAND.fullmatch(target_raw or ""))

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
            return _close(target_raw)

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
                        # Lista de argumentos (sem shell): o AppID nunca vira comando do cmd.
                        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_path}"],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        os.startfile(app_path)
                    return f"Inicializando sequência de abertura do {real_name}."
                except Exception:
                    return f"Erro ao tentar executar o binário do {real_name}."

            # Último recurso: programa no PATH (ex.: "notepad"), só com nome simples e
            # sem shell. O texto do LLM nunca vai para o cmd (GHSA-8j53).
            exe = shutil.which(target_raw) if _safe_command_name(target_raw) else None
            if exe:
                try:
                    subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return f"Protocolo padrão falhou. Iniciando {target_raw} pelo PATH do sistema."
                except Exception as e:
                    log.warning(f"[APP SKILL] Falha ao iniciar {exe}: {e}")
            return f"Busca negativa. O software {target_raw} não foi localizado no índice do sistema."

    except json.JSONDecodeError:
        return "Erro de sintaxe na resposta da IA. Requer diagnóstico."
    except Exception as e:
        log.error(f"Erro App Control: {e}")
        return "Detectada falha crítica no subsistema de gerenciamento de processos."

    return "Comando de software fora dos parâmetros conhecidos."