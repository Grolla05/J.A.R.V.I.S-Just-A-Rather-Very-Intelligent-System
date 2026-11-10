"""Trânsito entre locais fixos para o briefing, a skill TRAFFIC e o aviso de saída.

- Locais: `/rota <local> <endereço>` (casa, trabalho, faculdade, escola, academia…)
  → geocodificado uma vez no Nominatim (OpenStreetMap) e guardado na tabela `config`
  (`commute_home`/`commute_work` para casa/trabalho, `place_<local>` para os outros;
  `places_index` lista os nomes). O `/rota` só cadastra: quem calcula é a skill TRAFFIC.
- Briefing e aviso de saída usam casa ⇄ trabalho.
- Rota: com `TOMTOM_API_KEY` usa o TomTom (trânsito ao vivo + tempo sem trânsito);
  sem chave, OSRM público (tempo médio da rota, sem congestionamento).
- Sentido: até 15 h casa → trabalho; depois, trabalho → casa.

Funções públicas nunca levantam: falha vira log + None/texto amigável.
"""
import datetime
import json
import re
import unicodedata

from core.config import settings
from core.logger import log

PLACES = {"casa": "commute_home", "trabalho": "commute_work"}  # chaves antigas, mantidas
INDEX_KEY = "places_index"
ALIASES = {"home": "casa", "lar": "casa", "work": "trabalho", "servico": "trabalho", "escritorio": "trabalho",
           "empresa": "trabalho", "faculdade": "faculdade", "facul": "faculdade", "universidade": "faculdade",
           "colegio": "escola"}
ALERT_LAST_KEY = "commute_alert_last"
EVENING_HOUR = 15
TIMEOUT = 6
USER_AGENT = "JARVIS-assistant/1.0"  # Nominatim exige um User-Agent identificável
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{a_lon},{a_lat};{b_lon},{b_lat}"
TOMTOM_URL = "https://api.tomtom.com/routing/1/calculateRoute/{a_lat},{a_lon}:{b_lat},{b_lon}/json"
TOMTOM_SIGNUP_URL = "https://developer.tomtom.com/user/register"

NO_PLACES = "Defina a rota primeiro, Senhor: `/rota casa <endereço>` e `/rota trabalho <endereço>`."
ROTA_USAGE = "Uso: `/rota <local> <endereço>` — ex.: `/rota faculdade Av. Paulista, 1000, São Paulo`."


def _db():
    from core.database import db
    return db


def _requests():
    import requests
    return requests


def _get_json(url, params=None, headers=None):
    r = _requests().get(url, params=params or {}, headers=headers or {}, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}")
    return r.json()


# ---------------------------------------------------------------- lugares
def geocode(address):
    """Endereço → {'address', 'lat', 'lon', 'label'} ou None."""
    try:
        data = _get_json(NOMINATIM_URL, {"q": address, "format": "json", "limit": 1},
                         {"User-Agent": USER_AGENT, "Accept-Language": "pt-BR"})
    except Exception as e:
        log.warning(f"Trânsito: geocodificação falhou: {e}")
        return None
    if not data:
        return None
    hit = data[0]
    label = ", ".join(str(hit.get("display_name", address)).split(", ")[:3])
    return {"address": address, "lat": float(hit["lat"]), "lon": float(hit["lon"]), "label": label}


def _plain(text):
    text = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def normalize_tag(tag):
    """'Faculdade' → 'faculdade'; 'home' → 'casa'; 'Casa da Mãe' → 'casa_da_mae'. '' se inválido."""
    plain = _plain(tag)
    plain = ALIASES.get(plain, plain)
    slug = re.sub(r"[^a-z0-9]+", "_", plain).strip("_")
    return slug[:30]


def tag_label(tag):
    return tag.replace("_", " ")


def _key(tag):
    return PLACES.get(tag) or f"place_{tag}"


def _index():
    try:
        raw = _db().get_config(INDEX_KEY)
        tags = json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
    except Exception:
        tags = []
    tags = [t for t in tags if isinstance(t, str)] if isinstance(tags, list) else []
    return [t for t in PLACES if t not in tags] + tags  # casa/trabalho sempre conferidos


def get_place(kind):
    tag = normalize_tag(kind)
    if not tag:
        return None
    try:
        raw = _db().get_config(_key(tag))
        place = json.loads(raw) if isinstance(raw, str) and raw else raw
    except Exception:
        return None
    return place if isinstance(place, dict) and "lat" in place and "lon" in place else None


def list_places():
    """{tag: lugar} só dos locais cadastrados, na ordem de cadastro (casa/trabalho primeiro)."""
    return {tag: place for tag in _index() if (place := get_place(tag))}


def set_place(kind, address, geocoder=None):
    """Salva um local fixo (casa, trabalho, faculdade…). Devolve o texto para o usuário."""
    tag = normalize_tag(kind)
    if not tag:
        return ROTA_USAGE
    label = tag_label(tag)
    address = (address or "").strip()
    if not address:
        return f"Qual o endereço de {label}, Senhor? {ROTA_USAGE}"
    place = (geocoder or geocode)(address)
    if not place:
        return f"Não encontrei \"{address}\" no mapa. Tente rua, número e cidade."
    db = _db()
    db.save_config(_key(tag), json.dumps(place, ensure_ascii=False))
    tags = _index()
    if tag not in tags:
        tags.append(tag)
    db.save_config(INDEX_KEY, json.dumps([t for t in tags if t not in PLACES], ensure_ascii=False))
    return f"Endereço de {label} salvo: {place['label']}."


def places_text():
    """Resposta do `/rota` sem argumento: locais cadastrados."""
    places = list_places()
    if not places:
        return f"Nenhum local cadastrado, Senhor. {ROTA_USAGE}"
    lines = [f"- **{tag_label(tag).capitalize()}:** {place.get('label', place.get('address', ''))}"
             for tag, place in places.items()]
    return ("**Locais cadastrados**\n\n" + "\n".join(lines)
            + "\n\nPergunte o trânsito em linguagem natural (\"quanto tempo até a faculdade?\").")


def clear_places():
    db = _db()
    for tag in _index():
        db.save_config(_key(tag), "")
    db.save_config(INDEX_KEY, "[]")


def has_places():
    return bool(get_place("casa") and get_place("trabalho"))


def source_name():
    return "TomTom" if settings.TOMTOM_API_KEY else "OSRM"


# ------------------------------------------------------------------- rota
def _tomtom(a, b):
    data = _get_json(TOMTOM_URL.format(a_lat=a["lat"], a_lon=a["lon"], b_lat=b["lat"], b_lon=b["lon"]),
                     {"key": settings.TOMTOM_API_KEY, "traffic": "true", "computeTravelTimeFor": "all"})
    summary = data["routes"][0]["summary"]
    minutes = round(summary["travelTimeInSeconds"] / 60)
    free = summary.get("noTrafficTravelTimeInSeconds")
    return {"minutes": minutes, "typical": round(free / 60) if free else None, "source": "TomTom"}


def _osrm(a, b):
    data = _get_json(OSRM_URL.format(a_lat=a["lat"], a_lon=a["lon"], b_lat=b["lat"], b_lon=b["lon"]),
                     {"overview": "false"})
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(data.get("code") or "sem rota")
    return {"minutes": round(data["routes"][0]["duration"] / 60), "typical": None, "source": "OSRM"}


def route(a, b):
    """Tempo de a até b — TomTom (com chave) ou OSRM. None se falhar."""
    try:
        if settings.TOMTOM_API_KEY:
            try:
                return _tomtom(a, b)
            except Exception as e:
                log.warning(f"Trânsito: TomTom falhou ({e}); usando OSRM.")
        return _osrm(a, b)
    except Exception as e:
        log.warning(f"Trânsito: rota indisponível: {e}")
        return None


def direction(now=None):
    """('casa', 'trabalho') de manhã; invertido depois de EVENING_HOUR."""
    hour = (now or datetime.datetime.now()).hour
    return ("trabalho", "casa") if hour >= EVENING_HOUR else ("casa", "trabalho")


def describe(origin, dest, result):
    """'Casa → trabalho: 34 min (+9 pelo trânsito, TomTom).'"""
    head = f"{origin.capitalize()} → {dest}: {result['minutes']} min"
    if result["source"] == "OSRM":
        return f"{head} (estimativa sem trânsito ao vivo, OSRM)."
    extra = (result["minutes"] - result["typical"]) if result.get("typical") else 0
    if extra >= 3:
        return f"{head} (+{extra} pelo trânsito, TomTom)."
    return f"{head} (trânsito livre, TomTom)."


def commute_line(now=None):
    """Linha do deslocamento agora — None sem endereços ou se a rota falhar."""
    origin, dest = direction(now)
    a, b = get_place(origin), get_place(dest)
    if not (a and b):
        return None
    result = route(a, b)
    return describe(origin, dest, result) if result else None


def commute_text(now=None):
    """Casa ⇄ trabalho agora (sentido pelo horário) ou o que falta."""
    if not has_places():
        return NO_PLACES
    return commute_line(now) or "Não consegui calcular a rota agora, Senhor."


def trip_text(origin, dest):
    """Tempo entre dois locais cadastrados (tags) ou o que falta."""
    a, b = get_place(origin), get_place(dest)
    missing = [tag_label(t) for t, p in ((origin, a), (dest, b)) if not p]
    if missing:
        return f"Não tenho o endereço de {' e '.join(missing)}, Senhor. {ROTA_USAGE}"
    if normalize_tag(origin) == normalize_tag(dest):
        return f"Você já está em {tag_label(dest)}, Senhor."
    result = route(a, b)
    if not result:
        return "Não consegui calcular a rota agora, Senhor."
    return describe(tag_label(normalize_tag(origin)), tag_label(normalize_tag(dest)), result)


# ------------------------------------------------------------ aviso de saída
def alert_due(pref_minutes, now, last_date):
    """O aviso de saída deve disparar agora? Dias úteis, a partir do horário escolhido
    (até 60 min depois) e uma vez por dia. `pref_minutes` 0 = desligado."""
    if not pref_minutes or now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return pref_minutes <= minutes < pref_minutes + 60 and last_date != now.date().isoformat()
