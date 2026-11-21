import json
import re
import time
import unicodedata
from functools import lru_cache

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

# Mensagem só com estas palavras (sem o nome do JARVIS) é conversa trivial: vai
# direto para CHAT, sem ida ao classificador. "bom dia" fica de fora de propósito
# (sozinho pede o briefing, ver skills/daily_briefing). Máx. TRIVIAL_MAX_WORDS.
TRIVIAL_WORDS = frozenset((
    "oi", "ola", "opa", "eai", "e", "ai", "salve", "fala", "hey", "hello", "hi",
    "boa", "tarde", "noite", "tudo", "bem", "bom", "joia", "beleza", "blz",
    "obrigado", "obrigada", "obg", "brigado", "valeu", "vlw", "thanks", "thank", "you",
    "ok", "okay", "certo", "show", "perfeito", "entendi", "legal", "otimo", "massa",
    "tchau", "ate", "mais", "logo", "falou", "flw", "muito", "mto", "sim", "nao",
))
TRIVIAL_MAX_WORDS = 6

# Ollama sem OLLAMA_NUM_CTX usa a janela padrão dele; acima deste uso, o começo
# do prompt (as instruções) corre risco de ser cortado em silêncio.
OLLAMA_DEFAULT_CTX = 4096
CTX_WARN_RATIO = 0.7
CHARS_PER_TOKEN = 3.5
CTX_WARN_EVERY_S = 3600
_last_ctx_warning = 0.0


def normalize(text):
    """Minúsculas, sem acento e sem pontuação, com espaços simples."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def is_trivial(text):
    """Saudação/agradecimento/confirmação curta, sem nada que peça ação."""
    wake = {normalize(w) for w in settings.WAKE_WORDS}
    words = [w for w in normalize(text).split() if w not in wake]
    return 0 < len(words) <= TRIVIAL_MAX_WORDS and all(w in TRIVIAL_WORDS for w in words)


@lru_cache(maxsize=1024)
def _keyword_regex(keyword):
    """`abr*` casa prefixo de palavra; sem `*`, só a palavra/frase inteira."""
    kw = normalize(keyword.rstrip("*"))
    tail = "" if keyword.endswith("*") else r"\b"
    return re.compile(rf"\b{re.escape(kw)}{tail}")


def _matches_keywords(module, norm_text):
    """True/False se a skill declara KEYWORDS; None se não declara (sempre candidata)."""
    keywords = getattr(module, "KEYWORDS", None)
    if not keywords or not isinstance(keywords, (tuple, list, set, frozenset)):
        return None
    return any(_keyword_regex(k).search(norm_text) for k in keywords if isinstance(k, str) and k.strip("* "))


def prefilter_skills(intents, text):
    """Só as skills cujas KEYWORDS aparecem no texto (+ as sem KEYWORDS).
    Nenhuma casou → todas (o classificador decide como antes)."""
    norm = normalize(text)
    verdict = {i: _matches_keywords(manager.skills[i], norm) for i in intents}
    if not any(v is True for v in verdict.values()):
        return list(intents)
    return [i for i in intents if verdict[i] is not False]


def _warn_if_context_tight(prompt, n_skills):
    global _last_ctx_warning
    num_ctx = settings.OLLAMA_NUM_CTX or OLLAMA_DEFAULT_CTX
    tokens = len(prompt) / CHARS_PER_TOKEN
    if tokens <= num_ctx * CTX_WARN_RATIO:
        return
    now = time.monotonic()
    if _last_ctx_warning and now - _last_ctx_warning < CTX_WARN_EVERY_S:
        return
    _last_ctx_warning = now
    log.warning(f"Prompt do classificador com ~{int(tokens)} tokens ({n_skills} skills), "
                f"acima de {int(CTX_WARN_RATIO * 100)}% do contexto ({num_ctx}). "
                "Aumente OLLAMA_NUM_CTX ou desligue skills em /skills.")


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
    if is_trivial(text):
        log.debug("⚡ [INTENÇÃO TRIVIAL]: CHAT sem classificador")
        return {"intent": "CHAT", "entity": None, "confidence": 1.0}

    cache_key = ((text or "").strip().lower(), skip_skills, exclude_categories)
    cached = _intent_cache.get(cache_key)
    if cached is not None:
        log.debug(f"⚡ [INTENÇÃO CACHE HIT]: {cached.get('intent')}")
        return dict(cached)  # cópia: chamador nunca muta a entrada cacheada

    active_skills = [] if skip_skills else prefilter_skills(_offered_skills(exclude_categories), text)
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
    _warn_if_context_tight(prompt, len(active_skills))

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
