import os
import secrets
import sys
import threading
import time

import webview

# Token de sessão criptográfico único para todas as interações de voz do ciclo de execução atual
voice_session_id = f"voice_{secrets.token_urlsafe(32)}"

# Importa as configurações, o Logger e agora a Memória (Database)
from core import JarvisAPI, db, log, manager, obsidian, settings

# --- IMPORTAÇÃO DOS MÓDULOS ---
try:
    log.debug("Carregando serviços cognitivos (Audição, Fala, Cérebro)...")
    from core.alerts import process_system_alert
    from core.llm import warm_up_ollama
    from core.state import sys_monitor
    from services.brain import execute_command
    from services.listen import ear_pause, ear_resume, listen
    from services.speak import speak
    log.info("Serviços cognitivos carregados com sucesso.")
except ImportError as e:
    log.critical(f"Falha na importação dos módulos de serviço: {e}")
    sys.exit(1)

is_running = True
window_instance = None

def update_ui(status, message=""):
    global window_instance
    if window_instance and is_running:
        # Garante que message seja string para evitar erro no replace se vier None
        msg_str = str(message) if message else ""
        clean_msg = msg_str.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", " ")
        
        # Se mensagem for vazia, chamamos apenas com status (depende do seu JS)
        # Mas para segurança, enviamos os dois
        script = f"if(window.receiveStatus) {{ window.receiveStatus('{status}', '{clean_msg}'); }}"
        try:
            window_instance.evaluate_js(script)
        except Exception as e:
            log.error(f"Erro na Bridge: {e}")
            
# Wrapper para garantir que a UI também saiba dos alertas de hardware
def ui_aware_alert_callback(message, is_proactive=False, is_status_signal=False):
    # Se for apenas uma mudança de estado (Ligar/Desligar luz vermelha)
    if is_status_signal:
        if message == "CRITICAL_START":
            api.set_hud_state(True) # Liga o vermelho
        elif message == "CRITICAL_END":
            api.set_hud_state(False) # Desliga o vermelho
        return # Não fala nada, só muda a luz

    # Se for aviso de fala normal (mantém lógica antiga)
    if is_proactive:
        if api:
            api.send_frontend_alert("WARNING", message)
        update_ui("WARNING", f"ALERTA: {message}")
    
    process_system_alert(message, is_proactive)

# --- CICLO DE VIDA DO JARVIS ---
def jarvis_auto_loop():
    global is_running, window_instance
    
    time.sleep(4)
    log.info("Interface Gráfica Conectada. Loop principal ativo.")
    sys_monitor.brain_callback = ui_aware_alert_callback
    sys_monitor.start_proactive_monitor(interval=3)  # Verificações a cada 3 segundos
    api.start_telemetry_stream(settings.TELEMETRY_INTERVAL)  # Push delta-gated p/ a UI

    while is_running:
        try:
            log.debug("Estado: Ouvindo...")
            update_ui("LISTENING", "Aguardando comando...")
            
            command = listen()

            if command and is_running:
                # SALVAR NO HISTÓRICO (Entrada do Usuário)
                db.log_interaction("user", command, voice_session_id)
                
                log.info(f"Comando recebido: '{command}'")
                update_ui("PROCESSING", f"Processando: {command}")
                response_text = execute_command(command, session_id=voice_session_id)

                if response_text == "PROTOCOL_SHUTDOWN":
                    log.warning("Iniciando sequência de encerramento total.")
                    update_ui("PROCESSING", "Desconectando...")
                    
                    try:
                        ear_pause()
                        speak("Desativando núcleo de força. Até logo, Senhor.")
                    finally:
                        is_running = False
                        if window_instance:
                            window_instance.destroy() # Fecha a interface gráfica
                        
                        log.info("Aplicação encerrada com sucesso.")
                        os._exit(0) # Mata todos os processos e threads imediatamente
                        break

                if response_text:
                    # SALVAR NO HISTÓRICO (Resposta do JARVIS)
                    db.log_interaction("assistant", response_text, voice_session_id)
                    
                    def on_audio_start():
                        update_ui("SPEAKING", response_text)
                    
                    try:
                        ear_pause()
                        speak(response_text, play_callback=on_audio_start)
                    finally:
                        ear_resume()
                        update_ui("IDLE", "")
                        
        except Exception as e:
            log.error(f"Erro no loop principal: {e}")
            time.sleep(1)
    
    log.info("Loop principal encerrado.")

def do_boot_greeting():
    if "SYSTEM_REPORT" in manager.skills:
        msg = manager.skills["SYSTEM_REPORT"].execute(None, "boot_protocol_auto")
    else:
        user_name = obsidian.get_memory("nome") or "Senhor"
        msg = f"Sistemas sincronizados. Bem-vindo de volta, {user_name}."
    update_ui("SPEAKING", msg)
    speak(msg)
    update_ui("IDLE", "")

# --- API JS <-> PYTHON ---
window_instance = None
api = JarvisAPI(sys_monitor)
api.boot_greeting_fn = do_boot_greeting

# --- INICIALIZAÇÃO ---
def start_jarvis():
    global window_instance, api
    settings.perform_sanity_check()
    log.info(f"Inicializando {settings.PROJECT_NAME} v{settings.VERSION}")
    html_path = str(settings.DIR_ROOT / 'frontend' / 'dist' / 'index.html')

    if not os.path.exists(html_path):
        log.critical(f"Frontend não encontrado em: {html_path}")
        window_instance = webview.create_window('Erro', html='<h1>Erro Crítico: Frontend não encontrado</h1>')
        return
        
    window_instance = webview.create_window(
        title=settings.PROJECT_NAME,
        url=html_path,
        js_api=api,
        width=1280,
        height=800,
        fullscreen=False,
        frameless=True,
        resizable=True,
        background_color='#000000',
        easy_drag=False,
    )

    api.set_window(window_instance)

    # Warm-up do Ollama em paralelo à renderização da UI (esconde a latência do
    # 1º comando; com keep_alive=-1 o modelo fica residente na VRAM).
    threading.Thread(target=warm_up_ollama, daemon=True).start()

    t = threading.Thread(target=jarvis_auto_loop, daemon=True)
    t.start()

    def on_shown():
        window_instance.maximize()

    window_instance.events.shown += on_shown

    webview.start(debug=settings.DEBUG)

if __name__ == '__main__':
    try:
        start_jarvis()
    except KeyboardInterrupt:
        log.info("Aplicação finalizada pelo usuário.")
        import os
        os._exit(0)