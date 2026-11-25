"""Skill POWER_REPORT — "quanto o PC está gastando de energia?".

Só leitura: watts agora (GPU NVIDIA medida pelo nvidia-smi, CPU e resto
estimados), kWh de hoje e do mês e o custo pela tarifa `POWER_TARIFF_KWH`.
Texto montado em `core.power.summary_text` — sem LLM, nada inventado.
"""
from core.prompts import load_prompt

INTENT = "POWER_REPORT"
PROMPT_TEXT = load_prompt("skills/power_report.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
KEYWORDS = ("energi*", "consum*", "watt*", "kwh", "conta de luz", "gastando")


def execute(entity, command):
    from core import power
    try:
        return power.summary_text()
    except Exception as e:
        return f"Não consegui medir o consumo agora, Senhor: {e}"
