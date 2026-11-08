"""Clima e saudação compartilhados (status report e briefing diário).

Clima via Open-Meteo, com geolocalização por IP (ip-api) guardada no Obsidian
para os próximos boots. Fallback de coordenadas: São Paulo.
"""
import datetime

from core.logger import log

# Cache em memória de execução para evitar requisições redundantes de geolocalização
_geo = {"lat": None, "lon": None, "city": None}
_FALLBACK = ("-23.5505", "-46.6333")  # São Paulo


def get_time_greeting(user_name, now=None):
    hour = (now or datetime.datetime.now()).hour
    if 0 <= hour < 5:
        return f"Madrugada produtiva, {user_name}?"
    if 5 <= hour < 12:
        return f"Bom dia, {user_name}."
    if 12 <= hour < 18:
        return f"Boa tarde, {user_name}."
    return f"Boa noite, {user_name}."


def _condition(wmo_code):
    if wmo_code is None:
        return "condição desconhecida"
    if wmo_code > 80:
        return "chuva forte"
    if wmo_code > 50:
        return "chuva leve"
    if wmo_code > 3:
        return "nublado"
    return "céu limpo"


def _locate():
    """Coordenadas: cache → Obsidian → ip-api (e salva no Obsidian)."""
    if _geo["lat"] and _geo["lon"]:
        return
    from core.obsidian import obsidian
    lat, lon = obsidian.get_memory("latitude"), obsidian.get_memory("longitude")
    if lat and lon:
        city = obsidian.get_memory("cidade")
        _geo.update(lat=str(lat), lon=str(lon), city=str(city) if city else None)
        return
    try:
        import requests
        res = requests.get("http://ip-api.com/json/", timeout=2.5)
        data = res.json() if res.status_code == 200 else {}
        if data.get("status") == "success":
            _geo.update(lat=str(data.get("lat")), lon=str(data.get("lon")), city=data.get("city"))
            obsidian.save_memory("latitude", _geo["lat"])
            obsidian.save_memory("longitude", _geo["lon"])
            if _geo["city"]:
                obsidian.save_memory("cidade", _geo["city"])
    except Exception as geo_err:
        log.error(f"Erro na geolocalização automática por IP: {geo_err}")


def get_weather_context():
    """'24.1°C em Cidade com céu limpo.' — ou None se o clima não responder."""
    try:
        import requests
        _locate()
        lat = _geo["lat"] or _FALLBACK[0]
        lon = _geo["lon"] or _FALLBACK[1]
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        res = requests.get(url, timeout=3)
        if res.status_code != 200:
            return None
        data = res.json().get("current_weather", {})
        location_label = f" em {_geo['city']}" if _geo["city"] else ""
        return f"{data.get('temperature')}°C{location_label} com {_condition(data.get('weathercode'))}."
    except Exception as e:
        log.error(f"Erro ao capturar clima dinâmico: {e}")
        return None
