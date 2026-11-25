# Estrutura do repositório

Mapa das pastas e arquivos do J.A.R.V.I.S. Resumo e workflow em [`AGENTS.md`](../AGENTS.md); visão ponta a ponta em [`arquitetura.md`](arquitetura.md).

```
J.A.R.V.I.S/
├── frontend/                ← TUI (Textual), pacote Python `frontend` — visual do canvas "JARVIS TUI"
│   ├── app.py               ← JarvisApp: modos chat/copilot, bindings, stream, voz, alertas
│   ├── widgets.py           ← MessageView, PromptInput, JarvisOrb, Spectrum, VoiceStage (tela de voz do Copilot), ConfirmScreen (30 s)
│   ├── orb.py               ← Orb pixel-art 16×16 do Copilot (quadros + meio-bloco, lógica pura)
│   ├── sprites.py           ← Sprites 16-bit + efeitos (block_bar ▰▱, sparkline, bar_chart, CRT, scanline) — lógica pura; pintados pelo PixelSprite
│   ├── screens/             ← Telas cheias (JarvisScreen: topo + corpo + linha de status; Esc volta): /status, /skills, /log, /vault, /config (com cards de INTEGRAÇÕES em `integrations_panel.py`), save slots (SessionPicker, Ctrl+O), paleta Ctrl+K (CommandPalette); e BootScreen, UpdateScreen (atualização disponível), ShutdownScreen (CRT), HousePartyScreen
│   ├── commands.py          ← Parser puro dos /comandos + entradas da paleta Ctrl+K
│   ├── jarvis.tcss          ← Tema (cores como variáveis $j-*)
│   └── pyproject.toml       ← Herda o ruff do backend
│
├── backend/                 ← Python (cérebro cognitivo)
│   ├── main.py              ← Boot: sanity check, ensure_ollama_running, raiz no sys.path, JarvisApp(boot_fn=run_boot).run() (--copilot abre no modo voz)
│   ├── agent.py             ← Agente residente (pythonw, bandeja): atalho global Win+J abre/foca a TUI; sobe com o Windows (e sobe a ponte se algum canal estiver ligado)
│   ├── messenger.py         ← Ponte Telegram/Discord (pythonw, mutex próprio): o cérebro roda no PC, a plataforma é só o fio; modo Chat; reconcilia os canais ligados a cada 30 s
│   ├── core/                ← Infraestrutura
│   │   ├── state.py         ← Estado global (sys_monitor, pending_critical_action, voice_enabled, announce)
│   │   ├── pending.py       ← Ação crítica pendente: arm (sem sobrescrever, com id) / take / parse_reply (só frase de confirmação aprova)
│   │   ├── processes.py     ← Encerrar processo com segurança (nome + hora de criação) e lista PROTECTED
│   │   ├── llm.py           ← Cliente Ollama oficial (query_ollama / stream)
│   │   ├── hardware.py      ← scan_system_hardware() via PowerShell WMI
│   │   ├── alerts.py        ← process_system_alert() + PROCESS_JUDGEMENT_CACHE (com DND ligado guarda no backlog)
│   │   ├── health.py        ← Saúde de Ollama/Obsidian/mic/SQLite (boot + linha de status)
│   │   ├── notifications.py ← Toasts do Windows on/off (winreg HKCU)
│   │   ├── hotkey.py        ← Atalho global (RegisterHotKey) do agente
│   │   ├── presence.py      ← Ponte TUI⇄agente: tui.json + eventos nomeados (SUMMON/TO_CHAT/EXPLAIN) + explain.json (trecho a explicar)
│   │   ├── autostart.py     ← Valor JARVIS em HKCU Run (com --logon) + detecção/início do agente
│   │   ├── updater.py       ← Auto-update: Release do GitHub mais novo → tela ATUALIZAÇÃO DISPONÍVEL → tecla → setup silencioso (SHA-256 + assinatura Minisign conferidos)
│   │   ├── minisign.py      ← Ed25519 no formato Minisign: gerar chave, assinar (CI) e verificar (updater) contra a PUBLIC_KEY embutida
│   │   ├── launcher.py      ← Abre a TUI numa janela nova (wt ou console)
│   │   ├── prompts.py       ← load_prompt() com cache e string.Template
│   │   ├── uploads.py       ← load_local_file() + save_base64_upload() (/attach)
│   │   ├── transcription.py ← Whisper local (faster-whisper)
│   │   ├── config.py        ← Settings Singleton (.env, paths)
│   │   ├── database.py      ← DatabaseManager SQLite (9 tabelas)
│   │   ├── logger.py        ← JarvisLogger (console fora da TUI, arquivo sempre)
│   │   ├── obsidian.py      ← RAG sobre vault Obsidian via API REST (plugin Local REST API)
│   │   ├── oauth.py         ← OAuth Desktop genérico: PKCE + callback no loopback (Google Agenda, Spotify)
│   │   ├── secrets_store.py ← Cofre de Credenciais do Windows (keyring) p/ tokens OAuth (Google e Spotify); fallback JSON
│   │   ├── google_calendar.py ← Google Agenda (REST, só leitura): briefing, skill CALENDAR (resolve_period: dia, semana, fim de semana, mês, ano e os próximos; events_range com paginação; format_range por dia), is_busy(), upcoming() p/ os lembretes
│   │   ├── google_auth.py   ← GoogleAccount genérico (OAuth PKCE + token no Cofre + request autenticado): um segredo/card por integração
│   │   ├── gmail.py         ← Gmail (escopo gmail.modify): inbox, read_body, build_mime (resposta/anexo), send, save_draft, ensure_label, batch_modify, trash (Lixeira, 30 dias), find_contacts — sem exclusão permanente
│   │   ├── winget.py        ← winget: search (parser pt/en), best_match, install/download sem shell, id validado
│   │   ├── telegram_bot.py  ← Bot API por long polling (requests): só chat privado, token fora do log, backoff só em erro
│   │   ├── discord_bot.py   ← discord.py (gateway): responde DM ou menção
│   │   ├── messenger_ctl.py ← Ponte: canais ativos (token + pref), is_running (mutex), start (leve: o agente usa)
│   │   ├── traffic.py       ← Trânsito entre locais fixos (/rota <local> <endereço>): Nominatim + OSRM (grátis) ou TomTom (ao vivo)
│   │   ├── webwatch.py      ← Web Watch (lógica): preço no HTML (JSON-LD/meta/R$), hash do texto sem hora/data, linhas novas, release/commit cru do GitHub; URL só se `is_fetch_safe`
│   │   ├── news.py          ← Manchetes do briefing (/config → SISTEMA): 1 por fonte, a mais relevante (RSS oficial ou busca; Crossref p/ DOI; radicais `morr*` + `_FALSE_CONTEXT`; desempate pelo Ollama numa chamada só com a pref `news_ai`)
│   │   ├── briefing.py      ← Briefing diário em seções fixas (Clima, Computador, GitHub, Agenda, Trânsito, Manchetes); LLM só no fecho
│   │   ├── weather.py       ← Clima (Open-Meteo + local por IP) e saudação por horário
│   │   ├── github_client.py ← PyGithub: PRs, issues, commit, CI, create_issue (confirmação fica com quem chama)
│   │   ├── spotify.py       ← Spotify: OAuth PKCE, Web API e player
│   │   ├── web.py           ← Pesquisa DuckDuckGo + leitura das páginas (read_pages) + resumo no Ollama
│   │   ├── factcheck.py     ← Fact-Checking: afirmação → 2 buscas → 1 fonte por domínio → veredito JSON do Ollama + regras duras (≥2 fontes; senão INCONCLUSIVO/IMPRECISO)
│   │   ├── headless.py      ← Navegação headless: Playwright no Edge do Windows (channel="msedge", sem playwright install), perfil próprio, passos goto/click/fill/press/wait/extract (≤ 8), is_fetch_safe na navegação, nunca senha/cartão/CPF; render_html p/ o Web Watch
│   │   ├── clipboard.py     ← Monitor de clipboard, classificação (url/erro/código/inglês) e ações (/clip, skill CLIPBOARD)
│   │   ├── netwatch.py      ← Vigia de rede: foto (portas expostas, processos na internet, ARP), linha de base e diff
│   │   ├── window_utils.py  ← Win32: monitores, janela em foco, tela cheia, detecção de apresentação
│   │   ├── browser.py       ← Navegador Chromium sem CDP: janela (ordem Z), atalhos só com foco confirmado, UI Automation (URL da aba, lista/seleciona/fecha abas), is_fetch_safe
│   │   ├── youtube.py       ← find_video (página de resultados do YouTube → 1º videoId; ddgs de reserva) e limpeza de título de aba
│   │   ├── screen_capture.py← Captura da janela-alvo (pula o terminal do JARVIS) ou do monitor, só em memória (skill SCREEN_READ)
│   │   ├── ocr.py           ← OCR nativo do Windows (winrt, 0 VRAM, import tardio) + mask_secrets
│   │   ├── ollama_server.py ← Sobe `ollama serve` no boot se o Ollama local estiver fora
│   │   ├── boot.py          ← Etapas da tela de boot (run_boot)
│   │   ├── wt_profile.py    ← Fragmento do perfil JARVIS do Windows Terminal (logo na aba)
│   │   ├── utils.py         ← TTLCache
│   │   ├── selection.py     ← Copia a seleção (Ctrl+C; `restore=True` devolve o clipboard anterior) e lê/escreve o clipboard via Win32 (agente)
│   │   ├── skill_loader.py  ← Auto-discovery de skills (plug-and-play); carrega na etapa do boot (`manager.ensure_loaded()`), não no import
│   │   ├── power.py         ← Consumo de energia: GPU medida (nvidia-smi) + CPU/resto estimados; `meter` integra kWh/dia (config `power_daily`)
│   │   └── SystemInfo.py    ← psutil — monitoramento de hardware
│   ├── services/            ← Serviços cognitivos
│   │   ├── brain.py         ← Roteador: execute_command (voz) / execute_command_stream (TUI, por modo)
│   │   ├── intent.py        ← classify_intent() + is_skill_enabled()
│   │   ├── chat.py          ← ask_local_ai() + ask_local_ai_stream()
│   │   ├── sessions.py      ← Sessões/histórico do chat (SQLite)
│   │   ├── skill_settings.py← Liga/desliga skills e categorias (/skills)
│   │   ├── user_prefs.py    ← Preferências do /config (chaves pref_* na tabela config)
│   │   ├── focus.py         ← Pomodoro + Não Perturbe (FocusManager: /focus, /dnd, skill FOCUS_MODE)
│   │   ├── reminders.py     ← Lembretes: avisos antes dos eventos da agenda (com tempo de trajeto) e lembretes por pedido (/lembrete, skill REMINDER)
│   │   ├── web_watch.py     ← Web Watch: vigia página/preço/repositório (tabela web_watches), collect() no tick da TUI (/vigiar, skill WEB_WATCH)
│   │   ├── insights.py      ← Registro de insights: ideias da conversa → nota mensal em 🧠 Brainstorms (/ideia, skill INSIGHT_SAVE)
│   │   ├── clip_history.py  ← Histórico persistente do clipboard (tabela clipboard_history): busca, reuso, filtro de segredos
│   │   ├── net_guard.py     ← Guarda de rede: julga achados do netwatch, alerta, encerra processo/bloqueia IP com confirmação (/rede)
│   │   ├── net_trust.py     ← Softwares mantidos no Vigia de rede (tabela net_trusted_apps: nome + executável); conferido antes do juiz, sobrevive ao /rede reset
│   │   ├── mailbox.py       ← Caixa de entrada p/ TUI/voz/briefing/ponte: lista priorizada (cache = numeração vista), resumo como dado, VIP, /email
│   │   ├── email_triage.py  ← Prioridade (ALTA/MÉDIA/BAIXA) e categoria (urgente/financeiro/promoções/social) — regras puras
│   │   ├── email_compose.py ← Rascunho pelo LLM (só assunto/corpo), confirmação obrigatória; não = rascunho no Gmail; outra frase = ajuste (on_other)
│   │   ├── email_contacts.py← "Guilherme" → endereço (tabela email_contacts + histórico do Gmail; vários = pergunta)
│   │   ├── email_organize.py← Plano (arquivar promoções, marcadores JARVIS/Financeiro e JARVIS/Urgente) → "sim" → batchModify; nunca apaga
│   │   ├── email_trash.py   ← "Apaga o e-mail 3" / "as promoções" → lista → "sim" → Lixeira do Gmail (o que apagar vem só da fala: números ou categoria)
│   │   ├── local_files.py   ← Acha arquivo do usuário p/ anexar (Desktop/Documentos/Downloads/OneDrive); bloqueia sensíveis, fora do perfil e >25 MB
│   │   ├── software.py      ← Download inteligente: winget → confirmação → instala/baixa numa thread e anuncia
│   │   ├── headless_tasks.py← Tarefa web em segundo plano (skill HEADLESS_TASK): plano do modelo → validação → confirmação se envia algo → thread → resposta só com o texto da página → announce
│   │   ├── remote_chat.py   ← Núcleo da ponte: allowlist, sessão por usuário, brain em modo chat com owner canal:usuário, split por limite
│   │   ├── presentation.py  ← Modo Apresentação: /silent, skill PRESENTATION_MODE ou slides em tela cheia (PowerPoint, PDF, Canva, Google Slides no navegador) / PowerPoint aberto (pref) → mic fechado, TTS mudo, selo [SILENT]
│   │   ├── notify_filter.py ← Filtro de interrupções: prioridade × contexto (DND, reunião, tela cheia)
│   │   ├── integrations.py  ← Registro dos cards de /config → INTEGRAÇÕES (estado, conectar, desconectar)
│   │   ├── live_context.py  ← Dados reais no prompt do Chat (agenda do Google) quando a pergunta pede — evita alucinação
│   │   ├── memory.py        ← extract_fact_to_memory() → Obsidian
│   │   ├── listen.py        ← Ear lazy (STT + Wake Word "Jarvis") — mic só abre com a voz ligada
│   │   └── speak.py         ← TTS (edge-tts → fallback pyttsx3), no-op com a voz desligada
│   ├── skills/
│   │   ├── automation/      ← app_control, audio_control, browser_tabs, clipboard_assistant, keyboard_control,
│   │   │                       screen_control, software_install, spotify_control, work_macros, youtube_control  (só Copilot/voz)
│   │   ├── system/          ← network_guard, power_report, status_report, system_clear, system_security (só Copilot/voz)
│   │   ├── productivity/    ← calendar_agenda, daily_briefing, email_management, focus_mode,
│   │   │                       github_control, insight_note, presentation_mode, reminder, screen_read, traffic_commute, web_watch (Chat e Copilot)
│   │   └── web/             ← web_search, fact_check, headless_task               (Chat e Copilot)
│   ├── prompts/             ← Arquivos .md de prompt (system_prompt, classify_intent, mode_chat, mode_copilot, briefing...; skills/ p/ PROMPT_TEXT)
│   ├── tests/               ← pytest (backend + TUI)
│   └── docs/                ← Documentação por módulo
│
├── installer/               ← Instalador JARVIS-Setup.exe (Inno Setup 6)
│   ├── build_runtime.ps1    ← dist/runtime (Python 3.11 NuGet + libs) e dist/app (código sem testes/dados)
│   ├── jarvis.iss           ← Setup: páginas "Ollama necessário" (espera instalar) e "Modelo de IA" (dropdown + ollama pull)
│   ├── jarvis.cmd           ← Launcher instalado (Windows Terminal, JARVIS_DATA_DIR=%APPDATA%\JARVIS)
│   ├── sign_release.py      ← Assina o JARVIS-Setup.exe no release.yml (secret MINISIGN_SECRET_KEY) e confere contra a PUBLIC_KEY
│   └── test_setup.ps1       ← Instala em silêncio (/SKIPOLLAMA), confere e desinstala
├── docs/                    ← Documentação do projeto (índice no AGENTS.md): arquitetura, estrutura, regras do backend, TUI, skills, banco, alertas, agente residente, fluxos, variáveis de ambiente, personalidade, decisões e integrações OAuth
├── .github/workflows/       ← main.yml (CI: ruff + compileall + pytest em PR/push na main e DEV) e release.yml (push na main → testes → setup → Release vX.Y.Z só com JARVIS-Setup.exe)
├── env.example              ← Modelo do .env com todas as variáveis comentadas
└── VERSION                  ← versão publicada: o release calcula o patch pela última tag e o CI grava de volta na main e na DEV (dê `git pull` na DEV depois de cada release). Subir minor/major = editar para X.Y.0 no PR
```

## Modo instalado (`JARVIS_DATA_DIR`)

- O `jarvis.cmd` define `JARVIS_DATA_DIR=%APPDATA%\JARVIS`; com ela, `core/config.py` põe `.env`, logs, banco, uploads, áudio do TTS e token do Spotify lá (a pasta do programa pode ser só leitura). Sem ela (dev) tudo fica em `backend/` e o `.env` na raiz
- Todo caminho gravável **deve** sair de `settings.DIR_*` / `settings.DB_PATH` — nunca de `Path(__file__)`
- Nova lib: faixa no `requirements.txt` **e** regenere o `requirements.lock` (comando no cabeçalho do arquivo; CI e setup instalam do lock com `--require-hashes`); se for importante, inclua no smoke de `build_runtime.ps1`. Ferramentas de dev em `requirements-dev.txt` / `.lock`
- Integrações de conta (Google Agenda, Spotify) usam chaves **pessoais**: cada usuário cria o próprio app e preenche `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`SPOTIFY_CLIENT_ID` no `.env` (guia em [`integracoes-oauth.md`](integracoes-oauth.md)). Nunca versionar chaves. Tokens dos usuários só no Cofre do Windows (`core/secrets_store.py`); testes usam cofre em memória
- Variável nova do `.env` precisa de **default** no `Settings` (o setup copia o `env.example`, mas `.env` antigos não ganham a chave). Lista das variáveis em [`variaveis-ambiente.md`](variaveis-ambiente.md)
