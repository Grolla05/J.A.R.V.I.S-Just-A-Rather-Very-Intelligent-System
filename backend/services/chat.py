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


# Modo da conversa → prompt de regras (voz = modo standalone, sem Markdown).
MODE_PROMPTS = {"voice": "mode_voice.md", "chat": "mode_chat.md", "copilot": "mode_copilot.md"}


def _prompt(filename, **kwargs):
    return load_prompt(filename, **kwargs).strip()


def build_messages(text, intent_type="CHAT", vault_context="", vault_filename="", session_id="default",
                   live_context="", mode="chat"):
    """Mensagens do chat: system (personalidade + modo + HARDWARE/MEMORY_READ),
    telemetria ao vivo, nota do vault, dados reais (live_context), histórico e a pergunta.
    Todo texto de instrução vem de backend/prompts/*.md."""
    sys_instruction = SYSTEM_PROMPT['content'] + "\n\n" + _prompt(MODE_PROMPTS.get(mode, "mode_chat.md"))

    if intent_type == "HARDWARE":
        hardware = state.sys_monitor.get_detailed_hardware_context()
        sys_instruction += "\n" + _prompt("hardware_context.md", hardware=hardware)

    if intent_type == "MEMORY_READ":
        sys_instruction += "\n\n" + _prompt("memory_read.md")

    messages = [
        {'role': 'system', 'content': sys_instruction},
        {'role': 'system', 'content': _prompt("live_data.md", live_data=state.sys_monitor.get_realtime_context())},
    ]

    if vault_context:
        log.info(f"[VAULT PREVIEW — {vault_filename}]: {vault_context[:500]}")
        messages.append({'role': 'system',
                         'content': _prompt("vault_memory.md", note=vault_filename, content=vault_context)})

    if live_context:  # dados reais (agenda…) — services/live_context.py
        messages.append({'role': 'system', 'content': live_context})

    return messages + get_session_history_for_ai(session_id, limit=8) + [{'role': 'user', 'content': text}]


def _temperature(intent_type, live_context):
    return 0.1 if live_context or intent_type in ("HARDWARE", "MEMORY_READ") else 0.7


def ask_local_ai(text, intent_type="CHAT", entity=None, vault_context="", vault_filename="", session_id="default",
                 live_context=""):
    """Modo voz (standalone): resposta inteira, sem Markdown."""
    messages = build_messages(text, intent_type, vault_context, vault_filename, session_id, live_context, mode="voice")
    reply = query_ollama(messages, temperature=_temperature(intent_type, live_context))
    if reply:
        return reply.replace("*", "").replace("#", "").strip()
    return "Erro de processamento neural."


def ask_local_ai_stream(text, intent_type="CHAT", entity=None, vault_context="", vault_filename="", session_id="default",
                        images=None, mode="chat", live_context=""):
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

    messages = build_messages(text, intent_type, vault_context, vault_filename, session_id, live_context,
                              mode="copilot" if mode == "copilot" else "chat")
    for chunk in query_ollama_stream(messages, temperature=_temperature(intent_type, live_context)):
        yield chunk
