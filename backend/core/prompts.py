import os
import string

from core.logger import log

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

_prompt_cache = {}

def load_prompt(filename, **kwargs):
    """
    Carrega um arquivo de prompt .md e aplica injeção de variáveis via Template se houver kwargs.
    Usa um cache em memória para evitar IO excessivo no disco.
    
    A sintaxe no arquivo .md deve ser $variavel.
    """
    filepath = os.path.join(PROMPTS_DIR, filename)

    if not os.path.exists(filepath):
        log.error(f"Erro: Arquivo de prompt não encontrado: {filepath}")
        return ""

    mtime = os.path.getmtime(filepath)
    cached = _prompt_cache.get(filepath)

    # Recarrega do disco se nunca cacheado ou se o .md foi editado em runtime (mtime mudou)
    if not cached or cached[0] != mtime:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        # Pré-compila o Template UMA vez (evita reparse a cada load com kwargs)
        template = string.Template(content)
        _prompt_cache[filepath] = (mtime, content, template)
    else:
        content, template = cached[1], cached[2]

    if kwargs:
        # safe_substitute ignora variáveis no .md que não foram passadas no kwargs sem crashar
        return template.safe_substitute(**kwargs)

    return content
