"""Checagens de boot com progresso para a tela de boot da TUI.

`run_boot(report)` roda as etapas em sequência e chama
`report(etapa, status, detalhe)` para cada uma — status ∈ wait | ok | warn | fail.
No fim manda `report(DONE, "ok", "")`. Nenhuma etapa trava o boot: o warm-up do
Ollama e o scan de hardware seguem em threads daemon (podem levar dezenas de s).
"""
import threading

from .config import settings
from .logger import log

DONE = "__done__"


def _check_config():
    return "ok", f".env carregado · modelo {settings.OLLAMA_MODEL}"


def _check_database():
    from .database import db  # noqa: F401  (import cria/migra as tabelas)
    return "ok", f"{settings.DB_PATH.name} · 4 tabelas"


def _check_skills():
    from .skill_loader import manager
    skills = getattr(manager, "skills", {}) or {}
    cats = {getattr(m, "CATEGORY", "?") for m in skills.values()}
    if not skills:
        return "warn", "nenhuma skill carregada"
    return "ok", f"{len(skills)} skills · {len(cats)} categorias"


def _check_ollama():
    from .health import check_ollama
    from .llm import warm_up_ollama
    status, detail = check_ollama()
    if status != "ok":
        return status, detail
    threading.Thread(target=warm_up_ollama, daemon=True).start()
    return "ok", f"{settings.OLLAMA_MODEL} aquecendo em segundo plano"


def _check_hardware():
    from .hardware import scan_system_hardware
    threading.Thread(target=scan_system_hardware, daemon=True).start()
    return "ok", "varredura WMI em segundo plano"


def _check_obsidian():
    from .health import check_obsidian
    return check_obsidian()


def _check_microphone():
    from .health import check_microphone
    return check_microphone(refresh=True)


MIC_STEP = "services.listen"

STEPS = (
    ("core.config", _check_config),
    ("core.database", _check_database),
    ("core.skill_loader", _check_skills),
    ("core.llm / Ollama", _check_ollama),
    ("core.hardware", _check_hardware),
    ("core.obsidian", _check_obsidian),
    (MIC_STEP, _check_microphone),
)


def run_boot(report, steps=STEPS):
    for name, check in steps:
        report(name, "wait", "")
        try:
            status, detail = check()
        except Exception as e:
            log.warning(f"Boot: etapa '{name}' falhou: {e}")
            status, detail = "fail", str(e)[:60]
        report(name, status, detail)
    report(DONE, "ok", "")
