import core.state as state
from core.config import settings
from core.database import db
from core.llm import query_ollama, query_ollama_stream
from core.logger import log
from core.prompts import load_prompt

SYSTEM_PROMPT = {
    'role': 'system',
    'content': load_prompt("system_prompt.md")
}


def get_session_history_for_ai(session_id, limit=8):
    """Carrega o histórico recente do SQLite formatado para a IA.
    Busca limit+1 e descarta a última entrada (user) pois é a mensagem
    atual, já logada antes desta chamada, enviada separadamente no prompt."""
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, content FROM history
            WHERE session_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (session_id, limit + 1))
        rows = cursor.fetchall()
        conn.close()

        rows.reverse()
        # Última entrada é a mensagem atual (logada antes desta chamada) — remover
        if rows and rows[-1][0] == 'user':
            rows = rows[:-1]

        messages = []
        for role, content in rows:
            if content:
                messages.append({
                    'role': 'user' if role == 'user' else 'assistant',
                    'content': content
                })
        return messages
    except Exception as e:
        log.error(f"Erro ao obter histórico do banco para a IA: {e}")
        return []


def ask_local_ai(text, intent_type="CHAT", entity=None, vault_context="", vault_filename="", session_id="default"):
    db_history = get_session_history_for_ai(session_id, limit=8)

    sys_instruction = SYSTEM_PROMPT['content'] + "\n\n[MODO ATUAL: VOZ] Aplique REGRAS DE ÁUDIO. Proibido Markdown. Sem asteriscos, cerquilhas ou listas."

    if intent_type == "HARDWARE":
        sys_instruction += f"\n[DADOS DE HARDWARE]:\n{state.sys_monitor.get_detailed_hardware_context()}\nUSE ISSO."

    if intent_type == "MEMORY_READ":
        sys_instruction += (
            "\n\n[INSTRUÇÃO CRÍTICA — MEMÓRIA PESSOAL]: O arquivo Obsidian abaixo contém "
            "informações REAIS e VERIFICADAS sobre o usuário Felipe. Você TEM ACESSO a esses "
            "dados — eles são sua memória. Use-os para responder diretamente e com segurança. "
            "NUNCA diga que não tem acesso a informações pessoais quando um arquivo do vault "
            "for fornecido: esse arquivo É a fonte autoritativa. Extraia os fatos relevantes "
            "e responda como JARVIS teria acesso a todos os dados pessoais do Senhor."
        )

    live_data = state.sys_monitor.get_realtime_context()

    messages = [
        {'role': 'system', 'content': sys_instruction},
        {'role': 'system', 'content': f"LIVE DATA: {live_data}"},
    ]

    if vault_context:
        log.info(f"[VAULT PREVIEW — {vault_filename}]: {vault_context[:500]}")
        messages.append({
            'role': 'system',
            'content': f"[MEMÓRIA PESSOAL — {vault_filename}]:\n{vault_context}"
        })

    messages += db_history + [{'role': 'user', 'content': text}]

    temp = 0.1 if intent_type in ("HARDWARE", "MEMORY_READ") else 0.7
    reply = query_ollama(messages, temperature=temp)

    if reply:
        clean = reply.replace("*", "").replace("#", "").strip()
        return clean
    return "Erro de processamento neural."


def ask_local_ai_stream(text, intent_type="CHAT", entity=None, vault_context="", vault_filename="", session_id="default", images=None):
    if images:
        # Imagem anexada: roteia pro modelo de visão com um contexto mínimo e
        # dedicado. Moondream/LLaVA são modelos pequenos — empilhar a
        # personalidade completa do JARVIS + histórico + telemetria por cima
        # degrada a resposta sobre a imagem em vez de ajudar.
        vision_messages = [
            {'role': 'system', 'content': load_prompt("vision_context.md")},
            {'role': 'user', 'content': text, 'images': images},
        ]
        for chunk in query_ollama_stream(
            vision_messages,
            temperature=0.4,
            timeout=settings.TIMEOUT_VISION,
            model=settings.OLLAMA_VISION_MODEL,
            keep_alive=settings.OLLAMA_VISION_KEEP_ALIVE,
        ):
            yield chunk
        return

    db_history = get_session_history_for_ai(session_id, limit=8)

    sys_instruction = SYSTEM_PROMPT['content'] + "\n\n[MODO ATUAL: CHAT] Aplique REGRAS DE CHAT. Formate a resposta em Markdown. Use **negrito**, `código`, listas e blocos de código quando apropriado."

    if intent_type == "HARDWARE":
        sys_instruction += f"\n[DADOS DE HARDWARE]:\n{state.sys_monitor.get_detailed_hardware_context()}\nUSE ISSO."

    if intent_type == "MEMORY_READ":
        sys_instruction += (
            "\n\n[INSTRUÇÃO CRÍTICA — MEMÓRIA PESSOAL]: O arquivo Obsidian abaixo contém "
            "informações REAIS e VERIFICADAS sobre o usuário Felipe. Você TEM ACESSO a esses "
            "dados — eles são sua memória. Use-os para responder diretamente e com segurança. "
            "NUNCA diga que não tem acesso a informações pessoais quando um arquivo do vault "
            "for fornecido: esse arquivo É a fonte autoritativa. Extraia os fatos relevantes "
            "e responda como JARVIS teria acesso a todos os dados pessoais do Senhor."
        )

    live_data = state.sys_monitor.get_realtime_context()

    messages = [
        {'role': 'system', 'content': sys_instruction},
        {'role': 'system', 'content': f"LIVE DATA: {live_data}"},
    ]

    if vault_context:
        log.info(f"[VAULT PREVIEW — {vault_filename}]: {vault_context[:500]}")
        messages.append({
            'role': 'system',
            'content': f"[MEMÓRIA PESSOAL — {vault_filename}]:\n{vault_context}"
        })

    messages += db_history + [{'role': 'user', 'content': text}]

    temp = 0.1 if intent_type in ("HARDWARE", "MEMORY_READ") else 0.7
    for chunk in query_ollama_stream(messages, temperature=temp):
        yield chunk
