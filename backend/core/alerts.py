import re

from core import pending
from core.llm import query_ollama
from core.logger import log
from core.prompts import load_prompt
from core.utils import TTLCache

JUDGEMENT_TTL = 3600  # 1h: o veredito do LLM sobre um processo vale por esse tempo
# TTLCache remove as entradas vencidas e limita o tamanho (antes era um dict que só crescia)
PROCESS_JUDGEMENT_CACHE = TTLCache(maxsize=256, ttl=JUDGEMENT_TTL)


def _is_yes(decision):
    """Veredito do LLM: só a PRIMEIRA palavra conta ("SIMPLESMENTE…" não é "SIM")."""
    words = (decision or "").strip().upper().split()
    return bool(words) and words[0].strip(".,!:;\"'*") == "SIM"


def _close_process(name):
    """Confirmado pelo usuário: encerra pelo APP_CONTROL (nome exato, sem nova pergunta)."""
    from core.skill_loader import manager
    app_control = manager.skills.get("APP_CONTROL")
    if app_control is None or not hasattr(app_control, "close_now"):
        return f"Não consigo encerrar {name}: a skill APP_CONTROL não está disponível."
    return app_control.close_now(name)


def _announce(text):
    """Entrega o alerta à interface e, se a voz estiver ligada, fala.
    Import tardio dos sentidos: importar listen/speak abria o mic no boot."""
    from services.listen import ear_pause, ear_resume
    from services.speak import speak
    ear_pause()
    try:
        speak(text)
    finally:
        ear_resume()


def process_system_alert(message, is_proactive=False):
    from services import notify_filter
    verdict, prio, reason = notify_filter.evaluate(message)
    if verdict == notify_filter.DEFER:
        # Não Perturbe / reunião / tela cheia: nada de fala, notificação ou pedido de
        # confirmação. O alerta é resumido quando o silêncio acaba (services/focus.py
        # para o DND manual, notify_filter.poll_auto_quiet para o automático).
        from services.focus import remember_alert
        remember_alert(message)
        log.info(f"🔕 [{reason}] Alerta ({prio}) guardado: {str(message)[:80]}")
        return
    if is_proactive:
        try:
            # Intercepta alertas de disco — sem processo culpado para matar
            if "Disco" in message and ("CRÍTICO" in message or "pouco espaço" in message):
                clean_msg = message.replace("*", "")
                _announce(f"Alerta de Armazenamento: {clean_msg}")
                return

            culprit_match = re.search(r"(?:Top 5|Maiores consumos|Consumo): (.*?)\s*\(", message)
            culprit_app = culprit_match.group(1).strip() if culprit_match else None

            if culprit_app:
                decision = PROCESS_JUDGEMENT_CACHE.get(culprit_app)
                if decision is None:
                    judge_prompt = load_prompt("judge_process.md", culprit_app=culprit_app)
                    decision = query_ollama([{'role': 'user', 'content': judge_prompt}], temperature=0)
                    if decision:
                        decision = decision.strip().upper()
                        PROCESS_JUDGEMENT_CACHE.set(culprit_app, decision)

                if _is_yes(decision):
                    log.info(f"🔇 [KERNEL]: Silenciando alerta para '{culprit_app}'")
                    return

                question = f"Alerta de sistema: O processo {culprit_app} está com consumo crítico. Deseja que eu o encerre?"
                armed = pending.arm("KILL_PROCESS", question, lambda app=culprit_app: _close_process(app),
                                    target=culprit_app)
                if armed is None:
                    # Já há outra confirmação aberta: avisa sem pergunta (não troca a ação dela).
                    _announce(f"Alerta de sistema: O processo {culprit_app} está com consumo crítico.")
                    return
                _announce(question)
                return

            # Alerta genérico sem culpado identificável
            sys_prompt = load_prompt("system_alert.md")
            alert_text = query_ollama([
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': message}
            ], temperature=0.5)

            if alert_text:
                _announce(alert_text.replace("*", "").strip())

        except Exception as e:
            log.error(f"Erro no alerta: {e}")
