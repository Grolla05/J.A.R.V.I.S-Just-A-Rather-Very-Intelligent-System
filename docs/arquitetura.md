# Arquitetura do J.A.R.V.I.S — ponta a ponta

Este documento explica como o J.A.R.V.I.S funciona do boot à resposta, módulo a módulo. Para regras de código (o que é proibido, onde cada coisa deve morar), veja o [`CLAUDE.md`](../CLAUDE.md).

## 1. Visão geral

O J.A.R.V.I.S é um assistente pessoal **local** para Windows, 100% Python:

- **Interface:** uma TUI ([Textual](https://textual.textualize.io)) que roda no terminal (pacote `frontend/`). Não há browser, WebView, Node.js, REST nem IPC: a TUI importa o backend e chama funções Python.
- **Cérebro:** o backend (`backend/`) classifica cada mensagem com um LLM local (Ollama), decide se ela vira uma **skill** (ação) ou uma **resposta de chat**, e devolve texto em stream.
- **Memória:** SQLite local (histórico, sessões, preferências) + vault do Obsidian (memória de longo prazo, RAG).
- **Agente residente:** um processo separado, sem janela (`backend/agent.py`), que segura os atalhos globais (`Win+J`, `Ctrl+Alt+T`), fica na bandeja e cuida da atualização automática.

```
                ┌──────────────────────── processo da TUI (python main.py) ───────────────────────┐
 teclado ─────▶ │ frontend/app.py (JarvisApp)                                                       │
 microfone ───▶ │   ├─ modo CHAT  : PromptInput ─┐                                                  │
                │   └─ modo COPILOT: VoiceBar ◀── services/listen.py (wake word + Google STT)       │
                │                                ▼                                                  │
                │                 services/brain.py  execute_command_stream(texto, sessão, modo)    │
                │                   ├─ ação crítica pendente? → confirm_pending_action              │
                │                   ├─ services/intent.py  classify_intent (Ollama, JSON)           │
                │                   ├─ MEMORY_WRITE → services/memory.py → Obsidian                 │
                │                   ├─ skill permitida → skills/<cat>/<skill>.py execute(entity, cmd)│
                │                   └─ resto → services/chat.py (histórico + vault + live_context)  │
                │                                ▼ stream de texto                                  │
                │   MessageView (Markdown a cada 50 ms) · services/speak.py (TTS, se voz ligada)    │
                │   core/SystemInfo (telemetria 3 s) → alertas → services/notify_filter.py          │
                └───────────────────────────────────────────────────────────────────────────────────┘
                     ▲  tui.json + eventos nomeados (core/presence.py)
                ┌────┴──────── processo do agente (pythonw agent.py, bandeja) ────────┐
                │ Win+J → abre/foca a TUI · Ctrl+Alt+T → traduz seleção · atualização │
                └─────────────────────────────────────────────────────────────────────┘
```

## 2. Ciclo de vida

### 2.1 Boot (`backend/main.py`)

1. `settings.perform_sanity_check()` — cria pastas (`logs/`, `database/`, `uploads/`…) e valida o `.env`.
2. `faulthandler` grava crash nativo (PortAudio, CUDA) em `logs/crash.log`.
3. `core/wt_profile.ensure_profile()` — perfil "JARVIS" do Windows Terminal (logo na aba).
4. `core/ollama_server.ensure_ollama_running()` — se o Ollama local estiver fora, sobe `ollama serve` desacoplado e espera até `OLLAMA_START_TIMEOUT`. Nunca derruba o boot.
5. Põe a raiz do repositório no `sys.path` e cria `JarvisApp(boot_fn=core.boot.run_boot, …)`.
   - `--copilot` (vindo do agente): abre direto no Copilot, sem tela de boot.
   - `--update-preview X` (dev): mostra a tela de atualização sem rede.
6. No fim, `os._exit(0)` mata threads presas em I/O (microfone, monitor).

### 2.2 Tela de boot (`frontend/screens/boot.py` + `core/boot.py`)

`run_boot(report)` executa as etapas e informa cada uma como `[  OK  ]`, `[ WARN ]` ou `[ FAIL ]`:

| Etapa | O que verifica |
|---|---|
| `core.config` | `.env` e caminhos |
| `core.database` | abre o SQLite e cria/migra tabelas |
| `core.skill_loader` | quantas skills foram descobertas |
| `core.llm / Ollama` | servidor no ar; o *warm-up* do modelo roda numa thread daemon |
| `core.hardware` | scan WMI (PowerShell) em thread daemon → tabela `hardware` |
| `core.obsidian` | Local REST API do Obsidian respondendo |
| microfone | enumerado só via `core/health.check_microphone()` (lock + cache) |

Nenhuma etapa trava a TUI. Depois do boot:

- `core/updater.check_available()` → se houver Release mais novo, `UpdateScreen`.
- `JarvisApp._maybe_daily_briefing()` → no 1º boot do dia (pref `briefing_auto`), mostra e fala o briefing.
- Começam os timers: telemetria (`TELEMETRY_INTERVAL` = 3 s) e saúde (`HEALTH_INTERVAL` = 15 s).
- `core/presence.register_tui()` grava `tui.json` ({pid, hwnd}) para o agente.

### 2.3 Encerramento

`Esc` na conversa (sem nada em andamento) ou `/quit` abre a `ShutdownScreen` (efeito CRT). `Esc` de novo sai na hora. `unregister_tui()` apaga o `tui.json`.

## 3. Fluxo de uma mensagem

### 3.1 Modo Chat (texto)

1. `PromptInput` recebe o texto. Se começar com `/`, `frontend/commands.parse` transforma em comando e `JarvisApp.run_command` executa (veja §6). `//texto` envia literalmente `/texto`.
2. `JarvisApp.send` cria as bolhas e dispara o worker de thread `_stream`.
3. `db.log_interaction` grava a mensagem do usuário (com anexo, se houver `/attach`).
4. `services/brain.execute_command_stream(texto, session_id, images, mode="chat", on_route=…)`:
   - Se existe `state.pending_critical_action`, a mensagem é a resposta (sim/não) a ela.
   - `classify_intent(texto, exclude_categories=("automation", "system"))` pede ao Ollama um JSON `{intent, entity, confidence}`. Resultado fica em cache (TTL 30 s, 64 entradas).
   - `MEMORY_WRITE` → `services/memory.extract_fact_to_memory` → nota nova no Obsidian.
   - Skill ligada e permitida no Chat (categorias `productivity` e `web`) → `on_route(intent)` (selo `[INTENT]` na bolha) → `skill.execute(entity, texto)`.
   - Qualquer outra coisa (`CHAT`, `HARDWARE`, `MEMORY_READ`) → `services/chat.ask_local_ai_stream` com histórico da sessão, contexto do vault (`get_vault_context`) e dados reais (`services/live_context.build`).
5. A TUI re-renderiza o Markdown a cada 50 ms (`STREAM_FLUSH_S`) e grava a resposta no fim.

### 3.2 Modo Copilot (voz)

1. Entrar no Copilot (`Shift+Tab`/`Ctrl+T`/`Win+J`) liga a voz (`state.voice_enabled = True`); o input dá lugar à `VoiceBar` e à orb pixel-art.
2. `services/listen` abre o microfone sob demanda (`get_ear()`), espera a *wake word* (`WAKE_WORDS`) e transcreve com o Google STT. Depois do nome, há uma **janela de atenção** (pref `attention_window`, padrão 60 s) em que não é preciso repetir "Jarvis".
3. `_voice_loop` mostra a fala na sessão atual e chama o **mesmo** `_run_turn` do Chat com `mode="copilot"`: aqui todas as skills executam.
4. A orb muda de estado: ouvindo → pensando → respondendo (8 fps, só nesses dois últimos).
5. `services/speak` fala a resposta (edge-tts; fallback pyttsx3), com o ouvido pausado para não se escutar.

### 3.3 Ações críticas

Skills que mexem em algo sério (encerrar processo pesado, criar issue no GitHub) não executam direto: gravam `state.pending_critical_action` com `on_confirm` e um prazo. A TUI mostra a `ConfirmScreen` (topo vermelho, `s`/`n`, expira em 30 s = não); na voz, a próxima frase com "sim/pode/ok…" confirma. Quem resolve é `brain.confirm_pending_action`.

## 4. Módulos

### 4.1 Interface — `frontend/`

| Módulo | Papel |
|---|---|
| `app.py` | `JarvisApp`: modos, atalhos, worker de stream, voz, alertas, telemetria, briefing automático, atualização |
| `widgets.py` | `MessageView` (Markdown), `PromptInput` (arrastar arquivo = `/attach`), `StatusLine`, `JarvisOrb`, `CopilotHero`, `VoiceBar`, `ConfirmScreen` (30 s), `PixelSprite` |
| `commands.py` | Parser puro dos `/comandos`, aliases e entradas/busca fuzzy da paleta `Ctrl+K` |
| `orb.py` | Quadros 16×16 da orb e conversão para meio-bloco (lógica pura) |
| `sprites.py` | Sprites 16-bit e efeitos de texto: `block_bar` (▰▱), `sparkline`, `bar_chart`, CRT, scanline |
| `jarvis.tcss` | Tema. Todas as cores como variáveis `$j-*` |
| `screens/base.py` | `JarvisScreen`: topo + corpo + linha de status; `Esc` volta |
| `screens/boot.py` | Tela de boot estilo BIOS |
| `screens/status.py` | `/status`: CPU, RAM, GPU e rede com histórico, top processos, saúde |
| `screens/skills.py` | `/skills`: cartuchos por categoria; Enter liga/desliga, `c` liga/desliga a categoria |
| `screens/log.py` | `/log`: buffer do logger com filtros, busca e a timeline do último turno com skill |
| `screens/vault.py` | `/vault`: árvore do Obsidian, busca, prévia e "usar no chat" |
| `screens/settings.py` | `/config`: VOZ, MICROFONE, ROTINAS, INTEGRAÇÕES, SISTEMA, MODELO, SOBRE |
| `screens/integrations_panel.py` | Cards de INTEGRAÇÕES (Google Agenda, Spotify, GitHub…) |
| `screens/save_slots.py` | `Ctrl+O`: sessões como save slots (carregar, fixar, apagar, buscar) |
| `screens/palette.py` | `Ctrl+K`: paleta de comandos, modos, foco e skills |
| `screens/update.py` | "ATUALIZAÇÃO DISPONÍVEL!!" — qualquer tecla instala |
| `screens/shutdown.py` | Saída com efeito CRT |
| `screens/house_party.py` | Easter egg ("house party" no Chat) |

### 4.2 Roteamento e conversa — `backend/services/`

| Módulo | Papel |
|---|---|
| `brain.py` | Roteador. `execute_command_stream` (TUI, por modo) e `execute_command` (voz standalone); `confirm_pending_action` |
| `intent.py` | `classify_intent` (Ollama em JSON, cache TTL), `is_skill_enabled`, `CHAT_BLOCKED_CATEGORIES` |
| `chat.py` | Monta o prompt (system + live data + vault + live_context + histórico de 8 mensagens) e chama o Ollama |
| `live_context.py` | Detecta perguntas sobre a agenda e injeta os eventos reais com "não invente" |
| `memory.py` | Extrai um fato (chave/valor) e grava no Obsidian |
| `sessions.py` | Sessões e histórico do chat (SQLite); `to_local()` converte UTC |
| `skill_settings.py` | Liga/desliga skills e categorias (chaves `disabled_skills`/`disabled_categories`) |
| `user_prefs.py` | Preferências do `/config` (voz, mic, rotinas…) com padrão e opções válidas |
| `listen.py` | Ouvido lazy: wake word, janela de atenção, `ear_pause`/`ear_resume`, nível do mic |
| `speak.py` | TTS (edge-tts → pyttsx3), `speech_lock`, gírias, no-op com a voz desligada |
| `focus.py` | `FocusManager`: Pomodoro e Não Perturbe (silencia toasts e guarda alertas no backlog) |
| `presentation.py` | Modo Apresentação: manual (`/silent`) ou automático (slides/PDF em tela cheia) |
| `notify_filter.py` | Decide se um alerta fala agora, espera ou some: prioridade × contexto |
| `integrations.py` | Registro dos cards de INTEGRAÇÕES (`status`/`connect`/`disconnect`) |

### 4.3 Infraestrutura — `backend/core/`

| Módulo | Papel |
|---|---|
| `config.py` | `Settings`: lê o `.env`, define caminhos (`DIR_*`, `DB_PATH`) e padrões |
| `logger.py` | `log`: arquivo diário em `logs/`, console fora da TUI, `RingBufferHandler` para o `/log` |
| `database.py` | `db`: SQLite com 4 tabelas (`config`, `history`, `sessions`, `hardware`) e migrações |
| `state.py` | Estado global: `sys_monitor`, `pending_critical_action`, `voice_enabled`, DND, `announce` |
| `llm.py` | `query_ollama` (JSON/temperatura) e `query_ollama_stream`; `warm_up_ollama` |
| `ollama_server.py` | Sobe `ollama serve` no boot quando o servidor local está fora |
| `prompts.py` | `load_prompt("arquivo.md", var=…)` com cache e `string.Template` |
| `skill_loader.py` | `manager`: descobre skills em `skills/<categoria>/` |
| `SystemInfo.py` | Telemetria (psutil/GPUtil), limites críticos e monitor proativo |
| `alerts.py` | `process_system_alert`: passa pelo filtro, fala, notifica ou pede confirmação |
| `health.py` | Saúde de Ollama, Obsidian, microfone e SQLite |
| `hardware.py` | Scan WMI via PowerShell → tabela `hardware` |
| `boot.py` | Etapas da tela de boot |
| `obsidian.py` | REST do Obsidian + cliente MCP (`uvx mcp-obsidian`); RAG em 2 camadas |
| `briefing.py` | Briefing diário em seções fixas (veja §5.1) |
| `news.py` | Manchetes do briefing: uma por fonte, a mais relevante (RSS ou busca) |
| `weather.py` | Clima (Open-Meteo + geolocalização por IP) e saudação por horário |
| `google_calendar.py` | Google Agenda só leitura (OAuth Desktop + PKCE) |
| `traffic.py` | Locais fixos (`/rota`), rota OSRM ou TomTom, aviso de saída |
| `github_client.py` | PRs, issues, último commit, CI e criação de issue (PyGithub) |
| `spotify.py` | OAuth PKCE, Web API e controle do player |
| `oauth.py` | OAuth Desktop genérico: PKCE + callback no loopback |
| `secrets_store.py` | Tokens no Cofre de Credenciais do Windows (`keyring`); fallback JSON |
| `web.py` | Busca DuckDuckGo + leitura das páginas + resumo no Ollama |
| `clipboard.py` | Monitor de clipboard e ações (explicar, traduzir, resumir) |
| `selection.py` | Copia a seleção de qualquer app e lê/escreve o clipboard (Win32) |
| `transcription.py` | Whisper local (faster-whisper) para áudio anexado |
| `uploads.py` | Valida e grava anexos (imagem/áudio) |
| `notifications.py` | Liga/desliga os toasts do Windows (HKCU) |
| `window_utils.py` | Win32: monitores, janela em foco, tela cheia, detecção de apresentação |
| `hotkey.py` | Atalho global (`RegisterHotKey`) do agente |
| `presence.py` | Ponte TUI ⇄ agente: `tui.json` + eventos nomeados |
| `autostart.py` | Valor `JARVIS` em `HKCU\…\Run` (`--logon`) e início do agente |
| `launcher.py` | Abre a TUI numa janela nova (Windows Terminal ou console) |
| `updater.py` | Release do GitHub mais novo → tela → setup silencioso com SHA-256 |
| `wt_profile.py` | Fragmento do perfil "JARVIS" do Windows Terminal |
| `utils.py` | `TTLCache` |

### 4.4 Skills — `backend/skills/`

Cada skill expõe `INTENT`, `PROMPT_TEXT`, `CATEGORY` (herdada da pasta) e `execute(entity, command)`. O `SkillManager` as descobre no boot; o `PROMPT_TEXT` entra no prompt do classificador.

| Categoria | Skill (`INTENT`) | O que faz | Chat? |
|---|---|---|---|
| automation | `APP_CONTROL` | Abre, foca e fecha apps | não |
| automation | `AUDIO_CONTROL` | Volume e mudo (pycaw) | não |
| automation | `CLIPBOARD` | Explica/traduz/resume o clipboard | não |
| automation | `KEYBOARD_CONTROL` | Teclado fantasma (pyautogui) | não |
| automation | `SCREEN_CONTROL` | Brilho, gamma ("retina") e janelas | não |
| automation | `SPOTIFY_CONTROL` | Tocar, pausar, buscar no Spotify | não |
| automation | `WORK_MACRO` | Cenas de trabalho/estudo (apps, janelas, notificações) | não |
| system | `SYSTEM_REPORT` | Relatório de status da máquina | não |
| system | `SYSTEM_CLEANUP` | Lixeira, temporários, desinstalar app | não |
| system | `SYSTEM_SECURITY` | Bloquear, suspender, desligar, modo sentinela | não |
| productivity | `CALENDAR` | Compromissos do Google Agenda | sim |
| productivity | `DAILY_BRIEFING` | Briefing do dia | sim |
| productivity | `FOCUS_MODE` | Pomodoro e Não Perturbe | sim |
| productivity | `GITHUB` | PRs, issues, commit, CI, criar issue (com confirmação) | sim |
| productivity | `PRESENTATION_MODE` | Liga/desliga o Modo Apresentação | sim |
| productivity | `TRAFFIC` | Tempo entre locais cadastrados | sim |
| web | `WEB_SEARCH` | Pesquisa e resume com fontes | sim |

## 5. Rotinas

### 5.1 Briefing diário

`core/briefing.collect()` busca cada fonte isolada (uma falha não derruba as outras): saudação, clima, computador (CPU, RAM, GPU, internet medida em 1 s, bateria em notebook), GitHub, agenda, trânsito (dias úteis) e, se a pref `briefing_news` estiver ligada, manchetes. `to_markdown()` monta seções fixas, um tema por bloco; o Ollama só escreve uma frase de fecho. Roda sozinho no 1º boot do dia (chave `briefing_last_date`), por `/briefing` ou pela skill `DAILY_BRIEFING`, e é sempre falado.

**Manchetes (`core/news.py`):** fontes configuráveis em `/config` → SISTEMA (chave `news_sources`). Uma notícia por fonte, em paralelo:

1. Fontes com RSS oficial (G1, BBC, NYT, WSJ, CNN Brasil) leem o feed; fontes sem RSS usam a busca e descartam títulos de página inicial; "DOI" busca no Crossref.
2. Entram as 15 mais novas das últimas 48 h (item de feed sem data fica de fora).
3. Cada título ganha pontos por palavra-chave: morte (3), guerra/ataque/desastre (3), mercado (2), queda/disparada/recorde (2), política (1).
4. Vence a maior nota; empate fica com a mais nova.

### 5.2 Foco, Não Perturbe e Apresentação

- **Pomodoro** (`/focus`, skill `FOCUS_MODE`): foco 25 → pausa 5, pausa longa 15 a cada 4 focos (`POMODORO_*`). O foco liga o Não Perturbe.
- **Não Perturbe** (`/dnd`): silencia os toasts do Windows e manda alertas não-críticos para `state.dnd_backlog`; ao desligar, sai um resumo.
- **Modo Apresentação** (`/silent`, skill, ou automático com PowerPoint/Canva/Google Slides/PDF em tela cheia): mic fechado, TTS mudo e selo `[SILENT]`.

### 5.3 Alertas de hardware

`SystemInfo` vigia CPU > 90 %, RAM > 90 %, GPU > 85 °C, disco < 20 GB (aviso) / < 10 GB (crítico) e bateria < 15 %. Cada alerta passa por `core/alerts.process_system_alert` → `services/notify_filter`:

- crítico (disco crítico, bateria crítica, GPU superaquecendo) sempre fala;
- com Não Perturbe, reunião na agenda, tela cheia ou apresentação, o resto vai para o backlog.

Os sinais `CRITICAL_START`/`CRITICAL_END` pintam a TUI de vermelho (classe `-critical`).

### 5.4 Trânsito e aviso de saída

`/rota <local> <endereço>` geocodifica no Nominatim e guarda o local. A skill `TRAFFIC` entende origem e destino na frase. Sem `TOMTOM_API_KEY`, usa o OSRM público (tempo médio); com a chave, trânsito ao vivo. A pref `commute_alert` avisa a hora de sair.

## 6. Comandos e atalhos da TUI

| Comando | Faz |
|---|---|
| `/menu` (`Ctrl+K`) | Paleta de comandos; `/help`, `/h` e `/?` também abrem |
| `/new` (`Ctrl+N`), `/sessions` (`Ctrl+O`), `/rename`, `/pin` | Sessões |
| `/regen` (`Ctrl+R`), `/edit` (`↑` com input vazio) | Regenerar / editar a última |
| `/attach <caminho>`, `/detach` | Imagem → modelo de visão; áudio → Whisper (arrastar arquivo também anexa) |
| `/mode [chat\|copilot]` (`Shift+Tab`), `/voice` (`Ctrl+T`) | Modo e voz |
| `/skills`, `/status`, `/log`, `/vault`, `/config` | Telas cheias |
| `/web`, `/gh`, `/briefing`, `/rota`, `/clip` | Ferramentas |
| `/focus`, `/dnd`, `/silent` | Foco, Não Perturbe e Apresentação |
| `/clear` (`Ctrl+L`), `/quit` (`Esc`) | Limpar tela, sair |

Atalhos globais (agente): `Win+J` abre/foca a TUI no Copilot (em foco, volta ao Chat); `Ctrl+Alt+T` traduz o texto selecionado em qualquer app (toast + clipboard).

## 7. Dados

| Onde | O quê |
|---|---|
| `database/jarvis_memory.db` | Tabelas `config` (prefs, skills desligadas, fontes, locais, data do briefing), `history` (mensagens + anexo + modo), `sessions` (título, fixada), `hardware` (specs WMI). Veja [`backend/database/README.md`](../backend/database/README.md) |
| `logs/` | `jarvis-AAAA-MM-DD.log` e `crash.log` |
| `uploads/` | Anexos do `/attach` |
| Cofre do Windows (serviço "JARVIS") | Refresh tokens do Google e do Spotify |
| Vault do Obsidian | `⚙️ Configurações/🧠 Sobre mim.md` (perfil) e `🚀 Projetos/J.A.R.V.I.S/Memória/{chave}.md` (memórias novas; nunca sobrescreve) |

Em dev tudo fica em `backend/`. Instalado, `JARVIS_DATA_DIR=%APPDATA%\JARVIS` concentra `.env`, banco, logs e uploads.

## 8. Agente residente e instalação

- **Agente (`backend/agent.py`)**: sobe no logon (`HKCU\…\Run`, `--logon`), segura os atalhos globais, oferece a bandeja ("Abrir J.A.R.V.I.S", "Iniciar com o Windows", "Sair do agente") e conversa com a TUI só por `core/presence.py`. Carrega um pacote `core` vazio para não iniciar banco, MCP e skills.
- **Atualização (`core/updater.py`)**: a TUI e o agente comparam o último Release do GitHub com o `VERSION`. Com versão nova, a TUI mostra a tela de atualização; qualquer tecla pede ao agente baixar o `JARVIS-Setup.exe`, conferir o SHA-256 e instalar em silêncio. Dev (sem `JARVIS_DATA_DIR`) nunca atualiza.
- **Instalador (`installer/`)**: `build_runtime.ps1` monta Python 3.11 + libs; `jarvis.iss` (Inno Setup 6) exige o Ollama, deixa escolher o modelo e faz `ollama pull`. O workflow `release.yml` publica um Release a cada push na `main`.

## 9. Testes

`backend/tests/` cobre backend e TUI (`App.run_test()` + Pilot, com `stream_fn` e voz falsos, sem Ollama, microfone ou hardware).

```bash
cd backend
python -m pytest tests -q
ruff check . && ruff check ../frontend
```
