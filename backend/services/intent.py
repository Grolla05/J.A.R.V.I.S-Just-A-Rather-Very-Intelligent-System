import json

from core.config import settings
from core.llm import query_ollama
from core.logger import log
from core.prompts import load_prompt
from core.skill_loader import manager
from core.utils import TTLCache

# Memoiza classificações recentes: repetir o mesmo comando em <TTL s não
# desperdiça uma nova ida ao Ollama. Chave = (texto normalizado, skip_skills, categorias excluídas).
_intent_cache = TTLCache(maxsize=settings.INTENT_CACHE_SIZE, ttl=settings.INTENT_CACHE_TTL)

# Categorias que só rodam no Copilot/voz: mexem no PC (automation) ou no sistema
# (limpeza, processos, desligar). No Chat ficam de fora do classificador.
CHAT_BLOCKED_CATEGORIES = ("automation", "system")


def skill_category(intent):
    return getattr(manager.skills.get(intent), "CATEGORY", None)


def skill_allowed_in_chat(intent):
    """Skill pode rodar no modo Chat? (categoria fora de CHAT_BLOCKED_CATEGORIES)"""
    return intent in manager.skills and skill_category(intent) not in CHAT_BLOCKED_CATEGORIES


def _disabled_sets():
    from services import skill_settings  # tardio: skill_settings não importa intent, mas evita ciclo no boot
    return skill_settings.disabled_sets()


def is_skill_enabled(intent, disabled=None):
    """A skill e a categoria dela estão ativas? `disabled` = (skills, categorias)
    já lidas — o classificador lê uma vez e reaproveita para todas as skills."""
    try:
        disabled_skills, disabled_categories = disabled if disabled is not None else _disabled_sets()

        if intent in disabled_skills:
            return False

        skill_module = manager.skills.get(intent)
        if skill_module:
            category = getattr(skill_module, "CATEGORY", None)
            if category and category in disabled_categories:
                return False

        return True
    except Exception as e:
        log.error(f"Erro ao avaliar ativação da skill '{intent}': {e}")
        return True


def _offered_skills(exclude_categories):
    """Skills ativas fora das categorias excluídas (uma leitura do SQLite no máximo)."""
    try:
        disabled = _disabled_sets()
    except Exception as e:
        log.error(f"Erro ao ler skills desligadas: {e}")
        disabled = (frozenset(), frozenset())
    return [intent for intent in manager.skills
            if is_skill_enabled(intent, disabled) and skill_category(intent) not in exclude_categories]


def classify_intent(text, skip_skills=False, exclude_categories=()):
    """ROTEADOR DE INTENÇÃO: Classifica o comando do usuário em categorias.
    skip_skills=True tira todas as skills; exclude_categories tira só as dessas categorias."""
    exclude_categories = tuple(exclude_categories or ())
    # Cache LRU+TTL: comandos repetidos em sequência servem sem reconsultar o LLM.
    cache_key = ((text or "").strip().lower(), skip_skills, exclude_categories)
    cached = _intent_cache.get(cache_key)
    if cached is not None:
        log.debug(f"⚡ [INTENÇÃO CACHE HIT]: {cached.get('intent')}")
        return dict(cached)  # cópia: chamador nunca muta a entrada cacheada

    active_skills = [] if skip_skills else _offered_skills(exclude_categories)
    valid_intents = ["HARDWARE", "MEMORY_READ", "MEMORY_WRITE", "CHAT"] + active_skills

    options_str = " | ".join([f'"{opt}"' for opt in valid_intents])

    schema = f"""
    {{
        "intent": {options_str},
        "entity": "string (o objeto da ação, ex: 'spotify', 'luz', ou null se não houver)",
        "confidence": float (0.0 a 1.0)
    }}
    """
    active_prompts = [
        manager.skills[intent].PROMPT_TEXT
        for intent in active_skills if hasattr(manager.skills[intent], "PROMPT_TEXT")
    ]
    skills_prompts = "\n    ".join(active_prompts)
    prompt = load_prompt(
        "classify_intent.md",
        options_str=options_str,
        skills_prompts=skills_prompts,
        text=text,
        schema=schema
    )

    try:
        res = query_ollama([{'role': 'user', 'content': prompt}], format='json', temperature=0, timeout=settings.TIMEOUT_API)
        if not res:
            return {"intent": "CHAT", "entity": None, "confidence": 0.0}

        result = json.loads(res)
        if not result.get("intent"): result["intent"] = "CHAT"
        if "confidence" not in result: result["confidence"] = 0.5
        _intent_cache.set(cache_key, dict(result))  # guarda cópia estável
        return result
    except Exception as e:
        log.error(f"Erro no parsing do Classificador: {e}")
        return {"intent": "CHAT", "entity": None, "confidence": 0.0}
