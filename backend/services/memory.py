import json

from core.llm import query_ollama
from core.logger import log
from core.obsidian import obsidian
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
                ok = obsidian.save_memory(clean_key, val.strip())
                if ok:
                    return f"Memorizado no vault: {clean_key} = {val}."
    except Exception as e:
        log.error(f"Erro ao extrair memória: {e}")
    return "Não consegui extrair o fato com clareza."
