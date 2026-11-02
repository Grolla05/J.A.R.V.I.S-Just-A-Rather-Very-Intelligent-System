import json
import os
import subprocess
import time

import requests

from core import log
from core.config import settings
from core.prompts import load_prompt
from core.spotify import ensure_device_ready, spotify, start_uri

# --- CONFIGURAÇÃO DA SKILL ---
INTENT = "WORK_MACRO"
PROMPT_TEXT = load_prompt("skills/work_macros.md")

# --- CÉREBRO ESPECÍFICO DA SKILL (MACRO EXPERT) ---
MACRO_DECISION_PROMPT = load_prompt("skills/work_macro_decision.md")

# --- DEFINIÇÃO DAS CENAS ---
SCENES = {
    "code": {
        # Spotify sai da lista: _start_playlist() já lança o app via URI da playlist.
        "apps": ["opera gx", "visual studio code", "terminal"],
        "message": "Protocolo de desenvolvimento ativado.",
        "requires_internet": True,
        "playlist": "spotify:playlist:0XkPXLnaDEjO04Z3ZvrHIk" # Só ROCK
    },
    "estudo": {
        # Idem: o Spotify é aberto pelo bloco de trilha sonora.
        "apps": ["opera gx"],
        "message": "Modo de concentração ativado.",
        "requires_internet": True,
        "playlist": "spotify:playlist:5aofQDdd0buo5bRre6yMlG" # MPB
    },
    "gamer": {
        "apps": ["discord", "steam"],
        "message": "Sistemas de entretenimento online. Boa gameplay, senhor.",
        "requires_internet": True,
    }
}


def check_internet():
    """Verifica conectividade básica."""
    try:
        requests.get("https://www.google.com", timeout=3)
        return True
    except:
        return False

def _start_playlist(uri):
    """Inicia a trilha sonora da cena. Nunca levanta exceção.

    Caminho preferencial é a Web API (controle real do player). O `start_uri`
    local continua como rede de segurança para quando não há autorização,
    Premium ou dispositivo utilizável — foi o único mecanismo por muito tempo
    e segue sendo o que funciona com o Spotify fechado e sem token.
    """
    if spotify.is_authorized():
        device_id = ensure_device_ready()
        if spotify.play(context_uri=uri, device_id=device_id):
            log.debug("🎧 Trilha sonora iniciada pela Web API.")
            return True
        log.debug("Web API não iniciou a playlist. Caindo para o app local...")

    return start_uri(uri)

def _ask_ollama_macro_expert(user_text):
    """Consulta o LLM para decidir qual macro ativar."""
    url = f"http://{settings.OLLAMA_HOST}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": user_text,
        "system": MACRO_DECISION_PROMPT,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1}
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json().get("response", "{}")
    except Exception as e:
        log.error(f"❌ [MACRO SKILL] Erro no cérebro (Timeout/Conexão): {e}")
        return None

def execute_app_action(app_name, action="open"):
    """Reutiliza a skill APP_CONTROL para abrir os apps da macro."""
    from core import manager

    if "APP_CONTROL" in manager.skills:
        skill = manager.skills["APP_CONTROL"]

        # Tentamos silenciar a saída do processo aberto via variável de ambiente
        # ou redirecionamento se a skill permitir.
        # Por enquanto, apenas chamamos; a poluição vem geralmente do Popen sem shell=True
        return skill.execute(app_name, f"{action} {app_name}")
    return f"Não consegui acessar o subsistema de controle de apps para {app_name}."

def toggle_notifications(enabled=True):
    """Ativa ou desativa as notificações do Windows (Foco / DND)."""
    value = 1 if enabled else 0
    try:
        cmd = f'powershell -Command "Set-ItemProperty -Path \'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Notifications\\Settings\' -Name \'NOC_GLOBAL_SETTING_TOASTS_ENABLED\' -Value {value}"'
        os.system(cmd)
        log.info(f"🔔 Notificações do sistema {'ativadas' if enabled else 'silenciadas'}.")
        return True
    except Exception as e:
        log.error(f"Erro ao alternar notificações: {e}")
        return False

def organize_windows(mode):
    """
    Organiza as janelas baseando-se na qtde de monitores e no Modo.
    Usa um script PowerShell robusto injetado diretamente.
    """
    log.info("📐 Calculando layout de janelas...")

    # Script PowerShell Híbrido: C# para User32.dll + Lógica de Monitores
    ps_script = """
    Add-Type @"
      using System;
      using System.Runtime.InteropServices;
      public class Win32 {
        [DllImport("user32.dll")]
        public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
        [DllImport("user32.dll")]
        public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
        [DllImport("user32.dll")]
        public static extern bool SetForegroundWindow(IntPtr hWnd);
      }
"@

    # 1. Detectar Monitores
    Add-Type -AssemblyName System.Windows.Forms
    $screens = [System.Windows.Forms.Screen]::AllScreens
    $monitorCount = $screens.Count
    $prim = $screens[0].WorkingArea

    # Definição de Alvos (Process Name -> Variável)
    # Tenta pegar processos com janela visível
    $code = Get-Process -Name "Code" -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowHandle -ne 0} | Select-Object -First 1
    $browser = Get-Process -Name "opera", "chrome", "msedge" -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowHandle -ne 0} | Select-Object -First 1
    $term = Get-Process -Name "WindowsTerminal", "cmd", "powershell" -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowHandle -ne 0} | Select-Object -First 1
    $spotify = Get-Process -Name "Spotify" -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowHandle -ne 0} | Select-Object -First 1

    # --- MODO CODE ---
    if ("%MODE%" -eq "code") {
        if ($monitorCount -eq 1) {
            # 1 Monitor: VS Code (70%), Browser (30%)
            $wCode = [math]::Floor($prim.Width * 0.70)
            $wBrowser = $prim.Width - $wCode

            if ($code) {
                [Win32]::ShowWindow($code.MainWindowHandle, 1) # Ensure Normal State
                [Win32]::MoveWindow($code.MainWindowHandle, $prim.Left, $prim.Top, $wCode, $prim.Height, $true)
            }
            if ($browser) {
                [Win32]::ShowWindow($browser.MainWindowHandle, 1)
                [Win32]::MoveWindow($browser.MainWindowHandle, $prim.Left + $wCode, $prim.Top, $wBrowser, $prim.Height, $true)
            }
        }
        else {
            # 2+ Monitores: VS Code (Monitor 1), Browser (Monitor 2)
            $sec = $screens[1].WorkingArea

            if ($code) {
                [Win32]::ShowWindow($code.MainWindowHandle, 3) # Maximize
                [Win32]::MoveWindow($code.MainWindowHandle, $prim.Left, $prim.Top, $prim.Width, $prim.Height, $true)
            }
            if ($browser) {
                 [Win32]::ShowWindow($browser.MainWindowHandle, 1) # Normal (para mover entre telas as vezes precisa)
                 [Win32]::MoveWindow($browser.MainWindowHandle, $sec.Left, $sec.Top, $sec.Width, $sec.Height, $true)
                 [Win32]::ShowWindow($browser.MainWindowHandle, 3) # Maximize depois de mover
            }
        }
    }

    # --- MODO ESTUDO ---
    if ("%MODE%" -eq "estudo") {
         # Exemplo: Browser Esquerda (50%), Notion Direita (50%)
         # Adaptar conforme necessidade do Notion (geralmente é app web ou desktop name 'Notion')
         $notion = Get-Process -Name "Notion" -ErrorAction SilentlyContinue | Select-Object -First 1

         $half = [math]::Floor($prim.Width * 0.5)

         if ($browser) { [Win32]::MoveWindow($browser.MainWindowHandle, $prim.Left, $prim.Top, $half, $prim.Height, $true) }
         if ($notion) { [Win32]::MoveWindow($notion.MainWindowHandle, $prim.Left + $half, $prim.Top, $half, $prim.Height, $true) }
    }
    """

    # Injeta o modo atual no script
    final_script = ps_script.replace("%MODE%", mode)

    try:
        # Executa silenciosamente
        subprocess.Popen(["powershell", "-Command", final_script], shell=True)
        log.info(f"🪟 Layout de janelas aplicado para modo {mode}.")
    except Exception as e:
        log.error(f"Erro ao organizar janelas: {e}")

def execute(entity, command_text=""):
    # Importação Tardia de Speak para Feedback Verbal Imediato
    from services.speak import speak

    if not command_text:
        return "Qual protocolo de ambiente devo iniciar, senhor?"

    # 1. Pergunta ao cérebro qual o modo
    ai_response = _ask_ollama_macro_expert(command_text)
    if not ai_response:
        return "Falha na triangulação de dados. Não consigo processar a macro agora."

    try:
        decision = json.loads(ai_response)
        mode = decision.get("mode")

        if mode not in SCENES or mode == "outro":
             return "Esse perfil de ambiente ainda não consta nos meus protocolos, senhor."

        scene = SCENES[mode]

        # --- FATOR IMERSÃO: Confirmação Verbal ---
        speak(f"Carregando protocolo {mode}, senhor. Ajustando ambiente.")

        # 2. Executa as ações
        log.info(f"🎭 Ativando Cena: {mode.upper()}")

        if mode == "estudo":
            toggle_notifications(enabled=False)
        else:
            toggle_notifications(enabled=True)

        # 3. System Check (Internet)
        if scene.get("requires_internet") and not check_internet():
            return "Senhor, detectei que estamos sem conexão com a internet. Não poderei iniciar este protocolo online."

        # 4. Abre os apps da cena selecionada
        for app in scene["apps"]:
            log.debug(f"Macros: Verificando {app}...")
            execute_app_action(app, action="open")
            time.sleep(1.5)

        # 5. FATOR IMERSÃO: Trilha Sonora
        # Web API quando autorizado; app local como fallback.
        if "playlist" in scene:
            log.info(f"🎵 Iniciando trilha sonora: {scene['playlist']}")
            _start_playlist(scene["playlist"])

        # 6. Organiza as janelas
        # Mantido em 3s: o Tiling depende do MainWindowHandle do VS Code existir,
        # e a espera do Spotify retorna na hora quando ele já estava aberto.
        time.sleep(3)
        organize_windows(mode)

        return f"{scene['message']} Sistema pronto."

    except Exception as e:
        log.error(f"Erro na Skill de Macros: {e}")
        return "Detectada instabilidade ao tentar configurar o ambiente de trabalho."
