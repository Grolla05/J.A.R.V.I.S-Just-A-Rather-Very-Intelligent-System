import datetime

import requests

from core import log, obsidian
from core.prompts import load_prompt
from core.SystemInfo import SystemInfo

# --- CONFIGURAÇÃO DA SKILL ---
INTENT = "SYSTEM_REPORT"
PROMPT_TEXT = load_prompt("skills/status_report.md")

# Instanciamos um monitor para leituras
sys_monitor = SystemInfo()

def get_time_greeting(user_name):
    hour = datetime.datetime.now().hour
    if 0 <= hour < 5: 
        return f"Madrugada produtiva, {user_name}?"
    if 5 <= hour < 12: 
        return f"Bom dia, {user_name}."
    if 12 <= hour < 18: 
        return f"Boa tarde, {user_name}."
    return f"Boa noite, {user_name}."

# Cache em memória de execução para evitar requisições redundantes de geolocalização
_cached_lat = None
_cached_lon = None
_cached_city = None

def get_weather_context():
    """Busca dados de clima via Open-Meteo baseando-se na geolocalização automática por IP do usuário."""
    global _cached_lat, _cached_lon, _cached_city
    
    try:
        # Se as coordenadas ainda não estão em cache na execução atual
        if not _cached_lat or not _cached_lon:
            # Tenta buscar da memória de longo prazo (Obsidian)
            lat = obsidian.get_memory("latitude")
            lon = obsidian.get_memory("longitude")
            city = obsidian.get_memory("cidade")
            
            if lat and lon:
                _cached_lat = str(lat)
                _cached_lon = str(lon)
                _cached_city = str(city) if city else None
            else:
                # Tenta realizar geolocalização automática por IP
                try:
                    geo_res = requests.get("http://ip-api.com/json/", timeout=2.5)
                    if geo_res.status_code == 200:
                        geo_data = geo_res.json()
                        if geo_data.get("status") == "success":
                            _cached_lat = str(geo_data.get("lat"))
                            _cached_lon = str(geo_data.get("lon"))
                            _cached_city = geo_data.get("city")
                            
                            # Salva na memória do Obsidian para velocidade em boots futuros
                            obsidian.save_memory("latitude", _cached_lat)
                            obsidian.save_memory("longitude", _cached_lon)
                            if _cached_city:
                                obsidian.save_memory("cidade", _cached_city)
                except Exception as geo_err:
                    log.error(f"Erro na geolocalização automática por IP: {geo_err}")
        
        # Fallback definitivo para São Paulo se a geolocalização falhar por completo
        lat = _cached_lat or "-23.5505"
        lon = _cached_lon or "-46.6333"
        city = _cached_city
        
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        res = requests.get(url, timeout=3)
        
        if res.status_code == 200:
            data = res.json().get('current_weather', {})
            temp = data.get('temperature')
            
            wmo_code = data.get('weathercode')
            condition = "céu limpo"
            if wmo_code > 3: condition = "nublado"
            if wmo_code > 50: condition = "chuva leve"
            if wmo_code > 80: condition = "chuva forte"
            
            location_label = f" em {city}" if city else ""
            return f"{temp}°C{location_label} com {condition}."
    except Exception as e:
        log.error(f"Erro ao capturar clima dinâmico: {e}")
        return None
    return None

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
