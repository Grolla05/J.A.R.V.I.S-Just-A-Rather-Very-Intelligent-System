import json

from core.llm import query_ollama
from core.logger import log
from core.obsidian import MEMORY_KEPT, MEMORY_SAVED, obsidian
from core.prompts import load_prompt


def extract_fact_to_memory(text):
    prompt = load_prompt("extract_fact.md", text=text)
    try:
        res_str = query_ollama([{'role': 'user', 'content': prompt}], format='json', temperature=0)
        if res_str:
            data = json.loads(res_str)
            key = data.get("key")
            val = data.get("value")
            if key and val:
                clean_key = key.strip().lower().replace(" ", "_")
                val = val.strip()
                result = obsidian.save_memory(clean_key, val)
                if result == MEMORY_SAVED:
                    return f"Memorizado no vault: {clean_key} = {val}."
                if result == MEMORY_KEPT:
                    return _kept_reply(clean_key, val)
                return "Não consegui gravar no vault, Senhor. O Obsidian está acessível?"
    except Exception as e:
        log.error(f"Erro ao extrair memória: {e}")
    return "Não consegui extrair o fato com clareza."


def _kept_reply(key, new_value):
    """Nota já existia: o vault não foi alterado — diz isso em vez de "Memorizado"."""
    current = obsidian.get_memory(key)
    if current is not None and current.strip().lower() == new_value.lower():
        return f"Já estava memorizado no vault: {key} = {current}."
    shown = f" ({current})" if current else ""
    return (f"Já existe uma nota para '{key}' no vault{shown}; mantive a versão do vault "
            f"e descartei '{new_value}'. Edite a nota no Obsidian para atualizar.")
