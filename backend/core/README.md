# 🤖 J.A.R.V.I.S. - Backend Core Package

O diretório `backend/core/` é o coração da infraestrutura do J.A.R.V.I.S. Implementa o **Facade Pattern**, centralizando o acesso a todas as funcionalidades essenciais através de um único ponto de entrada.

## 📂 Módulos

### `__init__.py` — O Portal (Facade)

Interface pública do pacote. Exporta todos os singletons e utilitários usados pelo resto do sistema.

- **Exports:** `settings`, `log`, `db`, `obsidian`, `mcp_client`, `get_vault_context`, `manager`, `SystemInfo`, `load_prompt`
- **Silenciamento:** Filtra logs verbose de `httpx`, `urllib3`, `asyncio`, `multipart`.

```python
from core import settings, log, db, manager, load_prompt
```

---

### `config.py` — Configurações Globais

Gerencia variáveis de ambiente, caminhos e sanidade do ambiente.

- Criação automática de diretórios (`logs/`, `database/`, `assets/sounds/`)
- `perform_sanity_check()`: valida vars obrigatórias no boot

**Variáveis `.env` obrigatórias:**

| Variável | Exemplo | Descrição |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.1` | Modelo local no Ollama |
| `OLLAMA_HOST` | `http://localhost:11434` | URL do servidor Ollama |
| `OBSIDIAN_HOST` | `http://127.0.0.1:27123` | URL da REST API do Obsidian |
| `OBSIDIAN_API_KEY` | `token...` | Token da API do Obsidian |
| `SPEECH_RATE` | `175` | Velocidade do TTS (inteiro) |
| `MIC_INDEX` | `0` | Índice do microfone |

**Opcionais:** `LOG_LEVEL` (default: `INFO`), `DEBUG_MODE` (default: `False`), `DEFAULT_LANGUAGE` (default: `pt-BR`)

---

### `logger.py` — Sistema de Log

Logger Singleton com cores no terminal e persistência diária em arquivo (`logs/jarvis_YYYY-MM-DD.log`).

- **Níveis:** DEBUG (Ciano), INFO (Verde), WARNING (Amarelo), ERROR/CRITICAL (Vermelho)
- **Uso:** `from core import log` → `log.info("mensagem")`

---

### `database.py` — Persistência SQLite

Gerencia memória de longo prazo e histórico de conversas. Veja [database/README.md](../database/README.md) para schema completo.

- **Singleton:** `db`
- **Métodos principais:** `log_interaction()`, `get_system_specs()`, `save_config()`, `get_config()`, `search_relevant_context()`, `delete_history_from()`, `update_history_message()`

---

### `llm.py` — Wrapper Ollama

Chamadas ao LLM local (Ollama) em modo síncrono e streaming.

- `query_ollama(messages, temperature)` → `str`
- `query_ollama_stream(messages, temperature)` → `Generator[str]`

---

### `state.py` — Estado Global em Runtime

Container de estado compartilhado entre módulos.

- `sys_monitor`: instância de `SystemInfo` ativa
- `pending_critical_action`: ação destrutiva pendente aguardando confirmação do usuário (`dict | None`)

---

### `prompts.py` — Templates de Prompt

Carrega e renderiza arquivos `.md` da pasta `backend/prompts/` com substituição de variáveis.

- `load_prompt(filename, **kwargs)` → `str`
- Templates suportam `{variavel}` via `str.format_map`

---

### `SystemInfo.py` — Telemetria de Hardware

Monitora o estado físico da máquina em tempo real com callbacks proativos.

- **Monitoramento:** CPU, RAM, GPU (GPUtil), Rede, Disco, Bateria
- **Alertas:** dispara `brain_callback` quando limites críticos são atingidos
- `get_realtime_context()` → string para injeção no prompt
- `get_detailed_hardware_context()` → specs completos para queries HARDWARE

---

### `hardware.py` — Varredura de Hardware

Executa varredura via PowerShell (WMI) e persiste specs no SQLite para anti-alucinação da IA.

- `scan_system_hardware()` → salva CPU, GPU, RAM, Placa-mãe no banco
- `run_powershell(command)` → executa comando PS e retorna JSON

---

### `obsidian.py` — Memória de Longo Prazo (Obsidian Vault)

Integração com o vault Obsidian via REST API local e MCP stdio.

- **`ObsidianClient`** (REST): `search()`, `get_file()`, `get_memory()`, `save_memory()`
- **`ObsidianMCPClient`** (MCP): `call(tool_name, **kwargs)` — acesso completo ao vault via `uvx mcp-obsidian`
- **`extract_relevant_section(content, query)`** → extrai a seção mais relevante de um markdown antes de injetar no prompt (keyword-matching por categoria)
- **`get_vault_context(command)`** → `(filename, content)` — dois níveis:
  - **Camada 1:** keywords pessoais → lê `⚙️ Configurações/🧠 Sobre mim.md` diretamente
  - **Camada 2:** busca semântica no vault → arquivo com maior score

---

### `skill_loader.py` — Carregamento Dinâmico de Skills

Varre `backend/skills/` recursivamente e registra módulos que seguem o contrato de interface.

- **Singleton:** `manager`
- Cada skill precisa de: `INTENT` (str), `execute(entity)` (fn), `PROMPT_TEXT` (opcional)
- `manager.skills` → `dict[str, SkillModule]`

---

### Interface (antiga `bridge.py`)

A bridge PyWebView foi removida junto com o frontend React. A interface agora é a TUI em `backend/tui/`, que chama o backend direto:

| Antes (`JarvisAPI`) | Agora |
|---|---|
| `chat_message()` | `services.brain.execute_command_stream(text, session_id, images, mode)` |
| `get_chat_history()`, `delete_history_from()`, `update_session_title()`, `toggle_session_pin()`, `get_recent_sessions()` | `services/sessions.py` |
| `get_skills()`, `toggle_skill()`, `toggle_category()` | `services/skill_settings.py` |
| `transcribe_audio()` | `core.transcription.transcribe_audio_file()` (via `/attach`) |
| `get_telemetry()` / `set_hud_state()` / `send_frontend_alert()` | barra de status, classe `-critical` e `state.announce` na TUI |

---

### `alerts.py` — Sistema de Alertas

Processa alertas de sistema e decide ação (falar, silenciar ou pedir confirmação para matar processo).

- `process_system_alert(message, is_proactive)` → void
- **Cache do Juiz (`PROCESS_JUDGEMENT_CACHE`):** decisão por processo é cacheada em memória para não gastar tokens repetindo a mesma consulta LLM

---

## 🛠️ Tecnologias

- Python 3.10+, SQLite3, Psutil / GPUtil, Colorama, Requests, MCP (stdio), Ollama
