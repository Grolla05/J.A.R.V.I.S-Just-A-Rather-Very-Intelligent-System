# Backend do J.A.R.V.I.S.

O backend é o cérebro do JARVIS: classifica cada mensagem com um LLM local (Ollama), executa skills, conversa com histórico e memória, cuida da voz, das rotinas (briefing, foco, apresentação, alertas) e das integrações. A interface (pacote `frontend/` na raiz) consome tudo por import direto — não existe API HTTP.

Visão ponta a ponta: **[docs/arquitetura.md](../docs/arquitetura.md)**.

## Estrutura

```
backend/
├── main.py        ← entrada: sanity check, Ollama no ar, JarvisApp(...).run()
├── agent.py       ← agente residente (pythonw, bandeja): Win+J, Ctrl+Alt+T, atualização
├── core/          ← infraestrutura: config, banco, LLM, logger, telemetria, integrações
├── services/      ← roteador (brain), classificador, chat, voz, foco, filtros
├── skills/        ← ações plug-and-play (automation, system, productivity, web)
├── prompts/       ← prompts em .md (load_prompt), incluindo prompts/skills/
├── database/      ← SQLite (jarvis_memory.db) em dev
├── logs/          ← jarvis-AAAA-MM-DD.log e crash.log em dev
├── tests/         ← pytest (backend + TUI)
└── docs/          ← documentação por módulo
```

| Pasta | Leia |
|---|---|
| `core/` | [core/README.md](core/README.md) |
| `services/` | [services/README.md](services/README.md) |
| `skills/` | [skills/README.md](skills/README.md) |
| `database/` | [database/README.md](database/README.md) |

### Documentação por módulo (`docs/`)

- [main.py — boot](docs/main_orchestrator.md)
- Core: [config](docs/core/config.md) · [database](docs/core/database.md) · [logger](docs/core/logger.md) · [obsidian](docs/core/obsidian.md) · [skill_loader](docs/core/skill_loader.md) · [SystemInfo](docs/core/SystemInfo.md)
- Services: [brain](docs/services/brain.md) · [listen](docs/services/listen.md) · [speak](docs/services/speak.md)
- Skills: [app_control](docs/skills/automation/app_control.md) · [audio_control](docs/skills/automation/audio_control.md) · [keyboard_control](docs/skills/automation/keyboard_control.md) · [screen_control](docs/skills/automation/screen_control.md) · [work_macros](docs/skills/automation/work_macros.md) · [status_report](docs/skills/system/status_report.md) · [system_clear](docs/skills/system/system_clear.md) · [system_security](docs/skills/system/system_security.md)

## Rodar

```bash
cd backend
pip install -r requirements.txt
python main.py                 # TUI (Chat)
python main.py --copilot       # TUI já no modo voz, sem tela de boot
python -m services.brain       # modo voz standalone, sem interface
python agent.py                # agente residente (normalmente sobe com o Windows)
```

O `.env` fica na raiz do repositório em dev (copie de `env.example`). Instalado, fica em `%APPDATA%\JARVIS` (`JARVIS_DATA_DIR`). Toda variável nova precisa de padrão em `core/config.py`.

## Testes

```bash
python -m pytest tests -q
ruff check . && ruff check ../frontend
```

Os testes não precisam de Ollama, microfone nem hardware: stubs em `tests/_stubs.py`, TUI com `App.run_test()`.
