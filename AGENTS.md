# J.A.R.V.I.S — Instruções para o Codex Project

## O que é este projeto

O **J.A.R.V.I.S.** é um assistente virtual 100% autônomo inspirado no JARVIS do Iron Man. É um **app de terminal (TUI) para Windows**, 100% Python: a interface é feita em [Textual](https://textual.textualize.io) e roda no próprio terminal, sem browser, sem WebView e sem Node.js. A TUI consome o backend (o cérebro cognitivo) por chamadas Python diretas — não existe IPC, REST nem HTTP.

**Repositório:** `github.com/Jarvis-Project-2026/J.A.R.V.I.S`
**Dev:** Felipe Grolla Freitas

---

## Workflow obrigatório de funcionamento

1 -> A partir do prompt gere os testes para verificação da feature antes mesmo de começar a desenvolver, todos os testes unitários tem que ser criados dentro da pasta tests na raiz da frente do projeto ou seja dentro de backend ou frontend, caso a pasta não exista crie ela no respectivo lugar.
2 -> Com os testes escritos explore as opções e caminhos nos quais podem ser seguidos para o desenvolvimento
3 -> Escreva o plano de ação para implementar a feature
4 -> Desenvolva o plano proposto, dividindo a atividade do plano em task's
5 -> Após o desenvolvimento execute os testes escritos no passo 1, para validar oque foi gerado, não é necessário rodar a suite inteira de testes e sim somente os testes relacionado a feature implementada, se não passar em algum teste propostos para feature, identifique oque deu problema e conserte e rode o teste novamente
6 -> Após ter ocorrido tudo corretamente por favor crie, edite caso já exista, o arquivo CHANGES.md na raiz do projeto, no qual este por sua vez deve documentar tudo nos mínimos detalhes do que foi feito
7 -> Após ter ter documentado tudo no CHANGES.md prepare para gerar o commit, baseado nas alterações documentadas no CHANGES.md, ou seja deve ser feito baseado neste arquivo o commit mensage, mas espere a validação e comando do usuário
8 -> Com a validação do usuário siga o processo de commit -> push (sync changes) -> Pull Request. Não é necessário abrir uma branch nova para cada feature, apenas utilize a branch Grolla para realizar este processo.
9 -> Após o commit feito por favor limpe o arquivo CHANGES.md, ou seja apague, o conteúdo dele.

---

## Boas práticas

Sempre que for responder ou realizar qualquer prompt é obrigatório que utilize a skill caveman no desenvolvimento da task
também na hora de fazer/abrir o PR e commit, ccoloque sempre a tag de Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>.

---

## Estrutura do Repositório

```
J.A.R.V.I.S/
├── frontend/                ← TUI (Textual), pacote Python `frontend` — visual do canvas "JARVIS TUI"
│   ├── app.py               ← JarvisApp: modos chat/copilot, bindings, stream, voz, alertas
│   ├── widgets.py           ← MessageView, PromptInput, JarvisOrb, CopilotHero, VoiceBar, ConfirmScreen (30 s)
│   ├── orb.py               ← Orb pixel-art 16×16 do Copilot (quadros + meio-bloco, lógica pura)
│   ├── sprites.py           ← Sprites 16-bit + efeitos (block_bar ▰▱, sparkline, bar_chart, CRT, scanline) — lógica pura; pintados pelo PixelSprite
│   ├── screens/             ← Telas cheias (JarvisScreen: topo + corpo + linha de status; Esc volta): /status, /skills, /log, /vault, /config (com cards de INTEGRAÇÕES em `integrations_panel.py`), save slots (SessionPicker, Ctrl+O), paleta Ctrl+K (CommandPalette); e BootScreen, UpdateScreen (atualização disponível), ShutdownScreen (CRT), HousePartyScreen
│   ├── commands.py          ← Parser puro dos /comandos + entradas da paleta Ctrl+K
│   ├── jarvis.tcss          ← Tema (cores como variáveis $j-*)
│   └── pyproject.toml       ← Herda o ruff do backend
│
├── backend/                 ← Python (cérebro cognitivo)
│   ├── main.py              ← Boot: sanity check, ensure_ollama_running, raiz no sys.path, JarvisApp(boot_fn=run_boot).run() (--copilot abre no modo voz)
│   ├── agent.py             ← Agente residente (pythonw, bandeja): atalho global Win+J abre/foca a TUI; sobe com o Windows
│   ├── core/                ← Infraestrutura
│   │   ├── state.py         ← Estado global (sys_monitor, pending_critical_action, voice_enabled, announce)
│   │   ├── llm.py           ← Cliente Ollama oficial (query_ollama / stream)
│   │   ├── hardware.py      ← scan_system_hardware() via PowerShell WMI
│   │   ├── alerts.py        ← process_system_alert() + PROCESS_JUDGEMENT_CACHE (com DND ligado guarda no backlog)
│   │   ├── health.py        ← Saúde de Ollama/Obsidian/mic/SQLite (boot + linha de status)
│   │   ├── notifications.py ← Toasts do Windows on/off (winreg HKCU)
│   │   ├── hotkey.py        ← Atalho global (RegisterHotKey) do agente
│   │   ├── presence.py      ← Ponte TUI⇄agente: tui.json + eventos nomeados (SUMMON/TO_CHAT)
│   │   ├── autostart.py     ← Valor JARVIS em HKCU Run (com --logon) + detecção/início do agente
│   │   ├── updater.py       ← Auto-update: Release do GitHub mais novo → tela ATUALIZAÇÃO DISPONÍVEL → tecla → setup silencioso (SHA-256 conferido)
│   │   ├── launcher.py      ← Abre a TUI numa janela nova (wt ou console)
│   │   ├── prompts.py       ← load_prompt() com cache e string.Template
│   │   ├── uploads.py       ← load_local_file() + save_base64_upload() (/attach)
│   │   ├── transcription.py ← Whisper local (faster-whisper)
│   │   ├── config.py        ← Settings Singleton (.env, paths)
│   │   ├── database.py      ← DatabaseManager SQLite (4 tabelas)
│   │   ├── logger.py        ← JarvisLogger (console fora da TUI, arquivo sempre)
│   │   ├── obsidian.py      ← RAG sobre vault Obsidian via MCP
│   │   ├── oauth.py         ← OAuth Desktop genérico: PKCE + callback no loopback (Google Agenda, Spotify)
│   │   ├── secrets_store.py ← Cofre de Credenciais do Windows (keyring) p/ tokens OAuth (Google e Spotify); fallback JSON
│   │   ├── google_calendar.py ← Google Agenda (REST, só leitura): briefing, skill CALENDAR, is_busy()
│   │   ├── traffic.py       ← Trânsito entre locais fixos (/rota <local> <endereço>): Nominatim + OSRM (grátis) ou TomTom (ao vivo)
│   │   ├── news.py          ← Manchetes do briefing (/config → SISTEMA): 1 por fonte, a mais relevante (RSS oficial ou busca; Crossref p/ DOI)
│   │   ├── briefing.py      ← Briefing diário em seções fixas (Clima, Computador, GitHub, Agenda, Trânsito, Manchetes); LLM só no fecho
│   │   ├── weather.py       ← Clima (Open-Meteo + local por IP) e saudação por horário
│   │   ├── github_client.py ← PyGithub: PRs, issues, commit, CI, create_issue (confirmação fica com quem chama)
│   │   ├── spotify.py       ← Spotify: OAuth PKCE, Web API e player
│   │   ├── web.py           ← Pesquisa DuckDuckGo + leitura das páginas + resumo no Ollama
│   │   ├── clipboard.py     ← Monitor de clipboard e ações (/clip, skill CLIPBOARD)
│   │   ├── window_utils.py  ← Win32: monitores, janela em foco, tela cheia, detecção de apresentação
│   │   ├── ollama_server.py ← Sobe `ollama serve` no boot se o Ollama local estiver fora
│   │   ├── boot.py          ← Etapas da tela de boot (run_boot)
│   │   ├── wt_profile.py    ← Fragmento do perfil JARVIS do Windows Terminal (logo na aba)
│   │   ├── utils.py         ← TTLCache
│   │   ├── selection.py     ← Copia a seleção (Ctrl+C) e lê/escreve o clipboard via Win32 (agente)
│   │   ├── skill_loader.py  ← Auto-discovery de skills (plug-and-play)
│   │   └── SystemInfo.py    ← psutil — monitoramento de hardware
│   ├── services/            ← Serviços cognitivos
│   │   ├── brain.py         ← Roteador: execute_command (voz) / execute_command_stream (TUI, por modo)
│   │   ├── intent.py        ← classify_intent() + is_skill_enabled()
│   │   ├── chat.py          ← ask_local_ai() + ask_local_ai_stream()
│   │   ├── sessions.py      ← Sessões/histórico do chat (SQLite)
│   │   ├── skill_settings.py← Liga/desliga skills e categorias (/skills)
│   │   ├── user_prefs.py    ← Preferências do /config (chaves pref_* na tabela config)
│   │   ├── focus.py         ← Pomodoro + Não Perturbe (FocusManager: /focus, /dnd, skill FOCUS_MODE)
│   │   ├── presentation.py  ← Modo Apresentação: /silent, skill PRESENTATION_MODE ou slides em tela cheia (PowerPoint, PDF, Canva, Google Slides no navegador) / PowerPoint aberto (pref) → mic fechado, TTS mudo, selo [SILENT]
│   │   ├── notify_filter.py ← Filtro de interrupções: prioridade × contexto (DND, reunião, tela cheia)
│   │   ├── integrations.py  ← Registro dos cards de /config → INTEGRAÇÕES (estado, conectar, desconectar)
│   │   ├── live_context.py  ← Dados reais no prompt do Chat (agenda do Google) quando a pergunta pede — evita alucinação
│   │   ├── memory.py        ← extract_fact_to_memory() → Obsidian
│   │   ├── listen.py        ← Ear lazy (STT + Wake Word "Jarvis") — mic só abre com a voz ligada
│   │   └── speak.py         ← TTS (edge-tts → fallback pyttsx3), no-op com a voz desligada
│   ├── skills/
│   │   ├── automation/      ← app_control, audio_control, clipboard_assistant, keyboard_control,
│   │   │                       screen_control, spotify_control, work_macros  (só Copilot/voz)
│   │   ├── system/          ← status_report, system_clear, system_security       (só Copilot/voz)
│   │   ├── productivity/    ← calendar_agenda, daily_briefing, focus_mode, github_control,
│   │   │                       presentation_mode, traffic_commute               (Chat e Copilot)
│   │   └── web/             ← web_search                                          (Chat e Copilot)
│   ├── prompts/             ← Arquivos .md de prompt (system_prompt, classify_intent, mode_chat, mode_copilot, briefing...; skills/ p/ PROMPT_TEXT)
│   ├── tests/               ← pytest (backend + TUI)
│   └── docs/                ← Documentação por módulo
│
├── installer/               ← Instalador JARVIS-Setup.exe (Inno Setup 6)
│   ├── build_runtime.ps1    ← dist/runtime (Python 3.11 NuGet + libs) e dist/app (código sem testes/dados)
│   ├── jarvis.iss           ← Setup: páginas "Ollama necessário" (espera instalar) e "Modelo de IA" (dropdown + ollama pull)
│   ├── jarvis.cmd           ← Launcher instalado (Windows Terminal, JARVIS_DATA_DIR=%APPDATA%\JARVIS)
│   └── test_setup.ps1       ← Instala em silêncio (/SKIPOLLAMA), confere e desinstala
├── docs/                    ← arquitetura.md (ponta a ponta, módulo a módulo) e integracoes-oauth.md
├── .github/workflows/       ← main.yml (CI: ruff + compileall em PR/push na main e DEV) e release.yml (push na main → testes → setup → Release vX.Y.Z só com JARVIS-Setup.exe)
├── env.example              ← Modelo do .env com todas as variáveis comentadas
└── VERSION                  ← major.minor (patch sobe sozinho pela última tag)
```

### Modo instalado (`JARVIS_DATA_DIR`)

- O `jarvis.cmd` define `JARVIS_DATA_DIR=%APPDATA%\JARVIS`; com ela, `core/config.py` põe `.env`, logs, banco, uploads, áudio do TTS e token do Spotify lá (a pasta do programa pode ser só leitura). Sem ela (dev) tudo fica em `backend/` e o `.env` na raiz
- Todo caminho gravável **deve** sair de `settings.DIR_*` / `settings.DB_PATH` — nunca de `Path(__file__)`
- Nova lib no `requirements.txt` entra no setup automaticamente; se for importante, inclua no smoke de `build_runtime.ps1`
- Integrações de conta (Google Agenda, Spotify) usam chaves **pessoais**: cada usuário cria o próprio app e preenche `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`SPOTIFY_CLIENT_ID` no `.env` (guia em `docs/integracoes-oauth.md`). Nunca versionar chaves. Tokens dos usuários só no Cofre do Windows (`core/secrets_store.py`); testes usam cofre em memória
- Variável nova do `.env` precisa de **default** no `Settings` (o setup copia o `env.example`, mas `.env` antigos não ganham a chave)

---

## Backend — Regras e Convenções

### Logging

- **Proibido `print()`** em qualquer arquivo. Sempre: `from core import log` → `log.info()` / `log.warning()` / `log.critical()`
- **Nunca escrever direto em `sys.stdout`** — corrompe a tela da TUI. Para mostrar algo ao usuário use `state.announce(texto)` (ou `speak()`, que já passa por ele)
- Com a TUI ativa, `log.use_tui()` desliga o console; WARNING+ vira notificação na tela e tudo segue no arquivo `backend/logs/`
- `log.debug()` para loops, streaming e tracking de variáveis
- `log.critical()` apenas antes de `sys.exit(1)`

### Ollama (LLM)

- **Proibido `requests.post`** para chamar o Ollama diretamente nos serviços principais
- Sempre usar: `from core.llm import query_ollama, query_ollama_stream`
- `query_ollama(messages, format='json', temperature=0)` para classificação/extração
- `query_ollama_stream(messages, temperature=0.7)` para o chat da TUI

### Prompts

- **Proibido hardcodar prompts como strings Python** dentro de arquivos `.py`
- Sempre criar um arquivo `.md` em `backend/prompts/` e usar: `from core.prompts import load_prompt`
- Variáveis no `.md`: sintaxe `$variavel` (string.Template)
- `load_prompt("arquivo.md", variavel=valor)` → retorna a string com substituição

### Threading

- Toda I/O pesada disparada pela TUI **deve** rodar em worker de thread (`@work(thread=True)`) e voltar para a tela com `self.call_from_thread(...)` — nunca mexer em widget fora da thread da UI
- Toda nova `threading.Thread` **deve** ter `daemon=True` (garante que `os._exit(0)` no fim do `main.py` a destrua)
- A `speech_lock` do `speak.py` **nunca deve ser removida**

### Sentidos (voz) — imports sem efeito colateral

- Voz é **opcional** e começa desligada (`state.voice_enabled = False`); liga com `/voice` ou `Ctrl+T`
- **Proibido** abrir microfone, pyttsx3 ou pygame no import de módulo. `services.listen` usa `get_ear()` lazy e `speak.py` inicializa os motores na 1ª fala
- Em outros módulos, importe `listen`/`speak` **dentro da função** que usa (import tardio), como em `core/alerts.py`

### Banco de Dados — SQLite (`database.py`)

- Toda operação SQL **deve** terminar com `conn.close()` em bloco `finally`
- Novas colunas: sempre adicionar fallback `PRAGMA table_info` + `ALTER TABLE` para bancos antigos
- Arquivo gerado em `backend/database/jarvis_memory.db` com 4 tabelas: `config`, `history`, `sessions`, `hardware`
- UPSERT via `ON CONFLICT(key) DO UPDATE SET` — nunca checar existência manualmente antes de inserir
- Acesso: `from core.database import db` → `db.log_interaction()`, `db.get_config()`, `db.save_config()`, `db.update_hardware_spec()`
- Sessões/histórico do chat: `from services import sessions` (não escrever SQL de sessão na TUI)

### Banco de Dados — Obsidian (Memória de Longo Prazo)

- O Obsidian funciona como cofre semântico de **longo prazo** — não substitui o SQLite, complementa
- Memórias efêmeras da IA ficam em `🚀 Projetos/J.A.R.V.I.S/Memória/{key}.md` (`MEMORY_NOTE_PATH`; o path sempre passa por `urllib.parse.quote`)
- **Nunca sobrescreve** notas existentes — preserva edições manuais do usuário no vault
- RAG em 2 camadas via `core/obsidian.py`:
  - **Camada 1**: palavras de perfil pessoal (`_PROFILE_KEYWORDS`) → puxa `Sobre mim.md` inteiro
  - **Camada 2**: busca semântica via MCP `obsidian_simple_search` → retorna arquivo de maior score
- Acesso: `from core.obsidian import obsidian, get_vault_context`
  - `obsidian.save_memory(key, value)` → salva nota no vault
  - `obsidian.get_memory(key)` → lê primeira linha útil da nota
  - `get_vault_context(text)` → retorna `(filename, context_str)` para injetar no prompt
- Paths com acentos **devem** passar por `urllib.parse.quote(..., encoding="utf-8")` — sem isso: 404

### Estado Global

- `sys_monitor`, `pending_critical_action`, `voice_enabled` e `announce` vivem em `core/state.py`
- Acesso: `import core.state as state` → `state.sys_monitor` / `state.pending_critical_action`
- **Nunca** instanciar `SystemInfo()` novamente em outros módulos

### Skills — Contrato Obrigatório

Toda skill **deve** expor:

```python
INTENT = "NOME_UNICO"      # Primary key no dicionário global
PROMPT_TEXT = "..."        # Alimenta o system prompt do LLM
CATEGORY = "automation"    # Herdado automaticamente da pasta-mãe

def execute(entity: str, command: str) -> str:
    # entity: objeto da ação ("spotify", "50", etc.)
    # command: frase original do usuário
    return "resposta do Jarvis"
```

> ⚠️ `execute()` recebe **2 argumentos**: `entity` e `command`. Skills antigas com 1 argumento quebrarão o routing.
> No modo **Copilot** (e no modo voz) todas as skills executam. No modo **Chat** só as de categoria fora de `CHAT_BLOCKED_CATEGORIES` (`automation` e `system`, em `services/intent.py`): o classificador roda com `exclude_categories=` e o `brain` confere `skill_allowed_in_chat()`. Productivity e web (agenda, trânsito, GitHub, busca, briefing, foco, apresentação) rodam nos dois modos.
> Dado externo que o Chat precisa responder (ex.: agenda) entra como contexto via `services/live_context.py` (detecção por palavra-chave + bloco de sistema em `prompts/*_context.md` com "não invente") — nunca deixe o LLM responder sobre dado pessoal sem a fonte no prompt.

### Configurações

- **Nunca** usar `os.getenv("CHAVE")` diretamente em `brain.py`, na TUI ou em skills
- Toda variável do `.env` deve ser declarada em `core/config.py` como atributo da classe `Settings`

---

## TUI — Regras e Convenções

### Modos (`JarvisApp.mode`)

| Modo | Atalho | O que faz |
|------|--------|-----------|
| `chat` | `Shift+Tab` | Conversa **por texto** com o LLM em Markdown. Skills **nunca** executam. Voz desligada |
| `copilot` | `Shift+Tab` / `Ctrl+T` | Agente **só por voz**: o input dá lugar à `VoiceBar` + orb; mesmo pipeline com skills liberadas + confirmação de ação crítica (`ConfirmScreen`) |

O modo vai para `execute_command_stream(..., mode=)` e escolhe o prompt `mode_chat.md` / `mode_copilot.md`. Entrar no Copilot liga a voz; voltar ao Chat desliga. O loop de voz (`_voice_loop`) usa o **mesmo** `_run_turn` do Chat (stream + selo da skill) e fala a resposta no fim; grava na sessão atual. Comandos `/` só existem no Chat.

### Atalhos e comandos

- `Shift+Tab` modo · `Ctrl+N` nova sessão · `Ctrl+O` sessões · `Ctrl+R` regenerar · `Ctrl+T` vai para o Copilot (voz) — some do rodapé dentro dele · `Esc` cancela a edição → interrompe o stream → sem nada em andamento, sai (CRT; Esc de novo sai já) — fora do rodapé · `↑` com input vazio edita a última mensagem · `Ctrl+K` paleta (`/menu`; binding com `priority=True` porque o `Input` usa Ctrl+K) · `Win+J` (global, via `agent.py`) abre/foca a TUI no Copilot · `Ctrl+Alt+T` (global, `TRANSLATE_HOTKEY`) traduz o texto selecionado em qualquer app (toast da bandeja + clipboard)
- Telemetria e atalhos dividem **uma** linha: o `Footer` vive dentro do `#statusbar` (classe `.statusbar`); o `ConfirmScreen` tem a sua própria linha igual (o Footer só enxerga a Screen dele)
- `JarvisApp` usa `inherit_bindings=False` para "Sair" ficar no fim do rodapé — não volte a herdar sem reordenar
- Telas cheias: `/status` (dashboard), `/skills` (cartuchos), `/log` (buffer do logger + timeline do último turno com skill), `/vault` (Obsidian; "usar no chat" manda a nota como contexto via `prompts/vault_note_context.md`), `/config` (preferências em `services/user_prefs.py`; a fala do JARVIS é a linha `#cfg-quip` no pé do painel — sem caixa de diálogo; SISTEMA tem o campo "Fontes de notícias" com botão Salvar → `core/news.py`; INTEGRAÇÕES = cards de `services/integrations.py`: Enter conecta em worker de thread, card fica AGUARDANDO, Del desconecta com `ConfirmScreen`). Nova integração = uma entrada em `integrations._build()` com `status()`/`connect()`/`disconnect()` que devolvem texto e nunca levantam. Boot: `JarvisApp(boot_fn=core.boot.run_boot)`; `Esc` na conversa toca o CRT (`Esc` de novo sai já). Labels com `[  OK  ]` precisam de `markup=False`. `JarvisScreen._merge_bindings` põe `esc Voltar` no fim do rodapé, como no canvas. Dentro delas os atalhos da conversa ficam desativados; widgets da conversa são sempre buscados em `app.main_screen`
- Não existe `/help`: a paleta `Ctrl+K` lista os comandos (`/`, `/help`, `/h` e `/?` abrem a paleta). `frontend/commands.py` é a fonte única — novo comando entra em `COMMANDS` e em `JarvisApp.run_command`
- `//texto` envia uma mensagem que começa com `/`
- Arrastar arquivo para o terminal = `/attach`: o Windows Terminal cola o caminho; `PromptInput._on_paste` usa `commands.dropped_paths()` (só quando **todo** o texto é caminho de imagem/áudio existente) e emite `FilesDropped`. Não chame `super()._on_paste` — o Textual já roda o handler do `Input` pelo MRO (colaria 2×)
- Linha de status: telemetria · selo de foco (`◷ FOCO 24m 1/4` / `☾ DND` / `[SILENT]`, resolução de minutos, sem timer próprio) · voz. Sem modelo (fica no `/config` → MODELO) e sem "Sair" no rodapé. A saúde (`core.health`, a cada `HEALTH_INTERVAL`, só depois do boot) não aparece no rodapé: fica no `/status` e falha nova vira notificação
- PortAudio não é thread-safe: enumerar o microfone só via `health.check_microphone()` (lock + cache). Crash nativo grava stack em `logs/crash.log` (faulthandler no `main.py`)
- Logo na aba: `core/wt_profile.py` grava o fragment do perfil `JARVIS` do Windows Terminal; launcher e `jarvis.cmd` abrem com `-p JARVIS`
- Paleta: entradas e busca fuzzy são lógica pura em `frontend/commands.py` (`palette_entries`, `filter_entries`); comandos que exigem argumento (`NEEDS_ARG`) só preenchem o input

### Visual

- **Cores só no `frontend/jarvis.tcss`**, como variáveis `$j-*` (prefixo evita sobrescrever variáveis do tema do Textual, como `$panel`)
- Estado crítico → classe `-critical` na tela da conversa (`app.main_screen`, nunca `self.screen`, que pode ser um modal); Copilot → classe `-copilot` (ciano neon)
- Nada de animação contínua: a telemetria é polling a cada `TELEMETRY_INTERVAL` (3 s) numa linha de status. **Única exceção:** a orb do Copilot (`JarvisOrb`, 8 fps) anima só nos estados `pensando`/`respondendo`; em `ouvindo` o timer é parado
- Orb pixel-art: quadros em `frontend/orb.py` (lógica pura, testada); cores via component classes `orb--*` no `jarvis.tcss`
- Streaming re-renderiza o Markdown no máximo a cada 50 ms (`STREAM_FLUSH_S`)

### Badge de skill (Copilot)

- `execute_command_stream(..., on_route=fn)` chama `fn(intent)` quando a mensagem vira skill; a TUI mostra `[INTENT] executando…` → `✓`/`✗` no cabeçalho da resposta
- Cabeçalhos são montados com `Content.assemble`, nunca markup: o Textual lê `[MAIÚSCULAS]` como tag e apaga o badge
- Horários do SQLite estão em UTC: sempre passar por `sessions.to_local()`  antes de mostrar

### Alertas

- O `SystemInfo` chama `JarvisApp._on_system_alert`; nunca omitir `is_status_signal=True` nos sinais `CRITICAL_START`/`CRITICAL_END` → evita o TTS pronunciar o código
- `process_system_alert` passa pelo `services/notify_filter.py`: alerta crítico (disco CRÍTICO, bateria crítica, GPU superaquecendo) sempre fala; com Não Perturbe, reunião na agenda ou app em tela cheia (prefs `dnd_auto_meeting`/`dnd_auto_fullscreen`) o resto vai para o backlog. O prefixo `[SISTEMA CRÍTICO]` vem em todo alerta — não use para classificar
- Com o Não Perturbe ligado (`state.dnd_active`, dono: `services/focus.py`), `process_system_alert` só guarda no `state.dnd_backlog` — sem fala, notify nem `pending_critical_action`; o resumo sai quando o DND desliga. Ações do `FocusManager` devolvem texto (quem chama mostra/fala); só troca de fase e fim de prazo anunciam sozinhas

### Agente residente (`backend/agent.py`)

- Processo separado (pythonw, sem janela, bandeja via `pystray`) que segura `GLOBAL_HOTKEY` e sobe no logon (valor `JARVIS` em `HKCU\…\Run`, ligado pelo instalador, `/config` → SISTEMA ou bandeja). Fechar a TUI não o fecha
- Fala com a TUI só por `core/presence.py` (arquivo `tui.json` + eventos nomeados) — nada de socket/HTTP. A TUI chama `register_tui` no `on_mount` (com serviços) e `unregister_tui` ao sair
- Leve de propósito: registra um pacote `core` vazio em `sys.modules` para não rodar o `core/__init__` (banco, MCP, skills). Módulos usados por ele (`config`, `logger`, `hotkey`, `presence`, `autostart`, `launcher`, `window_utils`, `updater`) não podem importar o pacote `core` inteiro
- Atualização automática (`core/updater.py`): `check_available()` (Release de `UPDATE_REPO` **mais novo** que `settings.VERSION`; nunca levanta; cache `updates/available.json` por `CACHE_TTL_S`) roda na abertura da TUI (`JarvisApp(update_fn=, install_fn=)`, depois do boot) e no agente com `--logon` (que então abre a TUI). Com versão nova a TUI mostra `UpdateScreen` (`frontend/screens/update.py`, orb parada); **qualquer tecla** chama `request_install()` → evento `presence.INSTALL_UPDATE` (agente → `install_latest`: espera a TUI fechar, baixa, confere o SHA-256 do `digest` e roda o setup `/VERYSILENT /SKIPOLLAMA /UPDATE`) ou, sem agente, sobe um com `--install-update`; a TUI fecha com o CRT. O agente se fecha e o `[Run]` com `Check: EhAtualizacao` o reabre. O setup fecha `python`/`pythonw` do runtime e apaga `{app}\app` e `{app}\runtime` antes de copiar: a versão nova substitui a antiga. Dev (sem `JARVIS_DATA_DIR`) nunca atualiza; `main.py --update-preview X` mostra a tela sem instalar. Toggle em `/config` → SISTEMA (registro `HKCU\Software\JARVIS\AutoUpdate`, padrão `AUTO_UPDATE`)

---

## Fluxo de um Comando de Voz (modo Copilot)

```
1. listen.py           → captura áudio (Google STT), detecta wake word "Jarvis"   · orb: ouvindo
2. frontend/app.py     → _voice_loop mostra a fala no log (sessão atual, "voz · HH:MM") · orb: pensando
3. brain.py            → execute_command_stream(mode="copilot"): pending_critical_action? → intent → skill ou LLM
4. frontend/app.py     → _run_turn pinta o stream + selo da skill                  · orb: respondendo
5. speak.py            → edge-tts (ou pyttsx3) → áudio                              · orb volta a ouvindo
```

`execute_command()` (sem stream) segue existindo para o modo standalone `python -m services.brain`.

---

## Fluxo de uma Mensagem no Chat (TUI)

```
1. PromptInput         → usuário digita + Enter (ou /comando)
2. JarvisApp.send      → monta bolhas e dispara o worker _stream (thread)
3. db.log_interaction  → salva a mensagem (com anexo, se houver /attach)
4. brain.py            → execute_command_stream(text, session_id, images, mode)
5. intent.py           → classify_intent(text, exclude_categories=("automation", "system") no Chat)
6. chat.py             → ask_local_ai_stream() → Ollama stream (ou skill no Copilot)
7. MessageView         → call_from_thread(set_text) a cada 50 ms → Markdown em tempo real
```

---

## Como Criar uma Nova Skill

1. Criar arquivo em `backend/skills/{categoria}/nome_da_skill.py`
2. Declarar `INTENT`, `PROMPT_TEXT`, `CATEGORY` e `execute(entity, command)`
3. A skill é **auto-descoberta** pelo `SkillLoader` no próximo boot — sem registro manual
4. Ela aparece em `/skills`. Categorias `automation`/`system` só rodam no Copilot (ou voz); `productivity`/`web` rodam também no Chat
5. Guia completo (contrato, confirmação de ação crítica, testes): `backend/skills/README.md`. Visão ponta a ponta do projeto: `docs/arquitetura.md`

---

## Variáveis de Ambiente (`.env`)

```bash
OLLAMA_MODEL=llama3
OLLAMA_HOST=http://localhost:11434
# Opcionais (vazio = padrão do Ollama). Ver core/llm.py
OLLAMA_NUM_CTX=4096      # contexto menor = KV cache menor = cabe mais na VRAM
OLLAMA_NUM_GPU=99        # camadas na GPU; se o Ollama recusar, é desativado sozinho
OBSIDIAN_HOST=http://127.0.0.1:27123
OBSIDIAN_API_KEY=sua_chave
MIC_INDEX=1
WAKE_WORDS=jarvis,javis,jarbas   # vírgula separa; vazio = lista padrão
GLOBAL_HOTKEY=win+j              # atalho do agente residente; vazio desliga
TRANSLATE_HOTKEY=ctrl+alt+t      # traduz a seleção (agente); vazio desliga
AUTO_UPDATE=True                 # atualiza no logon pelo Release do GitHub (só instalado)
UPDATE_REPO=                     # dono/nome dos Releases; vazio = repositório oficial
GOOGLE_CLIENT_ID=                # client OAuth "App para computador" do próprio usuário (+ GOOGLE_CLIENT_SECRET)
TOMTOM_API_KEY=                  # opcional: trânsito ao vivo (sem ela, OSRM)
POMODORO_FOCUS_MIN=25            # + POMODORO_SHORT_BREAK_MIN, _LONG_BREAK_MIN, _CYCLES
DEFAULT_LANGUAGE=pt-BR
DEBUG_MODE=False
```

---

## Instalação de Dependências

### Backend (Python)

```bash
cd backend

# Criar e ativar ambiente virtual (recomendado)
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# Instalar todas as dependências
pip install -r requirements.txt
```

Principais pacotes do `requirements.txt`:
```
textual            # TUI no terminal (chat/copilot)
ollama             # Cliente oficial do Ollama (LLM local)
faster-whisper     # Transcrição local de áudio (/attach)
SpeechRecognition  # STT via Google (voz opcional)
edge-tts           # TTS neural Microsoft (nuvem)
pyttsx3            # TTS offline (fallback)
pygame-ce          # Reprodução de áudio .mp3
psutil             # Monitoramento de hardware (CPU, RAM, disco, rede)
GPUtil             # Monitoramento de GPU Nvidia (opcional)
pycaw              # Core Audio API Windows (controle de volume)
pyautogui          # Ghost keyboard e mouse virtual
python-dotenv      # Carregamento de .env
colorama           # Logs coloridos no console (fora da TUI)
requests           # HTTP (usado nas skills sub-agentes)
```

> ⚠️ O Ollama deve estar instalado e rodando separadamente: [ollama.ai](https://ollama.ai). Baixar o modelo com `ollama pull llama3`.

### Plugin Obsidian (para RAG)

Instalar o plugin **"Local REST API"** no Obsidian e configurar no `.env`:

```bash
OBSIDIAN_HOST=http://127.0.0.1:27123
OBSIDIAN_API_KEY=sua_chave_gerada_pelo_plugin
```

---

## Desenvolvimento Local

### TUI

```bash
cd backend
python main.py
# Prefira o Windows Terminal: o conhost antigo renderiza mal cores e Unicode.
```

### Testes

```bash
cd backend
python -m pytest tests -q
ruff check .
```

Testes da TUI ficam em `backend/tests/` (`test_tui_app.py`, `test_tui_commands.py`, `test_tui_orb.py`) e usam `App.run_test()` + Pilot, com `stream_fn` fake, `voice=FakeVoice(...)` e `start_services=False` — sem Ollama, microfone nem hardware. O `tearDown` zera `state.voice_enabled`. `tests/__init__.py` põe a raiz no `sys.path` para importar `frontend`. Lint: `ruff check .` em `backend/` **e** em `frontend/`. Com `NO_COLOR` definido o Textual desenha em cinza.

### Backend standalone (modo voz sem interface)

```bash
cd backend
python -m services.brain
# Roda start_brain() diretamente no terminal (liga a voz)
```

---

## Tom e Personalidade do JARVIS

- **Frio, educado, levemente sarcástico** — tom Tony Stark
- **Modo Voz**: texto puro, sem Markdown, sem asteriscos, sem emojis
- **Modo Chat/Copilot (TUI)**: Markdown obrigatório, `**negrito**`, blocos de código; matemática em LaTeX dentro de bloco de código (o terminal não renderiza KaTeX)
- Respostas limpas de `*` e `#` antes de ir para o TTS
- Gírias expandidas via `SLANG_MAP` em `speak.py`

---

## Decisões Arquiteturais Importantes

| Decisão | Razão |
|---------|-------|
| TUI Textual em vez de React + PyWebView | WebView2 + Three.js custavam centenas de MB de RAM e GPU; a TUI roda no terminal com poucas dezenas de MB |
| Chamadas Python diretas em vez de bridge IPC | Sem `evaluate_js`, sem escape de string, sem mock fallback — o cérebro é um generator consumido pela TUI |
| Voz opcional e lazy | Mic, pyttsx3 e pygame só carregam quando a voz é ligada |
| SQLite local em vez de nuvem | Privacidade total, zero latência, funciona offline |
| Ollama local em vez de API Claude/GPT | Sem custo por token, privacidade, funciona sem internet |
| Prompts em `.md` em vez de strings Python | Editáveis sem tocar no código, versionáveis de forma legível |
| `ollama` lib em vez de `requests.post` | Gerenciamento de sessão mais robusto, streaming tipado |
| state.py separado | Evita importações circulares entre brain, alerts e chat |
| `skill.execute(entity, command)` com 2 args | Sub-agentes precisam da frase original para contexto |

---

## Imported Claude Cowork project instructions

Claude sempre que for realizar qualquer atividade relacionada a este projeto deve ser consultado no obsidian primeiro com os arquivos existentes na vault, e também se basear no repositório apresentado como contexto
