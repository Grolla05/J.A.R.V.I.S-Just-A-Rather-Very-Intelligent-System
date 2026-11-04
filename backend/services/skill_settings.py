"""Ativação/desativação de skills e categorias (persistido no SQLite `config`).

Extraído da antiga JarvisAPI para o comando /skills da TUI.
"""
from core.database import db
from core.logger import log
from core.skill_loader import manager


def list_skills():
    """Lista de categorias: {id, enabled, skills: [{id, enabled}]}, ordenadas."""
    disabled_skills = db.get_config("disabled_skills") or []
    disabled_categories = db.get_config("disabled_categories") or []

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
