import re
import time

import core.state as state
from core.llm import query_ollama
from core.logger import log
from core.prompts import load_prompt

try:
    from services.listen import ear_pause, ear_resume
    from services.speak import speak
except ImportError as e:
    log.critical(f"❌ Erro ao importar sentidos em alerts.py: {e}")

PROCESS_JUDGEMENT_CACHE = {}
JUDGEMENT_TTL = 3600  # 1h — evita leak de memória em sessões longas


def process_system_alert(message, is_proactive=False):
    if is_proactive:
        try:
            # Intercepta alertas de disco — sem processo culpado para matar
            if "Disco" in message and ("CRÍTICO" in message or "pouco espaço" in message):
                clean_msg = message.replace("*", "")
                ear_pause()
                speak(f"Alerta de Armazenamento: {clean_msg}")
                ear_resume()
                return

            culprit_match = re.search(r"(?:Top 5|Maiores consumos|Consumo): (.*?)\s*\(", message)
            culprit_app = culprit_match.group(1).strip() if culprit_match else None

            if culprit_app:
                cached = PROCESS_JUDGEMENT_CACHE.get(culprit_app)
                if cached and time.time() < cached[1]:
                    decision = cached[0]
                else:
                    judge_prompt = load_prompt("judge_process.md", culprit_app=culprit_app)
                    decision = query_ollama([{'role': 'user', 'content': judge_prompt}], temperature=0)
                    if decision:
                        decision = decision.strip().upper()
                        PROCESS_JUDGEMENT_CACHE[culprit_app] = (decision, time.time() + JUDGEMENT_TTL)

                if decision and "SIM" in decision:
                    log.info(f"🔇 [KERNEL]: Silenciando alerta para '{culprit_app}'")
                    return

                state.pending_critical_action = {
                    'type': 'KILL_PROCESS',
                    'target': culprit_app,
                    'timeout': time.time() + 30
                }

                alert_text = f"Alerta de sistema: O processo {culprit_app} está com consumo crítico. Deseja que eu o encerre?"
                ear_pause()
                speak(alert_text)
                ear_resume()
                return

            # Alerta genérico sem culpado identificável
            sys_prompt = load_prompt("system_alert.md")
            alert_text = query_ollama([
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': message}
            ], temperature=0.5)

            if alert_text:
                clean_text = alert_text.replace("*", "").strip()
                ear_pause()
                speak(clean_text)
                ear_resume()

        except Exception as e:
            log.error(f"Erro no alerta: {e}")
