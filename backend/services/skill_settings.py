"""Ativação/desativação de skills e categorias (persistido no SQLite `config`).

Extraído da antiga JarvisAPI para o comando /skills da TUI.
"""
import threading

from core.database import db
from core.logger import log
from core.skill_loader import manager

# Cache das listas de desligados: o classificador consulta toda skill em toda
# mensagem; sem isto eram ~80 conexões SQLite por mensagem. Só este módulo
# grava as chaves, então `_toggle` invalida e o cache nunca fica velho.
_disabled_cache = None
_cache_lock = threading.Lock()


def disabled_sets():
    """(skills desligadas, categorias desligadas) como frozensets, em cache."""
    global _disabled_cache
    with _cache_lock:
        if _disabled_cache is None:
            _disabled_cache = (frozenset(db.get_config("disabled_skills") or ()),
                               frozenset(db.get_config("disabled_categories") or ()))
        return _disabled_cache


def invalidate_cache():
    global _disabled_cache
    with _cache_lock:
        _disabled_cache = None


def list_skills():
    """Lista de categorias: {id, enabled, skills: [{id, enabled}]}, ordenadas."""
    disabled_skills, disabled_categories = disabled_sets()

    categories = {}
    for intent, module in manager.skills.items():
        cat = getattr(module, "CATEGORY", "system")
        cat_enabled = cat not in disabled_categories
        item = categories.setdefault(cat, {"id": cat, "enabled": cat_enabled, "skills": []})
        item["skills"].append({"id": intent, "enabled": cat_enabled and intent not in disabled_skills})

    result = sorted(categories.values(), key=lambda c: c["id"])
    for cat in result:
        cat["skills"].sort(key=lambda s: s["id"])
    return result


def _toggle(config_key, item_id, enabled):
    disabled = db.get_config(config_key) or []
    if enabled and item_id in disabled:
        disabled.remove(item_id)
    elif not enabled and item_id not in disabled:
        disabled.append(item_id)
    db.save_config(config_key, disabled)
    invalidate_cache()


def set_enabled(target, enabled):
    """Liga/desliga uma skill (pelo INTENT) ou uma categoria inteira (pelo nome
    da pasta). Retorna 'skill', 'category' ou None se o alvo não existe."""
    skill_ids = {s.upper(): s for s in manager.skills}
    # Busca sem diferenciar maiúsculas, mas grava o nome exato da pasta
    # (is_skill_enabled compara literal, ex: "IoT").
    categories = {getattr(m, "CATEGORY", "system").lower(): getattr(m, "CATEGORY", "system")
                  for m in manager.skills.values()}
    try:
        if target.upper() in skill_ids:
            _toggle("disabled_skills", skill_ids[target.upper()], enabled)
            return "skill"
        if target.lower() in categories:
            _toggle("disabled_categories", categories[target.lower()], enabled)
            return "category"
    except Exception as e:
        log.error(f"Erro ao alternar '{target}': {e}")
    return None
