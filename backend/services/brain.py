import time

import core.state as state
from core import log, manager, settings
from core.alerts import process_system_alert
from core.obsidian import get_vault_context
from services.chat import ask_local_ai, ask_local_ai_stream
from services.intent import classify_intent, is_skill_enabled
from services.memory import extract_fact_to_memory

# Modos da interface de texto: CHAT só conversa; COPILOT pode executar skills.
MODE_CHAT = "chat"
MODE_COPILOT = "copilot"

# Callback padrão (a TUI sobrescreve com o seu próprio handler de alertas).
# scan_system_hardware() saiu do import: agora é chamado pelo boot (main.py).
state.sys_monitor.brain_callback = process_system_alert

_AFFIRMATION_WORDS = ["sim", "pode", "feche", "encerre", "faça", "ok", "confirmo", "autorizo", "vai"]


def confirm_pending_action(approved):
    """Resolve a ação crítica pendente (ex: encerrar processo pesado, criar issue).
    Retorna a resposta da skill, ou None se não havia ação válida/aprovada.

    Uma skill pode deixar a ação pronta em `pending['on_confirm']` (callable sem
    argumentos); sem ela, o padrão é encerrar `pending['target']` (APP_CONTROL)."""
    pending = state.pending_critical_action
    state.pending_critical_action = None
    if not pending or time.time() > pending['timeout'] or not approved:
        return None
    on_confirm = pending.get('on_confirm')
    if callable(on_confirm):
        log.info(f"✅ Autorização recebida: {pending.get('type', 'ação')}")
        return on_confirm()
    target = pending['target']
    log.info(f"✅ Autorização recebida para encerrar {target}")
    if "APP_CONTROL" in manager.skills:
        return manager.skills["APP_CONTROL"].execute(target, f"fechar {target}")
    return None


def _check_pending_action(command):
    """Se há ação crítica pendente, o próximo comando é a resposta a ela."""
    if not state.pending_critical_action:
        return None
    approved = any(w in command.lower().split() for w in _AFFIRMATION_WORDS)
    return confirm_pending_action(approved)


def execute_command(command, session_id='default'):
    """Pipeline do modo voz: sempre com skills liberadas (como o Copilot)."""
    res = _check_pending_action(command)
    if res:
        return res

    decision = classify_intent(command)
    intent = decision.get("intent")
    entity = decision.get("entity")
    log.info(f"🧠 [INTENÇÃO DETECTADA]: {intent} (Confiança: {decision.get('confidence')})")

    if intent == "MEMORY_WRITE":
        from services.speak import speak
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


def execute_command_stream(command, session_id='default', images=None, mode=MODE_CHAT, on_route=None):
    """Pipeline de texto (TUI). mode=chat nunca executa skill; mode=copilot sim.
    on_route(intent) é chamado quando a mensagem vira uma skill (badge na TUI)."""
    if mode == MODE_COPILOT:
        res = _check_pending_action(command)
        if res:
            yield res
            return

    decision = classify_intent(command, skip_skills=(mode != MODE_COPILOT))
    intent = decision.get("intent")
    entity = decision.get("entity")
    log.info(f"🧠 [INTENÇÃO DETECTADA STREAM/{mode}]: {intent} (Confiança: {decision.get('confidence')})")

    if intent == "MEMORY_WRITE":
        yield extract_fact_to_memory(command)

    elif mode == MODE_COPILOT and intent in manager.skills and is_skill_enabled(intent):
        if on_route:
            on_route(intent)
        skill_module = manager.skills[intent]
        yield skill_module.execute(entity, command)

    else:
        vault_file, vault_ctx = get_vault_context(command)
        for chunk in ask_local_ai_stream(command, intent_type=intent, entity=entity,
                                          vault_context=vault_ctx, vault_filename=vault_file,
                                          session_id=session_id, images=images, mode=mode):
            yield chunk


def start_brain():
    """Loop Principal (modo voz standalone, sem interface)."""
    from core.hardware import scan_system_hardware
    from services.listen import ear_pause, ear_resume, listen
    from services.speak import speak

    state.voice_enabled = True
    scan_system_hardware()
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
