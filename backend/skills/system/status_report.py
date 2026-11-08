from core import log, obsidian
from core.prompts import load_prompt
from core.SystemInfo import SystemInfo
from core.weather import get_time_greeting, get_weather_context

# --- CONFIGURAÇÃO DA SKILL ---
INTENT = "SYSTEM_REPORT"
PROMPT_TEXT = load_prompt("skills/status_report.md")

# Instanciamos um monitor para leituras
sys_monitor = SystemInfo()

def generate_boot_report():
    """Gera um relatório verbal conciso sobre o estado do JARVIS."""
    
    # 1. Recupera identidade
    user_name = obsidian.get_memory("apelido") or "Senhor"
    greeting = get_time_greeting(user_name)
    
    # 2. Leitura de Sensores
    batt = sys_monitor.get_battery_status()
    cpu = sys_monitor.get_cpu_usage()
    ram = sys_monitor.get_ram_usage()
    
    # 3. Análise de Saúde (Triage)
    alerts = []
    
    # Bateria
    batt_desc = f"{batt['percent']}%"
    if not batt['plugged'] and batt['percent'] < 30:
        alerts.append("reservas de energia baixas")
    
    # Carga
    if cpu > 80:
        alerts.append("núcleo de processamento sobrecarregado")
    if ram['percent'] > 90:
        alerts.append("memória saturada")

    # 4. Construção da Narrativa (Estilo Jarvis)
    # Ex: "Boa noite, Senhor. Interface conectada. Capacidade de energia em 100%. Todos os sistemas operando nominalmente."
    
    status_phrases = [greeting]
    
    status_phrases.append("Interface conectada.")
    
    if batt['plugged']:
         status_phrases.append(f"Fonte de alimentação externa acoplada. Carga em {batt_desc}.")
    else:
         status_phrases.append(f"Operando na bateria interna com {batt_desc} de capacidade.")
    
    if alerts:
        alert_msg = " e ".join(alerts)
        status_phrases.append(f"Atenção: Detectado {alert_msg}.")
    else:
        status_phrases.append("Todos os subsistemas operando dentro dos parâmetros nominais.")
        
    # Adiciona Clima
    weather = get_weather_context()
    if weather:
        status_phrases.append(f"No ambiente externo: {weather}")
    
    # Adiciona Ping (Latência Neural)
    ping = sys_monitor.get_ping()
    if ping:
        status_phrases.append(f"Latência de conexão neural em {ping}ms.")
    else:
        status_phrases.append("Atenção: Link neural offline.")
        
    return " ".join(status_phrases)

def execute(entity, command):
    log.info("📊 [STATUS] Executando Protocolo de Relatório.")
    return generate_boot_report()
