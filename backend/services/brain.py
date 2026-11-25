import time

import core.state as state
from core import log, manager, pending, settings
from core.alerts import process_system_alert
from core.obsidian import asks_vault, get_vault_context
from services import live_context
from services.chat import ask_local_ai, ask_local_ai_stream
from services.intent import CHAT_ALLOWED_CATEGORIES, classify_intent, is_skill_enabled, skill_allowed_in_chat
from services.memory import extract_fact_to_memory

# Modos da interface de texto: CHAT roda só skills de consulta/produtividade
# (sem automation/system); COPILOT executa todas.
MODE_CHAT = "chat"
MODE_COPILOT = "copilot"

# Callback padrão (a TUI sobrescreve com o seu próprio handler de alertas).
# scan_system_hardware() saiu do import: agora é chamado pelo boot (main.py).
state.sys_monitor.brain_callback = process_system_alert

REPLACED_REPLY = "Essa confirmação foi substituída por outra; nada foi feito, Senhor."


def confirm_pending_action(approved, explicit_decline=True, pending_id=None):
    """Resolve a ação crítica pendente (ex: encerrar processo pesado, criar issue).
    Retorna a resposta da skill, ou None se não havia ação válida/aprovada.

    Uma skill pode deixar a ação pronta em `pending['on_confirm']` (callable sem
    argumentos); sem ela, o padrão é encerrar `pending['target']` (APP_CONTROL.close_now).
    `pending['on_decline']` (opcional) roda quando o usuário recusa dentro do prazo.
    `pending_id` (o ConfirmScreen passa o da pergunta que mostrou): se a pendência foi
    trocada por outra, nada é executado (core/pending.py)."""
    action, status = pending.take(pending_id)
    if status == pending.REPLACED:
        return REPLACED_REPLY if (approved or explicit_decline) else None
    if status != pending.OK:
        return None
    if not approved:
        # Recusa explícita dentro do prazo (não vale para o tempo esgotado): a skill
        # pode reagir — ex.: o vigia de rede passa a tratar o processo como conhecido.
        # `explicit_decline=False` (voz: a frase seguinte não foi um "não") só descarta.
        on_decline = action.get('on_decline')
        return on_decline() if explicit_decline and callable(on_decline) else None
    on_confirm = action.get('on_confirm')
    if callable(on_confirm):
        log.info(f"✅ Autorização recebida: {action.get('type', 'ação')}")
        return on_confirm()
    target = action.get('target')
    log.info(f"✅ Autorização recebida para encerrar {target}")
    app_control = manager.skills.get("APP_CONTROL")
    if target and app_control is not None and hasattr(app_control, "close_now"):
        # O usuário já confirmou: encerra direto, sem nova pergunta nem LLM.
        return app_control.close_now(target)
    return None


def _check_pending_action(command, owner=pending.LOCAL):
    """Se há ação crítica pendente **deste dono**, o próximo comando é a resposta a ela.
    Só uma frase de confirmação aprova (pending.parse_reply); a negação vence;
    qualquer outra frase vai para `on_other` (se a pendência tiver) ou descarta a
    pendência e segue como comando normal. Pendência de outro dono fica intacta."""
    current = pending.active()
    if not current or (current.get("owner") or pending.LOCAL) != (owner or pending.LOCAL):
        return None
    reply = pending.parse_reply(command, current.get("target"))
    on_other = current.get("on_other")
    if callable(on_other) and reply != pending.YES and not (reply == pending.NO and pending.is_pure_denial(command)):
        # Pedido de ajuste ("deixa mais formal"): tira esta pendência e deixa quem a armou refazer.
        _action, status = pending.take(current.get("id"))
        return on_other(command) if status == pending.OK else None
    return confirm_pending_action(reply == pending.YES, explicit_decline=reply == pending.NO,
                                  pending_id=current.get("id"))


def _join_reply(result):
    """Resposta de skill como texto: `str` passa direto; iterável (stream) é juntado."""
    if result is None or isinstance(result, str):
        return result
    return "".join(chunk for chunk in result if chunk)


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
        return _join_reply(skill_module.execute(entity, command))

    else:
        vault_file, vault_ctx = get_vault_context(command)
        return ask_local_ai(command, intent_type=intent, entity=entity,
                            vault_context=vault_ctx, vault_filename=vault_file,
                            session_id=session_id, live_context=live_context.build(command),
                            vault_missing=not vault_ctx and asks_vault(command))


def _skill_allowed(intent, mode):
    if intent not in manager.skills or not is_skill_enabled(intent):
        return False
    return mode == MODE_COPILOT or skill_allowed_in_chat(intent)


def execute_command_stream(command, session_id='default', images=None, mode=MODE_CHAT, on_route=None,
                           force_chat=False, owner=pending.LOCAL):
    """Pipeline de texto (TUI). mode=chat só roda skills fora de automation/system;
    mode=copilot roda todas. on_route(intent) é chamado quando a mensagem vira
    uma skill (badge na TUI). force_chat=True (trecho de código/erro a explicar)
    vai direto ao LLM: sem classificador, sem vault e sem responder a ação pendente
    — o conteúdo de um trecho (ou de um arquivo anexado) não pode virar skill nem
    um "ok" de confirmação."""
    if force_chat:
        log.info(f"🧠 [CHAT DIRETO/{mode}]: {len(command)} caracteres, sem classificador.")
        yield from ask_local_ai_stream(command, intent_type="CHAT", session_id=session_id, mode=mode,
                                       images=images)
        return

    res = _check_pending_action(command, owner)
    if res:
        yield res
        return

    allowed = None if mode == MODE_COPILOT else CHAT_ALLOWED_CATEGORIES
    decision = classify_intent(command, allowed_categories=allowed)
    intent = decision.get("intent")
    entity = decision.get("entity")
    log.info(f"🧠 [INTENÇÃO DETECTADA STREAM/{mode}]: {intent} (Confiança: {decision.get('confidence')})")

    if intent == "MEMORY_WRITE":
        yield extract_fact_to_memory(command)

    elif _skill_allowed(intent, mode):
        if on_route:
            on_route(intent)
        skill_module = manager.skills[intent]
        with pending.owner_scope(owner):   # confirmação armada pela skill pertence a quem pediu
            result = skill_module.execute(entity, command)
        if result is None or isinstance(result, str):
            yield result
        else:  # skill que responde em stream (ex.: SCREEN_READ) devolve um iterável de pedaços
            yield from result

    else:
        vault_file, vault_ctx = get_vault_context(command)
        for chunk in ask_local_ai_stream(command, intent_type=intent, entity=entity,
                                          vault_context=vault_ctx, vault_filename=vault_file,
                                          session_id=session_id, images=images, mode=mode,
                                          live_context=live_context.build(command),
                                          vault_missing=not vault_ctx and asks_vault(command)):
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
