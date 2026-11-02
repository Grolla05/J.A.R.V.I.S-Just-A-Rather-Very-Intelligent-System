import time

import core.state as state
from core import log, manager, settings
from core.alerts import process_system_alert
from core.hardware import scan_system_hardware
from core.obsidian import get_vault_context
from services.chat import ask_local_ai, ask_local_ai_stream
from services.intent import classify_intent, is_skill_enabled
from services.memory import extract_fact_to_memory

try:
    from services.listen import ear_pause, ear_resume, listen
    from services.speak import speak
except ImportError as e:
    log.critical(f"❌ Erro ao importar sentidos: {e}")

# Injeta callback padrão (sobrescrito por main.py com ui_aware_alert_callback)
state.sys_monitor.brain_callback = process_system_alert
scan_system_hardware()


def execute_command(command, session_id='default'):
    # 0. Confirmação pendente (ex: fechar app crítico)
    if state.pending_critical_action:
        if time.time() > state.pending_critical_action['timeout']:
            state.pending_critical_action = None
        else:
            affirmation_words = ["sim", "pode", "feche", "encerre", "faça", "ok", "confirmo", "autorizo", "vai"]
            if any(w in command.lower().split() for w in affirmation_words):
                target = state.pending_critical_action['target']
                log.info(f"✅ Autorização recebida para encerrar {target}")
                if "APP_CONTROL" in manager.skills:
                    skill = manager.skills["APP_CONTROL"]
                    res = skill.execute(target, f"fechar {target}")
                    state.pending_critical_action = None
                    return res
            state.pending_critical_action = None

    decision = classify_intent(command)
    intent = decision.get("intent")
    entity = decision.get("entity")
    log.info(f"🧠 [INTENÇÃO DETECTADA]: {intent} (Confiança: {decision.get('confidence')})")

    if intent == "MEMORY_WRITE":
        speak("Processando nova memória...")
        return extract_fact_to_memory(command)

    elif intent in manager.skills and is_skill_enabled(intent):
        skill_module = manager.skills[intent]
        return skill_module.execute(entity, command)

    else:
        vault_file, vault_ctx = get_vault_context(command)
        return ask_local_ai(command, intent_type=intent, entity=entity,
                            vault_context=vault_ctx, vault_filename=vault_file,
                            session_id=session_id)


def execute_command_stream(command, session_id='default', images=None):
    if state.pending_critical_action:
        if time.time() > state.pending_critical_action['timeout']:
            state.pending_critical_action = None
        else:
            affirmation_words = ["sim", "pode", "feche", "encerre", "faça", "ok", "confirmo", "autorizo", "vai"]
            if any(w in command.lower().split() for w in affirmation_words):
                target = state.pending_critical_action['target']
                log.info(f"✅ Autorização recebida para encerrar {target}")
                if "APP_CONTROL" in manager.skills:
                    skill = manager.skills["APP_CONTROL"]
                    res = skill.execute(target, f"fechar {target}")
                    state.pending_critical_action = None
                    yield res
                    return
            state.pending_critical_action = None

    decision = classify_intent(command)
    intent = decision.get("intent")
    entity = decision.get("entity")
    log.info(f"🧠 [INTENÇÃO DETECTADA STREAM]: {intent} (Confiança: {decision.get('confidence')})")

    if intent == "MEMORY_WRITE":
        yield extract_fact_to_memory(command)

    elif intent in manager.skills and is_skill_enabled(intent):
        skill_module = manager.skills[intent]
        yield skill_module.execute(entity, command)

    else:
        vault_file, vault_ctx = get_vault_context(command)
        for chunk in ask_local_ai_stream(command, intent_type=intent, entity=entity,
                                          vault_context=vault_ctx, vault_filename=vault_file,
                                          session_id=session_id, images=images):
            yield chunk


def start_brain():
    """Loop Principal (modo voz standalone, sem GUI)."""
    log.info(f"Conectado à Interface Neural {settings.OLLAMA_MODEL} em {settings.OLLAMA_HOST}")
    speak("Importando preferências virtuais... pronto. À sua disposição, senhor.")
    state.sys_monitor.start_proactive_monitor(interval=30)

    while True:
        try:
            command = listen()
            if command:
                log.info(f"🧠 [BRAIN]: Intenção: '{command}'")
                response_text = execute_command(command)
                if response_text:
                    try:
                        ear_pause()
                        speak(response_text)
                    finally:
                        ear_resume()
        except KeyboardInterrupt:
            log.info("[SISTEMA] Encerrado manualmente.")
            break
        except Exception as e:
            log.critical(f"❌ [ERRO CRÍTICO]: {e}")
            time.sleep(1)


if __name__ == "__main__":
    start_brain()
