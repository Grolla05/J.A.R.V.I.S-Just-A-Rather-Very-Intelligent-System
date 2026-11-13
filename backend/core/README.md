# `backend/core/` — infraestrutura

Singletons e serviços de baixo nível usados pelo resto do JARVIS. O `__init__.py` expõe os principais:

```python
from core import settings, log, db, obsidian, mcp_client, get_vault_context, manager, SystemInfo, load_prompt
import core.state as state   # estado global (não instancie SystemInfo de novo)
```

Importar `core` abre o banco, carrega as skills e prepara o cliente MCP. Por isso o agente residente (`agent.py`) registra um pacote `core` vazio e importa só os módulos leves (`config`, `logger`, `hotkey`, `presence`, `autostart`, `launcher`, `window_utils`, `updater`, `selection`, `wt_profile`).

## Fundação

| Módulo | Papel | API principal |
|---|---|---|
| `config.py` | Lê o `.env` e define caminhos e padrões. Todo caminho gravável sai de `settings.DIR_*`/`DB_PATH` | `settings`, `perform_sanity_check()` |
| `logger.py` | Arquivo diário em `logs/`, console colorido fora da TUI; com a TUI, WARNING+ vira notificação. `RingBufferHandler` alimenta o `/log` | `log.info/warning/error/critical`, `log.use_tui()` |
| `database.py` | SQLite com `config`, `history`, `sessions`, `hardware` e migrações por `PRAGMA table_info` | `db.log_interaction`, `get_config/save_config`, `update_hardware_spec` |
| `state.py` | Estado de runtime: `sys_monitor`, `pending_critical_action`, `voice_enabled`, `dnd_active`/`dnd_backlog`, `auto_quiet`, `presentation_active`, `announce` | `import core.state as state` |
| `prompts.py` | Carrega `backend/prompts/*.md` com cache e `string.Template` (`$variavel`) | `load_prompt("x.md", var=...)` |
| `skill_loader.py` | Descobre skills em `skills/<categoria>/` e herda `CATEGORY` da pasta | `manager.skills` |
| `utils.py` | Cache LRU com validade | `TTLCache` |

## LLM e boot

| Módulo | Papel |
|---|---|
| `llm.py` | Cliente oficial do Ollama: `query_ollama(messages, format='json', temperature=0)`, `query_ollama_stream(messages)`, `warm_up_ollama()`. Aplica `OLLAMA_NUM_CTX`/`NUM_GPU`/`KEEP_ALIVE` |
| `ollama_server.py` | `ensure_ollama_running()`: sobe `ollama serve` se o servidor local estiver fora |
| `boot.py` | Etapas da tela de boot (`run_boot(report)`); warm-up e scan de hardware em threads daemon |
| `health.py` | Saúde de Ollama, Obsidian, microfone (único lugar que enumera o PortAudio) e SQLite |
| `hardware.py` | Scan WMI via PowerShell → tabela `hardware` (evita o LLM inventar specs) |

## Telemetria e alertas

| Módulo | Papel |
|---|---|
| `SystemInfo.py` | CPU, RAM, GPU (GPUtil), disco, rede, bateria, processos; limites (`DEFAULT_THRESHOLDS`: CPU/RAM 90 %, GPU 85 °C, disco 20/10 GB, bateria 15 %) e monitor proativo |
| `alerts.py` | `process_system_alert`: passa pelo `services/notify_filter`, fala/notifica, guarda no backlog ou pede confirmação para matar processo (`PROCESS_JUDGEMENT_CACHE`) |
| `notifications.py` | Liga/desliga os toasts do Windows (HKCU) |
| `window_utils.py` | Win32: monitores, janela em foco, tela cheia, detecção de apresentação |

## Memória

| Módulo | Papel |
|---|---|
| `obsidian.py` | `ObsidianClient` (REST) + `ObsidianMCPClient` (`uvx mcp-obsidian`). `get_vault_context(texto)`: camada 1 = palavras de perfil → `⚙️ Configurações/🧠 Sobre mim.md`; camada 2 = busca no vault → nota de maior score. `save_memory` nunca sobrescreve |
| `transcription.py` | Whisper local (faster-whisper) para áudio anexado |
| `uploads.py` | Valida (MIME, tamanho) e grava anexos em `DIR_UPLOADS` |

## Rotinas e integrações

| Módulo | Papel |
|---|---|
| `briefing.py` | Briefing diário: coleta isolada por fonte, seções fixas, frase de fecho do LLM |
| `news.py` | Manchetes: uma por fonte, a mais relevante (RSS oficial ou busca; Crossref para DOI) |
| `weather.py` | Clima (Open-Meteo, local por IP guardado no Obsidian) e saudação |
| `google_calendar.py` | Google Agenda só leitura: briefing, skill `CALENDAR`, `is_busy()` para o filtro |
| `traffic.py` | Locais fixos (`/rota`), rota OSRM (grátis) ou TomTom (ao vivo), aviso de saída |
| `github_client.py` | PRs, issues, último commit, CI, `create_issue` (quem chama confirma antes) |
| `spotify.py` | OAuth PKCE, Web API (busca, playlists, dispositivos) e player |
| `oauth.py` | OAuth Desktop genérico: PKCE + callback no loopback |
| `secrets_store.py` | Tokens no Cofre de Credenciais do Windows (`keyring`); fallback JSON |
| `web.py` | DuckDuckGo → leitura das páginas em paralelo → resumo no Ollama |
| `clipboard.py` | Monitor de clipboard e ações (explicar, traduzir, resumir) |
| `selection.py` | Copia a seleção de qualquer app e lê/escreve o clipboard (Win32) — atalho de tradução |

## Agente residente e instalação

| Módulo | Papel |
|---|---|
| `hotkey.py` | Atalho global (`RegisterHotKey`) numa thread com laço de mensagens próprio |
| `presence.py` | Ponte TUI ⇄ agente: `tui.json` ({pid, hwnd}) + eventos nomeados (`SUMMON`, `TO_CHAT`, `INSTALL_UPDATE`) |
| `autostart.py` | Valor `JARVIS` em `HKCU\…\Run` (com `--logon`); detecta e sobe o agente |
| `launcher.py` | Abre a TUI numa janela nova (Windows Terminal ou console) |
| `updater.py` | `check_available()` (Release mais novo, cache 6 h) e `install_latest()` (baixa, confere SHA-256, setup silencioso) |
| `wt_profile.py` | Fragmento do perfil "JARVIS" do Windows Terminal (logo na aba) |

## Regras

- Nada de `print()` nem `sys.stdout`: use `log` ou `state.announce`.
- Ollama só por `core.llm`; prompts só em `.md` via `load_prompt`; `.env` só via `settings`.
- SQL sempre com `conn.close()` no `finally`; UPSERT com `ON CONFLICT`.
- Funções de integração nunca levantam para cima: falha vira log + `None`/texto.
