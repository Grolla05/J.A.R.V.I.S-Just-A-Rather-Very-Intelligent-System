# CHANGES.md

Registro das mudanças aplicadas no J.A.R.V.I.S.

**Data:** 2026-11-13
**Escopo:** Tela "ATUALIZAÇÃO DISPONÍVEL!!" ao abrir o JARVIS (logon, Win+J, bandeja, menu Iniciar) com instalação por qualquer tecla; versão nova substitui a antiga sem sobras; Modo Apresentação automático com Canva, Google Slides e PowerPoint aberto.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | **`updater.check_available()`**: o Release do GitHub é **mais novo** que o `VERSION` instalado? (diferente mas mais velho não conta, sem downgrade). Nunca levanta; cache em `%APPDATA%\JARVIS\updates\available.json` por 6 h (`CACHE_TTL_S`) para Win+J/bandeja não consultarem o GitHub toda vez; cache de outra versão instalada é ignorado. Dev e "Atualização automática" desligada continuam sem nada | `backend/core/updater.py` |
| 2 | **Tela de atualização** (canvas "16 · Atualização disponível"): orb do JARVIS parada no centro, "ATUALIZAÇÃO DISPONÍVEL!!", `instalada vX ──▶ nova vY` e "Clique qualquer tecla para prosseguir". Aparece depois do boot (ou por cima do Copilot no boot silencioso do Win+J). Atalhos da conversa ficam desligados nela; o sinal SUMMON do agente não a fecha | `frontend/screens/update.py`, `frontend/screens/__init__.py`, `frontend/app.py`, `frontend/jarvis.tcss`, `backend/main.py` |
| 3 | **Qualquer tecla instala já**: a TUI chama `updater.request_install()` → evento novo `presence.INSTALL_UPDATE` para o agente (sem agente rodando, sobe um com `--install-update`) e fecha com o CRT. O agente espera a TUI fechar (até 60 s), baixa, confere SHA-256 e roda o setup `/UPDATE` (fluxo já existente). Falha no pedido = aviso e a TUI fica aberta | `backend/core/updater.py`, `backend/core/presence.py`, `backend/core/autostart.py`, `backend/agent.py` |
| 4 | **Logon**: o agente com `--logon` não instala mais em silêncio: verifica (mesmas tentativas 15/45/90/180 s) e, havendo versão nova, abre a TUI no Chat, que mostra a tela | `backend/agent.py` |
| 5 | **Versão nova "apaga" a antiga**: o `PrepareToInstall` (e o desinstalador) fecham `python.exe` **e** `pythonw.exe` do runtime (antes só o agente; uma TUI aberta travava arquivos e o `[InstallDelete]` deixava pedaços da versão antiga). Após atualizar, o setup baixado e o cache são apagados na hora (antes ficavam até o próximo logon). AppId fixo + `[InstallDelete]` de `{app}\app` e `{app}\runtime` seguem garantindo uma instalação só | `installer/jarvis.iss`, `backend/core/updater.py` |
| 6 | **Modo Apresentação automático**: além de PowerPoint/PDF em tela cheia, conta `Canva.exe` em tela cheia e navegador (Chrome, Edge, Firefox, Opera, Brave, Vivaldi) em tela cheia numa aba de slides (título com "Canva", "Google Slides", "Apresentações Google" ou "PowerPoint"). Pref nova **"Apresentação c/ PowerPoint aberto"** (ROTINAS, padrão ligado): o PowerPoint em foco já silencia, mesmo em janela | `backend/core/window_utils.py`, `backend/services/notify_filter.py`, `backend/services/user_prefs.py`, `backend/services/presentation.py`, `frontend/screens/settings.py` |
| 7 | `python main.py --update-preview 9.9.9` mostra a tela sem rede e sem instalar (dev) | `backend/main.py` |
| 8 | Documentação | `CLAUDE.md` |

**Testes novos:** `test_updater.py` — `check_available` (mais nova, igual/mais velha, cache e TTL, cache de outra versão, nunca levanta, dev/desligado, tentativas no logon), `install_latest` espera a TUI fechar, `request_install` (agente, sobe agente, falha), sucesso apaga setup e cache, agente no logon abre a TUI / adia / fica quieto, `run_install` só fecha o agente com o setup aberto. `test_tui_app.py` — tela aparece com as versões e orb parada, sem versão nova não aparece, qualquer tecla (até Shift+Tab) pede a instalação e fecha, falha mantém a TUI, prévia não instala. `test_presentation.py` — Canva app/navegador, Google Slides, PowerPoint Online, YouTube em tela cheia não conta, pref de PowerPoint aberto.

**Pendente (manual):** compilar o setup e testar de verdade (instalar versão antiga, publicar Release nova, logon → tela → tecla → versão nova em `/config` → SISTEMA, sem sobras em `{app}`); conferir no Canva ("Apresentar" em tela cheia) se o título da aba contém "Canva".

---

**Data:** 2026-11-10 (3)
**Escopo:** Fontes de notícias do briefing, Modo Apresentação, /config sem a caixa do JARVIS, skills de consulta no Chat, `/rota` com locais livres e Esc para sair.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | **Fontes de notícias**: `/config` → SISTEMA ganha o campo "Fontes de notícias do briefing" (texto separado por vírgula) com botão **Salvar alterações** (Enter também salva; o texto volta limpo, sem repetidos). Padrão: G1, BBC, CNN, New York Times, Wall Street Journal, SciELO, Google Acadêmico, DOI. Cada fonte vira `site:<domínio>` (nomes conhecidos ou domínio digitado), "DOI" busca artigos de periódico publicados desde ontem no Crossref; nome desconhecido vira busca livre. Uma manchete por fonte, começando por uma fonte diferente a cada dia. Guardado na tabela `config` (`news_sources`), sem variável nova no `.env` | `backend/core/news.py`, `backend/core/briefing.py`, `frontend/screens/settings.py`, `frontend/jarvis.tcss` |
| 2 | **Modo Apresentação**: `/silent [on\|off]`, skill **PRESENTATION_MODE** ("vou apresentar", "acabou a apresentação") ou automático com PowerPoint/leitor de PDF em tela cheia (pref "Modo apresentação auto" em ROTINAS). Enquanto ativo: alertas não-críticos vão para o backlog (críticos passam), o TTS não fala nem com `force=True`, o ouvido não abre o microfone e a linha de status mostra `[SILENT]`. Ao sair, resumo dos alertas guardados | `backend/services/presentation.py`, `backend/skills/productivity/presentation_mode.py`, `backend/prompts/skills/presentation_mode.md`, `backend/services/notify_filter.py`, `backend/services/speak.py`, `backend/services/listen.py`, `backend/core/window_utils.py`, `backend/core/state.py`, `backend/services/user_prefs.py`, `frontend/commands.py`, `frontend/app.py` |
| 3 | **/config sem a caixa do JARVIS** (rosto + fala): a fala vira uma linha no pé do painel (`#cfg-quip`), com as mesmas mensagens (ajustes, integrações, fontes salvas) | `frontend/screens/settings.py`, `frontend/jarvis.tcss` |
| 4 | **Skills no Chat**: o Chat passa a rodar as skills de `productivity` e `web` (agenda, trânsito, GitHub, busca, briefing, foco, apresentação) com o selo `[INTENT]`; `automation` e `system` seguem só no Copilot/voz (`CHAT_BLOCKED_CATEGORIES`). Ações que pedem confirmação (ex.: issue no GitHub) também funcionam no Chat. Briefing pela skill no Chat também é falado | `backend/services/intent.py`, `backend/services/brain.py`, `backend/prompts/mode_chat.md`, `frontend/app.py` |
| 5 | **`/rota <local> <endereço>` só cadastra** qualquer local fixo (casa, trabalho, faculdade, escola, academia…; apelidos como "facul", "colégio", "home"); `/rota` sem argumento lista os locais. Quem calcula é a skill **TRAFFIC**, por decisão do classificador: entende origem e destino na frase ("quanto tempo até a faculdade?", "da escola pra casa"), usa casa/trabalho pelo horário quando só um ponto é citado e avisa como cadastrar um local que não existe. Casa/trabalho mantêm as chaves antigas (briefing e aviso de saída inalterados) | `backend/core/traffic.py`, `backend/skills/productivity/traffic_commute.py`, `backend/prompts/skills/traffic.md`, `frontend/commands.py`, `frontend/app.py` |
| 6 | **Rodapé mais limpo e Esc para sair**: saem o nome do modelo e o "^q Sair" da linha de status; `Ctrl+Q` deixa de existir. Na conversa, `Esc` cancela a edição → interrompe a resposta → sem nada em andamento, sai com o CRT (Esc de novo sai na hora). Nas telas cheias o Esc continua sendo "Voltar" | `frontend/app.py`, `frontend/screens/shutdown.py`, `frontend/commands.py` |
| 7 | Documentação das regras novas | `CLAUDE.md` |

**Testes novos:** `test_news.py` (parse, mapeamento das fontes, rodízio diário, Crossref, fonte que falha, briefing usa as fontes), `test_presentation.py` (detecção PowerPoint/PDF, filtro + `[SILENT]`, resumo ao sair, TTS mudo com `force`, mic fechado, skill e `/silent`), `test_intent_chat_skills.py` (Chat oferece só productivity/web, cache separado por modo); ampliados `test_mode_routing.py` (skills por categoria no Chat, confirmação no Chat), `test_traffic.py` (locais livres, `places_text`, `trip_text`, origem/destino da skill), `test_tui_phase34.py` (/config sem caixa, campo de fontes em SISTEMA, ←→ no campo, Esc sai/para/volta), `test_tui_app.py` (rodapé sem modelo nem Sair).

**Pendente (manual):** abrir `/config` → SISTEMA, salvar fontes e rodar `/briefing` com "Manchetes no briefing" ligado; `/rota faculdade <endereço>` e perguntar "quanto tempo até a faculdade?"; apresentar no PowerPoint (F5) e conferir `[SILENT]`.

---

**Data:** 2026-11-10 (2)
**Escopo:** Atualização automática do app instalado, verificada só quando o JARVIS inicia com o Windows.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | **`core/updater.py`**: compara o `VERSION` instalado com o último Release do GitHub (`UPDATE_REPO`); se houver versão nova, baixa o `JARVIS-Setup.exe` para `%APPDATA%\JARVIS\updates`, confere tamanho e SHA-256 (`digest` do asset; sem digest ou URL fora do repositório = não instala) e roda o setup com `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SKIPOLLAMA /UPDATE`. Sem rede logo após o logon: tenta de novo (15/45/90/180 s) e desiste em silêncio. TUI aberta adia para o próximo logon. Dev (sem `JARVIS_DATA_DIR`) nunca atualiza. Setups antigos são apagados | `backend/core/updater.py` |
| 2 | **Só no logon**: o valor `JARVIS` do `HKCU\…\Run` passa a levar `--logon`; só com ele o agente verifica (bandeja, Win+J e menu Iniciar não). `autostart.ensure_logon_flag()` regrava valores antigos. Com `installing`, o agente fecha a bandeja e sai (libera o runtime); toasts "Baixando…", "Instalando…" e, na volta, "Atualizado para a versão X" | `backend/agent.py`, `backend/core/autostart.py` |
| 3 | **Instalador**: Run com `--logon`; `/UPDATE` (`EhAtualizacao`) reabre o agente ao fim do setup silencioso (sem `--logon`, não verifica de novo). O `PrepareToInstall` já fechava o pythonw antigo | `installer/jarvis.iss` |
| 4 | **`/config` → SISTEMA**: opção "Atualização automática" (registro `HKCU\Software\JARVIS\AutoUpdate`; padrão `AUTO_UPDATE`) e linha com a versão instalada | `frontend/screens/settings.py` |
| 5 | Novas variáveis com default: `AUTO_UPDATE=True`, `UPDATE_REPO` (vazio = repositório oficial) | `backend/core/config.py`, `env.example`, `CLAUDE.md` |

**Testes novos:** `test_updater.py` — versões, Release (404, sem asset, prerelease, URL estranha, sem digest), download (hash/tamanho errado apagam o arquivo), fluxo (dev, desligado, em dia, sem rede com novas tentativas, rede voltando, TUI aberta, instalação com `/UPDATE` e marcador, download adulterado nunca roda o setup), aviso pós-atualização, agente só verifica no logon e sai ao instalar, migração do `--logon`.

**Pendente (manual):** compilar o setup (ISCC) e testar de verdade: instalar uma versão antiga, fazer logoff/logon e ver o toast + a versão nova em `/config` → SISTEMA.

---

**Data:** 2026-11-10
**Escopo:** Login de contas de verdade no Google Agenda e no Spotify (OAuth pelo navegador com escolha de conta), conexão salva entre reinícios e chaves **pessoais** documentadas.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | **Chaves pessoais**: cada usuário cria o próprio app no Google Cloud (client "App para computador") e no Spotify Developer e preenche `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e `SPOTIFY_CLIENT_ID` no `.env`. Guia passo a passo com tabela de erros comuns; aviso no README e no `env.example`. Sem chave, o card diz qual variável falta, abre o painel do serviço e aponta o guia | `docs/integracoes-oauth.md`, `README.md`, `env.example`, `core/config.py`, `core/google_calendar.py`, `services/integrations.py`, `skills/automation/spotify_control.py` |
| 2 | **Escolha de conta no navegador**: Google abre em "Escolha uma conta" (`prompt=select_account consent`); Spotify sempre mostra login/consentimento (`show_dialog=true`). Página de retorno no visual do JARVIS (CONECTADO / NEGADO) | `core/google_calendar.py`, `core/spotify.py`, `core/oauth.py` |
| 3 | **Spotify usa o OAuth comum** (`oauth.authorize` com porta e caminho fixos do redirect cadastrado); some o servidor de callback próprio. Depois do login busca o nome da conta (`/v1/me`) e o card mostra "conta: …" | `core/spotify.py`, `services/integrations.py` |
| 4 | **Conexão salva**: token do Spotify vai para o Cofre do Windows (o `spotify_token.json` antigo é migrado e apagado); Google já estava lá. Access token renova sozinho; Enter num card já conectado não abre o login de novo ("Del para trocar de conta"). Só pede reconexão se o serviço revogar (`invalid_grant`); erro de rede mantém a conta | `core/spotify.py`, `core/google_calendar.py`, `services/integrations.py` |
| 6 | **Chat consulta a agenda de verdade**: no modo Chat as skills não rodam, então "o que tenho amanhã?" ia direto ao LLM, que inventava compromissos. `services/live_context.py` detecta pergunta de agenda (palavras-chave, sem LLM), resolve o dia (hoje, amanhã, dia da semana), busca os eventos reais no Google Agenda e injeta no prompt (`prompts/calendar_context.md`) com a regra de não inventar; agenda desconectada ou com erro vira instrução de dizer isso. Temperatura 0.1 quando há dados reais. `resolve_day` foi para `core/google_calendar.py` (skill CALENDAR reusa). Validado com a agenda real + Ollama | `services/live_context.py`, `prompts/calendar_context.md`, `services/chat.py`, `services/brain.py`, `core/google_calendar.py`, `skills/productivity/calendar_agenda.py` |
| 5 | /config: a fala do JARVIS quebra linha (instrução longa não some na borda) e o aviso no canto só aparece quando um card muda de estado (antes empilhava o mesmo texto a cada Enter) | `frontend/screens/settings.py`, `frontend/jarvis.tcss` |

**Testes novos:** `test_live_context.py` (detecção da pergunta, eventos reais do dia pedido, agenda livre/desconectada/com erro, contexto chega ao modelo); `test_oauth_connect.py` — loopback de verdade com socket (código, porta/caminho fixos, página de negado), escolha de conta, fluxo do Spotify com conta, token sobrevivendo a reinício, migração do arquivo antigo, renovação sem login, revogação × erro de rede (Google e Spotify), card conectado não reabre login, card sem chave aponta o `.env` e o guia, docs citam as chaves pessoais. Cofre em memória nos testes (nunca o Cofre real).

**Pendente (manual):** criar os apps seguindo `docs/integracoes-oauth.md`, preencher as variáveis já cadastradas (vazias) no `.env` local, reiniciar e conectar pelos cards.

---|---------|----------|
| 1 | **Client IDs do projeto embutidos**: o JARVIS lê `backend/oauth_clients.json` (Google: client "App para computador" + secret; Spotify: client ID). O arquivo não vai para o repositório: o `release.yml` grava a partir dos GitHub Secrets `JARVIS_GOOGLE_CLIENT_ID`, `JARVIS_GOOGLE_CLIENT_SECRET` e `JARVIS_SPOTIFY_CLIENT_ID` antes do build. `.env` continua sobrescrevendo. O usuário não cadastra nada | `core/config.py`, `.github/workflows/release.yml`, `.gitignore`, `backend/oauth_clients.example.json` |
| 2 | **Escolha de conta no navegador**: Google abre em "Escolha uma conta" (`prompt=select_account consent`); Spotify sempre mostra login/consentimento (`show_dialog=true`). Página de retorno no visual do JARVIS (CONECTADO / NEGADO) | `core/google_calendar.py`, `core/spotify.py`, `core/oauth.py` |
| 3 | **Spotify usa o OAuth comum** (`oauth.authorize` com porta e caminho fixos do redirect cadastrado); some o servidor de callback próprio. Depois do login busca o nome da conta (`/v1/me`) e o card mostra "conta: …" | `core/spotify.py`, `services/integrations.py` |
| 4 | **Conexão salva**: token do Spotify vai para o Cofre do Windows (o `spotify_token.json` antigo é migrado e apagado); Google já estava lá. Access token renova sozinho; Enter num card já conectado não abre o login de novo ("Del para trocar de conta"). Só pede reconexão se o serviço revogar (`invalid_grant`); erro de rede mantém a conta | `core/spotify.py`, `core/google_calendar.py`, `services/integrations.py` |
| 5 | Mensagens de "sem client" falam do build (não pedem mais para o usuário editar o .env); guia de cadastro dos apps para o mantenedor, incluindo o aviso de que app do Google "Em teste" expira o token em 7 dias | `services/integrations.py`, `skills/automation/spotify_control.py`, `docs/integracoes-oauth.md` |

**Testes novos:** `test_oauth_connect.py` — client embutido (BOM, vazio, .env vence), loopback de verdade com socket (código, porta/caminho fixos, página de negado), escolha de conta, fluxo do Spotify com conta, token sobrevivendo a reinício, migração do arquivo antigo, renovação sem login, revogação × erro de rede (Google e Spotify), card conectado não reabre login. Os testes usam cofre em memória (nunca o Cofre real).

**Pendente (manual):** cadastrar os apps (ver `docs/integracoes-oauth.md`), pôr os IDs no `.env` para testar em dev e nos GitHub Secrets para o instalador; colocar o app do Google **Em produção** para o login não expirar em 7 dias.

---

**Data:** 2026-11-10
**Escopo:** TUI aberta pelo agente (Win+J / bandeja) abre direto na interface do Copilot, sem a tela de boot.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `--copilot` (usado só pelo agente) liga `quiet_boot`: a conversa já aparece no Copilot e as checagens do boot rodam num worker de thread; etapas com `warn`/`fail` viram notificação "Boot". A etapa do microfone fica de fora (o Copilot já abre o mic e duas threads no PortAudio derrubam o processo); a saúde roda ao fim, como no boot normal. Aberto à mão (`jarvis.cmd` / `python main.py`) continua com a tela de boot | `frontend/app.py`, `backend/main.py`, `backend/core/boot.py` (`MIC_STEP`) |

**Testes novos:** `test_quiet_boot_skips_screen_and_notifies_problems` em `test_tui_phase34.py`.

---

**Data:** 2026-11-09 (4)
**Escopo:** /config → INTEGRAÇÕES (canvas 15), Google Agenda, trânsito antes de sair, tradução do texto selecionado e filtro inteligente de notificações.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | **INTEGRAÇÕES no /config** (entre ROTINAS e SISTEMA): cards Google Agenda, GitHub, Spotify e Trânsito com LED, selo (CONECTADO / AGUARDANDO / DESCONECTADO / CONFIGURAR), detalhe e dica de tecla. Setas andam na grade; Enter conecta em worker de thread (card fica AGUARDANDO enquanto o navegador espera); Del desconecta com confirmação. `ConfirmScreen` aceita título/botões próprios | `services/integrations.py`, `frontend/screens/integrations_panel.py`, `frontend/screens/settings.py`, `frontend/widgets.py`, `frontend/jarvis.tcss` |
| 2 | **OAuth genérico + cofre**: PKCE e callback num servidor efêmero do loopback (porta livre, valida `state`); refresh tokens no Cofre de Credenciais do Windows via `keyring` (fallback JSON). O Spotify passa a reusar o PKCE daqui | `core/oauth.py`, `core/secrets_store.py`, `core/spotify.py`, `requirements.txt`, `installer/build_runtime.ps1` |
| 3 | **Google Agenda** (só leitura, REST com `requests`): cada usuário usa o próprio client "App para computador" (`GOOGLE_CLIENT_ID/SECRET`); sem client, o card abre o Google Cloud Console. Agenda entra no briefing; skill **CALENDAR** ("o que tenho amanhã?", "próxima reunião", dias da semana) | `core/google_calendar.py`, `skills/productivity/calendar_agenda.py`, `prompts/skills/calendar.md`, `core/briefing.py`, `prompts/briefing.md` |
| 4 | **Trânsito**: `/rota casa|trabalho <endereço>` (Nominatim) e `/rota` mostra o tempo agora; OSRM grátis ou TomTom (`TOMTOM_API_KEY`) com trânsito ao vivo; sentido inverte depois das 15 h. Entra no briefing em dias úteis; skill **TRAFFIC**; **aviso de saída** (ROTINAS → horário) com clima + trânsito + agenda, 1×/dia no tick da telemetria | `core/traffic.py`, `skills/productivity/traffic_commute.py`, `frontend/commands.py`, `frontend/app.py`, `services/user_prefs.py` |
| 5 | **Tradução do texto selecionado**: `Ctrl+Alt+T` (`TRANSLATE_HOTKEY`) no agente copia a seleção (Ctrl+C sintético depois de soltar o atalho), traduz no Ollama (pt → inglês; resto → pt-BR), põe no clipboard (Win32, sem PowerShell) e mostra toast da bandeja. `GlobalHotkey` ganhou id por atalho | `agent.py`, `core/selection.py`, `core/clipboard.py`, `core/hotkey.py`, `prompts/translate_selection.md` |
| 6 | **Filtro de notificações**: prioridade do alerta (crítico = disco CRÍTICO, bateria crítica, GPU superaquecendo) × contexto (Não Perturbe, reunião na agenda, app em tela cheia). Crítico sempre fala; o resto vai para o backlog e é resumido quando o silêncio acaba. Prefs "Silenciar em reunião/tela cheia" em ROTINAS; selo `☾ REUNIÃO` / `☾ TELA CHEIA`. Janela só maximizada não conta como tela cheia | `services/notify_filter.py`, `core/alerts.py`, `core/window_utils.py`, `core/state.py`, `frontend/app.py` |
| 7 | Novas variáveis com default: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `TOMTOM_API_KEY`, `TRANSLATE_HOTKEY`; docs atualizadas | `core/config.py`, `env.example`, `CLAUDE.md` |

**Testes novos:** `test_oauth.py`, `test_integrations.py`, `test_google_calendar.py`, `test_traffic.py`, `test_selection.py`, `test_notify_filter.py`; ampliados `test_briefing.py`, `test_hotkey_agent.py`, `test_alerts_cache.py`, `test_tui_phase34.py` (cards de integrações e aviso de saída).

**Pendente (manual):** criar o client OAuth Desktop no Google Cloud (ativar Calendar API, seu e-mail como usuário de teste) e conectar pelo card; `/rota casa …` e `/rota trabalho …`; reiniciar o agente para o `Ctrl+Alt+T`; conferir o silêncio em tela cheia (F11 num vídeo).

---

**Data:** 2026-11-09 (3)
**Escopo:** Issue #29 — "Memorizado no vault" respondido mesmo quando a nota já existia e o valor novo era descartado.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `ObsidianClient.save_memory` devolve `MEMORY_SAVED` (nota criada), `MEMORY_KEPT` (nota já existia; vault mantido, valor novo descartado) ou `None` (falha ao gravar), em vez de `True` para os dois primeiros casos | `backend/core/obsidian.py` |
| 2 | `extract_fact_to_memory` só diz "Memorizado" quando gravou; nota existente com o mesmo valor → "Já estava memorizado"; com valor diferente → avisa que manteve a versão do vault (mostra o valor atual) e pede para editar a nota no Obsidian; falha de gravação deixa de cair no genérico "não consegui extrair" | `backend/services/memory.py` |

**Testes novos:** `test_memory_save.py` (retornos de `save_memory` e as 4 respostas). 408 testes passando, ruff limpo.

---

**Data:** 2026-11-09 (2)
**Escopo:** Correções de interface: crash intermitente no boot, rodapé, logo na aba do Windows Terminal, VU de voz, fim do `/help` e `/skills` por categoria.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | **Crash `0xC0000005` no boot.** Causa: o poll de saúde disparava no `on_mount` e enumerava o microfone (`PyAudio()`/`terminate()`) ao mesmo tempo que a etapa `services.listen` do boot — PortAudio não é thread-safe. `check_microphone()` agora roda sob lock e com cache (PortAudio é tocado uma vez; o boot força a releitura); o 1º poll de saúde só sai quando a tela de boot fecha. `faulthandler` grava o stack de crashes nativos em `logs/crash.log`. O `jarvis.cmd` desliga rastreio de mouse/tela alternativa depois que a TUI sai (o lixo `[555;89;14M…` no prompt) | `backend/core/health.py`, `backend/core/boot.py`, `frontend/app.py`, `backend/main.py`, `installer/jarvis.cmd` |
| 2 | Selos `OLL● OBS● MIC● DB●` saem do rodapé; a saúde segue no `/status` e falha nova vira notificação | `frontend/app.py` |
| 3 | Logo do JARVIS na aba: `core/wt_profile.py` grava um fragment do Windows Terminal com o perfil `JARVIS` (ícone `jarvis.ico`); launcher do agente e `jarvis.cmd` abrem com `-p JARVIS`; o desinstalador apaga o fragment. O `+`/`⌄` do WT não podem ser escondidos por janela (limitação do WT) | `backend/core/wt_profile.py`, `backend/core/launcher.py`, `backend/main.py`, `installer/jarvis.cmd`, `installer/jarvis.iss` |
| 4 | VU de voz fiel: o tap mede **todos** os blocos do microfone e avisa o pico de cada janela (antes media 1 bloco a cada 125 ms e descartava o resto); escala em dBFS com piso no limiar de energia do recognizer (barra zerada = JARVIS não está te ouvindo); barra sobe na hora e desce suave; sai a onda falsa inicial | `backend/services/listen.py`, `frontend/widgets.py` |
| 5 | `/help` removido: `Ctrl+K` lista tudo; `/`, `/help`, `/h` e `/?` abrem a paleta; placeholder vira "(Ctrl+K menu)" | `frontend/commands.py`, `frontend/app.py`, `frontend/README.md`, `CLAUDE.md` |
| 6 | `/skills`: cartuchos agrupados por categoria (título colorido + grade, linha separando uma categoria da outra) numa área rolável; o foco leva a rolagem junto | `frontend/screens/skills.py`, `frontend/jarvis.tcss` |

**Testes novos:** `test_wt_profile.py`; `test_health.py` (cache e serialização do mic); `test_tui_phase34.py` (dBFS, limiar, pico da janela, release do VU); `test_tui_app.py::test_skills_screen_groups_by_category_and_scrolls`; `test_tui_commands.py` (`/help` → paleta); `test_hotkey_agent.py` (`-p JARVIS`). 401 testes passando, ruff limpo.

**Pendente (manual):** abrir/fechar a TUI várias vezes para confirmar que o crash sumiu; ver a logo na aba (vale a partir da 2ª abertura, depois que o fragment existe); conferir o VU falando baixo/normal/alto.

---

**Data:** 2026-11-09
**Escopo:** Pendências de 08/11 (ícone, testes do WORK_MACRO), arrastar arquivo para a TUI e briefing sempre falado.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | Arrastar imagem/áudio para o Windows Terminal = `/attach`: `dropped_paths()` (pura) aceita o texto colado só quando **todo** pedaço é arquivo existente de imagem/áudio (com/sem aspas, vários arquivos); `PromptInput` intercepta o `Paste` e emite `FilesDropped`; sem bracketed paste, enviar só o caminho também anexa. Uma imagem por mensagem (fica a primeira, com aviso); áudios são todos transcritos. Dica no `/help` | `frontend/commands.py`, `frontend/widgets.py`, `frontend/app.py` |
| 2 | Ícone `installer/assets/jarvis.ico` (16–256 px) gerado do `frontend/assets/Logo.jpg` (orb do `/status` em 8 bits): instalador, atalhos e bandeja do agente passam a usá-lo — nenhum código mudou, os `#if FileExists` e o `_tray_image()` já o procuravam | `installer/assets/jarvis.ico`, `frontend/assets/Logo.jpg` |
| 3 | `test_work_macros_spotify.py` → `test_work_macros.py`: saem os casos de `_sanitize_spotify_uri`/`_is_playing_title` (moraram para `core/spotify.py`, já cobertos por `test_spotify_client.py`); ficam os das cenas e entra `TestStartPlaylist` (Web API autorizada, fallback para o app local quando a API falha ou sem autorização). Fim das 11 falhas antigas | `backend/tests/test_work_macros.py` |
| 4 | Briefing sempre falado, em qualquer modo: automático (1º boot do dia), `/briefing` e skill `DAILY_BRIEFING`. `speak(..., force=True)` fala só pelo TTS mesmo com a voz desligada (microfone segue fechado); com a voz ligada o ouvido pausa durante a fala. No Copilot, a skill fala mesmo se o modo mudar no meio do turno. As outras ferramentas (`/web`, `/gh`…) seguem caladas | `backend/services/speak.py`, `frontend/app.py` |

**Testes novos:** `test_tui_drop.py` (parse dos caminhos + colar/enviar na TUI com Pilot) e `test_tui_tools.py::TestBriefingIsSpoken` (/briefing e automático falam com a voz desligada, skill no Copilot força a fala, /web segue calado).

**Pendente (manual):** Win+J com a TUI real, toasts somindo pelo registro, build do instalador com o ícone, arrastar PNG do Explorer para o Windows Terminal.

---

**Data:** 2026-11-08
**Escopo:** Atalho global (Win+J), agente residente na bandeja e início com o Windows.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `backend/agent.py`: agente leve (pythonw, ~30 MB, instância única por mutex `Local\JARVIS_AGENT`) que segura o atalho global e fica na bandeja (Abrir · Iniciar com o Windows · Sair). Win+J com a TUI fechada abre a TUI já no Copilot; com a TUI aberta fora de foco, foca a janela e manda ao Copilot; com ela em foco, volta ao Chat. Fechar a TUI não fecha o agente. Carrega só os submódulos de `core` que usa (pacote `core` vazio em `sys.modules`), sem banco, skills nem MCP | `backend/agent.py` |
| 2 | `core/hotkey.py` (`parse_hotkey` + `GlobalHotkey` com `RegisterHotKey` e laço de mensagens numa thread daemon), `core/presence.py` (`tui.json` com pid/hwnd em `DIR_DATA` + eventos nomeados `Local\JARVIS_SUMMON`/`JARVIS_TO_CHAT`), `core/autostart.py` (valor `JARVIS` em `HKCU\…\Run`, detecção e início do agente), `core/launcher.py` (abre a TUI no Windows Terminal ou num console novo), `window_utils.find_terminal_window()` | `backend/core/` |
| 3 | TUI: `main.py --copilot` → `JarvisApp(start_mode="copilot")`; a TUI anuncia a presença ao subir e escuta os sinais (SUMMON fecha telas cheias/paleta e entra no Copilot, nunca fecha o `ConfirmScreen`); `/config` ganha o grupo **SISTEMA** (Iniciar com o Windows ◀ ▶ e Agente em 2º plano, que o inicia) | `backend/main.py`, `frontend/app.py`, `frontend/screens/settings.py` |
| 4 | Instalador: tarefa "Iniciar o J.A.R.V.I.S com o Windows" (marcada), valor Run com `uninsdeletevalue`, sobe o agente no fim da instalação e o fecha antes de atualizar (`PrepareToInstall`) e de desinstalar (`[UninstallRun]`); `jarvis.cmd` repassa os argumentos (`--copilot`); `build_runtime.ps1` exige `pythonw.exe` e importa `pystray` no smoke | `installer/` |
| 5 | `GLOBAL_HOTKEY=win+j` (vazio desliga) e `pystray` nas dependências | `backend/core/config.py`, `env.example`, `backend/requirements.txt` |

**Contexto:** a TUI vive no terminal e o X do Windows Terminal mata o processo, então o "2º plano" é um processo separado. Ícone da bandeja/instalador (`installer/assets/jarvis.ico`) ainda não existe: a geração via nano-banana falhou (Gemini CLI recusou o cliente) e o agente usa um marcador liso até lá.

**Testes novos:** `test_hotkey_agent.py` (parse do atalho, presença com pid vivo/morto, autostart com winreg falso, comando do launcher dev/instalado, decisão do Win+J) e `test_tui_features.py::TestSummon`.

---

**Data:** 2026-11-08
**Escopo:** Command palette (Ctrl+K) estilo seletor de cartucho.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `CommandPalette` ("▶ SELECT"): filtro, lista agrupada (COMANDOS, MODO, FOCO, SKILLS) com glifo da skill, ↑↓/Enter/Esc. Comandos que exigem argumento (`/rename`, `/attach`, `/web`) só preenchem o input e somem no Copilot; skills alternam ON/OFF | `frontend/screens/palette.py`, `frontend/jarvis.tcss` |
| 2 | Lógica pura: `palette_entries()`, `fuzzy_score()` (prefixo > início de palavra > subsequência) e `filter_entries()` | `frontend/commands.py` |
| 3 | `Ctrl+K` com `priority=True` (o `Input` do Textual usa Ctrl+K para "apagar até o fim") e `/menu` | `frontend/app.py`, `frontend/commands.py` |

**Testes novos:** `test_tui_features.py::TestPaletteLogic` e `TestPaletteScreen` (abre com o prompt focado sem apagar o texto, "sta"+Enter abre o `/status`, prefill do `/rename`, skill alterna, `/menu`).

---

**Data:** 2026-11-08
**Escopo:** Não Perturbe + Pomodoro (por voz, `/focus` e `/dnd`).

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `services/focus.py` (`FocusManager`): Pomodoro 25/5, pausa longa de 15 depois de 4 focos (POMODORO_* no `.env`); foco liga o Não Perturbe, pausa desliga; trocas de fase anunciadas (texto + voz). DND manual com ou sem prazo. Guarda o valor anterior dos toasts (`dnd_restore` no banco) e restaura ao sair, no X do terminal e no próximo boot se o app cair | `backend/services/focus.py`, `backend/core/config.py`, `env.example` |
| 2 | `core/notifications.py`: toasts de todos os apps via `winreg` (HKCU, sem admin) no lugar do `os.system(powershell)` do `WORK_MACRO`, que agora não mexe nas notificações com o DND ligado | `backend/core/notifications.py`, `backend/skills/automation/work_macros.py` |
| 3 | Alertas proativos com DND ligado vão para `state.dnd_backlog` (máx. 20) sem fala, notificação nem pedido de confirmação; são resumidos ao fim do foco | `backend/core/alerts.py`, `backend/core/state.py` |
| 4 | Skill `FOCUS_MODE` ("inicia um pomodoro", "foco de 50 minutos", "não perturbe por 1 hora", "quanto falta?"): frases óbvias sem LLM, resto via `query_ollama` (JSON) | `backend/skills/productivity/focus_mode.py`, `backend/prompts/skills/focus_mode*.md`, `backend/prompts/classify_intent.md` |
| 5 | TUI: `/focus [min\|stop\|skip\|status]`, `/dnd [on\|off\|min]` (num worker) e selo na linha de status (`◷ FOCO 24m 1/4`, `☕ PAUSA 4m`, `☾ DND`) em minutos, no polling de 3 s | `frontend/app.py`, `frontend/commands.py`, `frontend/screens/skills.py` |

**Testes novos:** `test_focus.py` (ciclo completo com relógio/timer falsos, restauração dos toasts, backlog, crash, skill) e `test_tui_features.py::TestFocusCommands`.

---

**Data:** 2026-11-08
**Escopo:** Health check vivo na linha de status (Ollama, Obsidian, microfone, SQLite).

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `core/health.py`: checagens rápidas sem efeito colateral (`ok`/`warn`/`fail`), `run_all()`, `status_line()` e `newly_failed()`; o boot passa a usá-las (sem lógica duplicada) | `backend/core/health.py`, `backend/core/boot.py` |
| 2 | TUI: worker a cada `HEALTH_INTERVAL` (15 s) e bloco `OLL● OBS◐ MIC○ DB●` na linha de status (forma do glifo legível sem cor; verde/âmbar/vermelho no tema); notificação quando algo que estava de pé cai; painel "saúde" no `/status` | `frontend/app.py`, `frontend/widgets.py`, `frontend/screens/status.py`, `frontend/jarvis.tcss`, `backend/core/config.py` |

**Testes novos:** `test_health.py` e `test_tui_features.py::TestHealthStatus`.

---

**Data:** 2026-11-08
**Escopo:** Wake word configurável via `.env`.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `WAKE_WORDS` (vírgula separa; vazio = lista padrão) em `Settings`, normalizado por `parse_word_list()` | `backend/core/config.py`, `env.example` |
| 2 | `find_wake_word()` / `clean_phrase()`: palavra inteira, mais longas primeiro, `re.escape`, pontuação vira espaço (`sexta-feira` do `.env` casa com `sexta feira` do STT) | `backend/services/listen.py` |

**Testes novos:** `test_wake_words.py`.

**Pendência conhecida (anterior a estas mudanças):** `test_work_macros_spotify.py` tem 11 falhas porque chama `_sanitize_spotify_uri`/`_is_playing_title`, que não existem mais em `work_macros.py`.

---

**Data:** 2026-11-08
**Escopo:** GitHub com listas vazias — `/gh prs` e `/gh issues` quebravam com `list index out of range`.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | No PyGithub 2.x fatiar uma `PaginatedList` vazia (`[:8]`) lança `IndexError`: sem PR aberto ou issue atribuída, a resposta era "O GitHub não colaborou". `_take()` usa `itertools.islice`; `last_commit` trata repositório sem commits e mensagem vazia | `backend/core/github_client.py` |

**Contexto:** achado no 1º teste real com o token do `.env` (PyGithub 2.10.0): último commit e CI funcionavam, PRs e issues (ambos vazios) falhavam. Os testes usavam listas Python, que aceitam o fatiamento.

**Testes novos:** `test_github.py` (`_Paginated` imita a lista do PyGithub: `test_empty_paginated_lists_do_not_break`, `test_paginated_list_is_limited`).

---

**Data:** 2026-11-08
**Escopo:** Busca no vault (RAG) quebrada — `Erro ao processar resultado: Expecting value`.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | O `mcp-obsidian` usa HTTPS quando `OBSIDIAN_PROTOCOL` não vem no ambiente, mas a porta 27123 do plugin Local REST API é HTTP: toda busca falhava com `SSL WRONG_VERSION_NUMBER` e voltava como texto, que o `json.loads` não entende. `mcp_endpoint()` tira protocolo, host e porta do `OBSIDIAN_HOST` (sem esquema, 27124 = HTTPS e o resto = HTTP) e o cliente MCP passa `OBSIDIAN_PROTOCOL` | `backend/core/obsidian.py` |
| 2 | Resposta não-JSON da busca vira aviso "Busca indisponível: …" com o motivo real, uma vez por sessão (depois só no arquivo de log), em vez de ERROR a cada mensagem | `backend/core/obsidian.py` |

**Contexto:** apareceu ao testar a voz (Copilot), mas valia para todo turno do Chat/Copilot que consulta o vault: o contexto do Obsidian nunca era injetado.

**Testes novos:** `test_obsidian_endpoint.py` (protocolo por esquema/porta, padrões, texto de erro avisa 1× e devolve vazio sem ERROR).

---

**Data:** 2026-11-08
**Escopo:** Voz online (edge-tts) recusada com 403.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `edge-tts` fixado em `>=7.3.1`: a 7.2.8 recebe `403 Invalid response status` no handshake com `speech.platform.bing.com` (a Microsoft passou a recusar a versão do Edge que a lib antiga anuncia) e a voz caía no fallback offline. A 7.3.1 gera o áudio normalmente | `backend/requirements.txt` |

**Contexto:** teste da voz no Copilot exibiu `Falha na voz online (403, ...)`. Reproduzido com a 7.2.8 e resolvido com a 7.3.1 (síntese de teste OK).

---

**Data:** 2026-11-08
**Escopo:** Clipboard inteligente — monitor opt-in que sugere e skill `CLIPBOARD` (explicar / traduzir / resumir).

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `core/clipboard.py`: `read()` (PowerShell `Get-Clipboard -Raw`, sem janela), `classify()` heurístico (`url` / `code` / `english` / nada), `act()` com prompts próprios (link → `web.fetch_text` + `web.summarize`) e `ClipboardMonitor` (thread daemon, polling 1,5 s, hash do último conteúdo, histórico de 20). O que já estava copiado ao ligar não gera aviso; o conteúdo copiado nunca vai para o log | `backend/core/clipboard.py`, `backend/prompts/clipboard_*.md` |
| 2 | Skill `CLIPBOARD` ("explica/traduz/resume o que eu copiei") | `backend/skills/automation/clipboard_assistant.py`, `backend/prompts/skills/clipboard.md`, `backend/prompts/classify_intent.md` |
| 3 | TUI: preferência **Monitor de clipboard** (desligada por padrão) no grupo novo `ROTINAS` do `/config`, que liga/desliga o monitor na hora (`on_pref_changed`); aviso discreto na conversa no máximo a cada 30 s; `/clip [explicar\|traduzir\|resumir\|hist]` | `frontend/app.py`, `frontend/commands.py`, `frontend/screens/settings.py`, `backend/services/user_prefs.py` |
| 4 | `KEYBOARD_CONTROL` passa a ler o clipboard por `core.clipboard.read` | `backend/skills/automation/keyboard_control.py` |

**Testes novos:** `test_clipboard.py` (classificação, monitor 1× por conteúdo novo, start/stop idempotente com thread daemon, ações com LLM mockado, skill) e `test_tui_tools.py::TestClipCommand`.

---

**Data:** 2026-11-08
**Escopo:** Briefing diário automático (1º boot do dia) e sob pedido — skill `DAILY_BRIEFING` e `/briefing`.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `core/briefing.py`: `collect()` junta saudação, clima, CPU/RAM/bateria, arquivos modificados nas últimas 24 h (Desktop/Documentos/Downloads ou `BRIEFING_DIRS`, profundidade 2, teto de 4000 itens), resumo do GitHub e manchetes opcionais — cada fonte isolada em `try`. `build()` pede o texto ao Ollama (`prompts/briefing.md`) e cai numa lista Markdown sem LLM. `should_run_today()/mark_ran()` usam a chave `briefing_last_date` da tabela `config` | `backend/core/briefing.py`, `backend/prompts/briefing.md` |
| 2 | Clima e saudação saíram da skill `SYSTEM_REPORT` para `core/weather.py` (reuso no briefing, sem uma skill importar outra) | `backend/core/weather.py`, `backend/skills/system/status_report.py` |
| 3 | Skill `DAILY_BRIEFING` ("bom dia, Jarvis", "resumo do dia") | `backend/skills/productivity/daily_briefing.py`, `backend/prompts/skills/daily_briefing.md` |
| 4 | TUI: briefing sozinho no 1º boot do dia (falado se a voz estiver ligada), `/briefing` força; prefs **Briefing no 1º boot do dia** (ligado) e **Manchetes no briefing** (desligado) no grupo `ROTINAS` | `frontend/app.py`, `frontend/commands.py`, `frontend/screens/settings.py`, `backend/services/user_prefs.py` |
| 5 | `.env`: `BRIEFING_DIRS` (default vazio) | `backend/core/config.py`, `env.example` |

**Testes novos:** `test_briefing.py` (1× por dia, arquivos recentes em pasta temporária, fonte com erro isolada, manchetes só quando pedidas, fallback sem LLM, skill) e `test_tui_tools.py::TestBriefingCommand` (sem serviços nada roda sozinho; automático respeita pref e data).

---

**Data:** 2026-11-08
**Escopo:** Integração com o GitHub (PyGithub) — skill `GITHUB` e `/gh`; confirmação genérica de ação crítica.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `core/github_client.py`: PRs abertos, issues atribuídas, último commit, CI (Actions), `summary()` para o briefing e `create_issue`. Import tardio do `github`, erros 401/404 viram mensagem amigável | `backend/core/github_client.py` |
| 2 | Skill `GITHUB`: frases óbvias sem LLM (`parse_fast`), o resto via `skills/github_decision.md` (JSON). Criar issue nunca executa direto: pergunta e espera o "sim" (voz) ou o `ConfirmScreen` (30 s) | `backend/skills/productivity/github_control.py`, `backend/prompts/skills/github*.md` |
| 3 | `confirm_pending_action` aceita `pending['on_confirm']` (callable) — qualquer skill pode pedir confirmação; sem ele segue encerrando o processo (APP_CONTROL). A TUI abre o `ConfirmScreen` ao fim do turno quando a skill deixou uma ação pendente | `backend/services/brain.py`, `frontend/app.py` |
| 4 | `/gh [prs\|issues\|commit\|ci] [dono/repo]` (só leitura) | `frontend/app.py`, `frontend/commands.py` |
| 5 | `.env`: `GITHUB_TOKEN`, `GITHUB_DEFAULT_REPO` (default vazio = desligado). `PyGithub` no `requirements.txt` e no smoke do setup | `backend/core/config.py`, `env.example`, `backend/requirements.txt`, `installer/build_runtime.ps1` |

**Testes novos:** `test_github.py` (sem token, resolução do repo, listagens, erro 401, criação, `parse_fast`, fallback do LLM, issue só após confirmação / negada / sem título) e `test_tui_tools.py::TestGitHubCommand`.

---

**Data:** 2026-11-08
**Escopo:** Pesquisa web com sumarização local — skill `WEB_SEARCH` e `/web` (pasta `skills/web/` deixa de estar vazia).

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `core/web.py`: busca no DuckDuckGo (`ddgs`, sem chave), leitura das 3 primeiras páginas em paralelo com extração por `html.parser` (sem lxml), resumo no Ollama com citações `[n]` e lista de fontes; cache de 10 min por pergunta; sem LLM devolve os trechos | `backend/core/web.py`, `backend/prompts/web_summarize.md` |
| 2 | Skill `WEB_SEARCH` | `backend/skills/web/web_search.py`, `backend/prompts/skills/web_search.md`, `backend/prompts/classify_intent.md` |
| 3 | TUI: `/web <pergunta>` e `tool_reply()` — bolha do JARVIS preenchida por um worker de thread (reusada por `/gh`, `/briefing` e `/clip`) | `frontend/app.py`, `frontend/commands.py` |
| 4 | `/skills`: cores das categorias `web` e `productivity` e ícones das 4 skills novas | `frontend/jarvis.tcss`, `frontend/screens/skills.py` |
| 5 | `ddgs` no `requirements.txt` e no smoke do setup | `backend/requirements.txt`, `installer/build_runtime.ps1` |

**Testes novos:** `test_web.py` (extração de HTML, busca mockada, erros de rede, fluxo completo com cache, fallback sem LLM, skill) e `test_tui_tools.py::TestWebCommand`.

**Gate local (4 entregas juntas):** 307 passam; `ruff check .` limpo em `backend/` e `frontend/`. **Pré-existente:** os 11 testes de `test_work_macros_spotify.py` já falham no `HEAD` (`_sanitize_spotify_uri` / `_is_playing_title` não existem em `work_macros.py`; nenhum dos dois arquivos foi tocado aqui).

---

**Data:** 2026-11-07
**Escopo:** Selo da tela de boot que podia nunca aparecer (2ª falha do gate do Release) e ensaio do Release fora da `main`.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | Boot: cada linha de checagem era criada vazia e pintada por `call_after_refresh` uma única vez; se a montagem ainda não tinha terminado nesse refresh (PC/runner lento), `is_mounted` era falso e o selo `[ FAIL ]`/`[  OK  ]` nunca aparecia. Agora a linha já nasce com o estado e as atualizações usam os labels guardados, sem depender do momento da montagem | `frontend/screens/boot.py` |
| 2 | `release.yml` rodado por `workflow_dispatch` fora da `main` vira ensaio: gera e testa o setup e guarda como artifact (`JARVIS-Setup-ensaio`, 7 dias), sem criar tag nem Release | `.github/workflows/release.yml` |
| 3 | O 1º ensaio parou no ISCC (`The system cannot find the path specified`): a raiz do runner tem ~105 caracteres e arquivos do onnxruntime em `dist\runtime` têm ~156, passando do MAX_PATH (260) que o Inno Setup aceita. O workflow mapeia a raiz em `J:\` (`subst`) para build, setup e teste; o `build_runtime.ps1` falha cedo com mensagem clara se algum caminho passar do limite | `.github/workflows/release.yml`, `installer/build_runtime.ps1` |

**Contexto:** o Release do merge do PR #37 parou de novo no gate: `test_boot_screen_shows_checks_then_closes` esperou 10 s por um `[ FAIL ]` que nunca foi pintado no runner do GitHub.

**Testes novos:** `test_tui_phase34.py` (`test_boot_row_has_status_without_waiting_for_mount`: selo e classe corretos logo ao criar/atualizar a linha, antes de montar — falha com o código antigo). Gate local: 237 passam.

---

**Data:** 2026-11-07
**Escopo:** Ordem das sessões nos save slots com empate de horário — destrava o 1º Release automático.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `get_recent_sessions` ordenava só por `MAX(timestamp)`, que no SQLite tem resolução de segundo: duas conversas no mesmo segundo apareciam em ordem aleatória nos save slots. Agora desempata pela mensagem mais nova (`MAX(id) DESC`) | `backend/services/sessions.py` |

**Contexto:** o workflow de Release do merge do PR #36 parou no gate de testes — `test_session_picker_focuses_current_slot_card` falhava no runner do GitHub (rápido o bastante para gravar as duas sessões do teste no mesmo segundo). Nenhuma tag/Release foi criada; o próximo merge na `main` gera a `v1.0.0`.

**Testes novos:** `test_sessions_service.py` (`test_recent_sessions_same_second_newest_first`: três sessões com o mesmo timestamp saem da mais nova para a mais velha — falha sem a correção).

---

**Data:** 2026-11-06
**Escopo:** Instalador completo `JARVIS-Setup.exe` (mesmo processo do OhmFlow: Inno Setup + teste do setup) e Release automático a cada merge na `main`, com o instalador como único asset.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | Instalador Inno Setup 6: Python 3.11 embutido com todas as libs do `requirements.txt` + código; sem admin por padrão (`%LOCALAPPDATA%\Programs\JARVIS`), atalhos, opção de PATH (`jarvis`), atualização limpa por cima (AppId fixo) e desinstalador que pergunta se apaga os dados | `installer/jarvis.iss` (novo) |
| 2 | Página "Ollama necessário": se o Ollama não for encontrado, mostra o link oficial `https://ollama.com/download`, trava o Avançar e verifica a cada 2 s (pasta padrão, PATH do processo e do registro); ao detectar, avança sozinho | `installer/jarvis.iss` |
| 3 | Página "Modelo de IA": dropdown com llama3.2 (padrão), llama3.1:8b, qwen2.5:7b, mistral, gemma2:9b, phi3 ou "não baixar"; marca os já instalados (`ollama list`); opção do modelo de visão moondream. No fim, `ollama pull` em janela visível e `OLLAMA_MODEL` gravado no `.env` | `installer/jarvis.iss` |
| 4 | Montagem do conteúdo do setup: pacote NuGet oficial `python` 3.11.9 → `dist/runtime`, `pip install`, limpeza, bytecode pré-compilado e smoke test das libs; código sem testes/dados → `dist/app` | `installer/build_runtime.ps1` (novo) |
| 5 | Launcher: abre no Windows Terminal quando existir (`--here` roda no terminal atual) e define `JARVIS_DATA_DIR=%APPDATA%\JARVIS` | `installer/jarvis.cmd` (novo) |
| 6 | Modo instalado no config: com `JARVIS_DATA_DIR`, `.env`, logs, banco, uploads, áudio do TTS e token do Spotify vão para essa pasta (a pasta do programa pode ser só leitura). Sem a variável (dev) nada muda. `VERSION` lido do arquivo `VERSION` | `backend/core/config.py`, `VERSION` (novo) |
| 7 | Defaults para rodar sem `.env` completo: `SPEECH_RATE` (180), `MIC_INDEX` (0), `OLLAMA_HOST`, `OLLAMA_MODEL` (llama3.2) e `OBSIDIAN_HOST` — antes `int(None)` / `None.replace` derrubavam o import | `backend/core/config.py` |
| 8 | Teste do setup: instala em silêncio (`/SKIPOLLAMA`), confere arquivos, importa o JARVIS com o Python instalado em modo instalado (dados fora da pasta do programa), chave de desinstalação, desinstala e confere que nada ficou | `installer/test_setup.ps1` (novo) |
| 9 | Workflow de Release: no push da `main` (merge) roda ruff + pytest, calcula a versão (major.minor do `VERSION`, patch = última tag `vX.Y.*` + 1), monta o runtime, gera e testa o setup e publica o Release `vX.Y.Z` só com `JARVIS-Setup.exe` | `.github/workflows/release.yml` (novo) |
| 10 | README com a seção "Instalar" e como gerar o setup localmente | `README.md` |

**Decisões:** Python embutido em vez de PyInstaller, para o `SkillLoader` continuar carregando skills por arquivo (plug-and-play) e evitar hidden-imports de pycaw/ctranslate2. O modelo escolhido é **acrescentado** no fim do `.env` (o python-dotenv usa o último valor) para não reescrever nem recodificar o arquivo do usuário. O GitHub sempre anexa "Source code (zip/tar.gz)" ao Release; o único asset enviado é o `JARVIS-Setup.exe`. Ícone próprio fica para depois (o `.iss` usa `installer/assets/jarvis.ico` se existir; sem ele, o ícone do Python).

**Testes novos:** `test_config_paths.py` (modo instalado com `JARVIS_DATA_DIR`: dados e `.env` na pasta de dados, pastas criadas; modo dev inalterado; defaults sem `.env`); `installer/test_setup.ps1` (25 verificações). Tamanho: ~479 MB instalado, setup de ~130 MB.

---

**Data:** 2026-11-06
**Escopo:** Falso "PROTOCOLO CRÍTICO" corrigido e telas `/status` (canvas "6 · Dashboard de sistema") e `/log` (canvas "9 · Log de atividade") refeitas para ficarem iguais ao canvas.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | Protocolo crítico: o disco entrava em "cheio" por **porcentagem** livre (< 10%), então um C: de 222 GB com 20,9 GB sobrando deixava a TUI vermelha sem motivo. Agora usa **GB livres** (< 10 GB), o mesmo critério do aviso falado. Lógica extraída para `critical_reasons()` (testável) | `backend/core/SystemInfo.py` |
| 2 | O topo mostra o motivo (`⚠ PROTOCOLO CRÍTICO · disco C:\ com 8.2 GB livres`) e a entrada/saída do estado vai para o log | `backend/core/SystemInfo.py` (`critical_reasons`), `frontend/app.py` |
| 3 | `/status`: painéis com nome e valor no topo, gráfico de **barras espaçadas** que ocupa o painel inteiro com cada barra na cor da sua carga (ciano/âmbar/vermelho), detalhe embaixo em pt-BR (`8 núcleos · 3,6 GHz`, `22,7 / 32 GB`, `RTX 3060 · VRAM 7,1 / 12 GB`, `↓ 1,1 · ↑ 0,1 MB/s`). Lateral: núcleo pixel-art 16×16, faixa de carga, top processos por memória (`ollama · 2,1 GB`) e o limiar crítico. Topo `últimos N s` e `uptime HH:MM:SS`; `p` pausa | `frontend/screens/status.py`, `frontend/sprites.py` (`core_orb`, `spaced_bar_chart`, `bar_slots`), `backend/core/SystemInfo.py` (`get_dashboard_details`), `frontend/jarvis.tcss` |
| 4 | Rede do `/status` usa a última amostra da telemetria (antes uma 2ª chamada a `get_network_speed` zerava o contador e mostrava ~92 B/s) | `frontend/app.py` (`last_net`) |
| 5 | `/log`: topo com o arquivo do dia (`backend/logs/jarvis_AAAA-MM-DD.log · seguindo`), filtros com borda, timeline em caixa (título + passos em blocos ligados por fio, `✓ SPOTIFY ABERTO`, `FALA` tracejado), horário com milissegundos, módulo com pacote (`services.listen`), linha de erro com fundo vermelho, emojis tirados da exibição e `/` para buscar | `frontend/screens/log.py`, `backend/core/logger.py` (`dotted_module`, `file_path`), `frontend/jarvis.tcss` |
| 6 | Linha de status das telas cheias aceita uma dica própria, como no canvas: `/status` → `atualiza a cada 3 s`, `/log` → `N linhas · N avisos · N erros`, `/skills` → `skills só rodam no Copilot (voz)` | `frontend/screens/base.py` (`status_hint`), `frontend/screens/status.py`, `frontend/screens/log.py`, `frontend/screens/skills.py` |

**Decisões:** a orb e o rótulo da carga ficam ciano em BAIXA/MODERADA (como no canvas) e só ficam vermelhos em ALTA; as barras é que mostram a faixa. "Encerrar processo" (`k` no rodapé do canvas) ficou de fora: é ação destrutiva e pediria confirmação própria.

**Testes novos:** `test_tui_dashboard.py` (`critical_reasons` com disco em GB, CPU/RAM/GPU/bateria; `dotted_module`; barras espaçadas; números pt-BR, janela e uptime; textos do dashboard e processos; emojis, contagem, filtro com busca e timeline do `/log`); `test_tui_app.py` (motivo no topo crítico).

---

**Data:** 2026-11-06
**Escopo:** Ajustes de interface para ficar igual ao canvas "JARVIS TUI": tabela do `/help`, save slots em tela cheia (canvas "11 · Histórico — save slots") e cartuchos retrô no `/skills` (canvas "8 · Skills — cartuchos").

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `/help`: o `\|` de `/mode [chat\|copilot]` e `/skills [on\|off <skill\|categoria>]` quebrava a coluna da tabela Markdown; agora é escapado e a linha fica com 2 células | `frontend/commands.py` |
| 2 | Save slots (`Ctrl+O` / `/sessions`) viram tela cheia `CARREGAR` · "Escolha um save · N sessões", com grade de 2 colunas de cartões: nº do slot, título, `★` fixada, `hoje · 14:03 · 48 msgs · copilot`, última fala do JARVIS entre aspas e barra `▰` do tamanho da conversa. Foco começa na sessão aberta; setas navegam, Enter carrega, `p` fixa, `Del Del` apaga, `/` busca por título ou trecho | `frontend/screens/save_slots.py` (novo), `frontend/widgets.py` (sai o modal; `format_slot_when` substitui `format_when`), `frontend/app.py`, `frontend/jarvis.tcss` |
| 3 | Modo de cada mensagem gravado no histórico (coluna `mode`, com migração `PRAGMA`/`ALTER TABLE`); `get_recent_sessions` devolve `mode` e `last_reply` | `backend/core/database.py`, `backend/services/sessions.py`, `frontend/app.py` |
| 4 | `/skills`: cartucho retrô com aba na cor da categoria, etiqueta com ícone + INTENT, linha `■ categoria  ON/OFF` e contatos dourados; desligado fica apagado e 1 linha abaixo. Setas navegam a grade e Enter também alterna | `frontend/screens/skills.py`, `frontend/jarvis.tcss` (`$j-contact`) |
| 5 | Ícones dos cartuchos iguais ao canvas e cobrindo os INTENTs reais: SPOTIFY `♫`, KEYBOARD `⌨`, MACRO `⚙`, REPORT `≡`, CLEANUP `✕`, SECURITY `⛨` (antes SPOTIFY/CLEANUP/REPORT caíam no `◆`) | `frontend/screens/skills.py` |
| 6 | Telas cheias: `esc Voltar` passa para o fim do rodapé, como no canvas | `frontend/screens/base.py` |

**Decisões:** o picker deixou de ser modal para ter a barra do topo e a linha de status das outras telas cheias (o `dismiss(id)` segue igual para o `app`). A busca saiu do topo e foi para baixo da grade (`/` foca), porque `p` e `Del` são atalhos dos cartões. Sessões antigas sem modo gravado aparecem como `chat`.

**Testes novos:** `test_tui_commands.py` (tabela do `/help` com 2 células e `\|` preservado, `format_slot_when`, ícones dos INTENTs reais e glifos de 1 célula); `test_sessions_service.py` (`mode`/`last_reply`, migração da coluna `mode`); `test_tui_app.py` (save slots: selo, contagem, foco na sessão atual, setas, busca, meta `· chat`, prévia, ★, apagar; cartucho com ícone, nome, ON/OFF e contatos). Observação: `test_work_macros_spotify.py` já falhava antes desta mudança (11 testes; funções que não existem em `work_macros.py`).

---

**Data:** 2026-11-05
**Escopo:** Boot verifica o servidor Ollama e o inicia (`ollama serve`) se estiver offline, antes de carregar a TUI.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `ensure_ollama_running()`: sonda `GET /api/version` (2 s, sem proxy). Offline + host local → acha o `ollama` (PATH ou `%LOCALAPPDATA%\Programs\Ollama`), roda `ollama serve` sem janela, em outro grupo de processo e com a saída descartada, e espera a API por até `OLLAMA_START_TIMEOUT` s. Retorna `running` / `started` / `failed` e nunca derruba o boot | `backend/core/ollama_server.py` (novo) |
| 2 | `main.py` chama a checagem logo após o sanity check, antes de importar a TUI | `backend/main.py` |
| 3 | Etapa "core.llm / Ollama" da tela de boot mostra `[ FAIL ]` se o servidor seguir offline (e não dispara o warm-up à toa) | `backend/core/boot.py` |
| 4 | Novas variáveis `OLLAMA_AUTOSTART` (padrão `True`) e `OLLAMA_START_TIMEOUT` (padrão `30`) | `backend/core/config.py`, `env.example` |

**Decisões:** o servidor fica desacoplado e continua rodando depois que o JARVIS fecha (mesmo comportamento do app oficial do Ollama; evita recarregar o modelo a cada boot). Host remoto no `OLLAMA_HOST` não é iniciado — só avisa. Se o `ollama serve` morrer (ex.: outra instância já pegou a porta), uma última sonda decide. O `boot.bat` mantém a própria checagem; com ele, a do Python só confirma que está online.

**Testes novos:** `test_ollama_server.py`: normalização do host, host local × remoto, sonda (200 e conexão recusada), fallback do executável no `%LOCALAPPDATA%`, `Popen` com `serve` e saída descartada, espera (responde depois de N sondas, para se o processo morrer) e `ensure_ollama_running` (já online, offline → inicia, não instalado, sem resposta, `OSError` no `Popen`, host remoto, autostart desligado).

---

**Data:** 2026-11-05
**Escopo:** Fases 3 e 4 de 4 das novas telas 16-bit: `/vault`, `/config`, nível real do microfone na barra de voz, tela de boot, desligamento CRT e o easter egg "House Party Protocol".

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | Nível real do microfone: `_LevelTap` envolve o stream do mic e calcula o RMS de cada bloco (sem `audioop`, removido no 3.13), avisando no máx. 8×/s. `listen(on_level=)` repassa para a TUI | `backend/services/listen.py` |
| 2 | Barra de voz do Copilot mostra o espectro real (24 amostras ▁…█) e um VU de 15 blocos; zera fora do estado "ouvindo", sem timer | `frontend/widgets.py` (`VoiceBar.set_level`), `frontend/app.py` (`_listen_with_level`) |
| 3 | `/vault [termo]`: árvore do vault carregada pasta a pasta, busca com radar pixel-art girando só durante a busca, prévia em Markdown e "▶ usar no chat" — a nota vai como contexto da próxima mensagem (o histórico guarda só a pergunta) | `frontend/screens/vault.py` (novo), `backend/core/obsidian.py` (`list_dir`, `search_results`), `backend/prompts/vault_note_context.md` (novo), `frontend/app.py` (`pending_note`) |
| 4 | `/config`: menu estilo RPG (VOZ, MICROFONE, MODELO, SOBRE) com cursor ▶, opções ◀ ▶ e barra de blocos, e caixa de diálogo com o rosto pixel-art do JARVIS | `frontend/screens/settings.py` (novo), `backend/services/user_prefs.py` (novo) |
| 5 | Preferências persistidas na tabela `config`: voz neural, velocidade e volume do TTS; limiar do mic e janela de atenção | `backend/services/user_prefs.py`, `backend/services/speak.py`, `backend/services/listen.py` |
| 6 | Tela de boot: checagens estilo BIOS (`[  OK  ]`/`[ WARN ]`/`[ FAIL ]`), logo montado por scanline a 8 fps e barra de progresso; fecha sozinha (ou `Esc`). Warm-up do Ollama e scan de hardware seguem em threads daemon | `backend/core/boot.py` (novo), `frontend/screens/boot.py` (novo), `backend/main.py` |
| 7 | Desligamento CRT no `Ctrl+Q`/`/quit`: 3 linhas `[  OK  ]` e 5 quadros (tela cheia → faixa → linha → ponto); `Ctrl+Q` de novo sai na hora | `frontend/screens/shutdown.py` (novo), `frontend/app.py` (`shutdown_jarvis`) |
| 8 | Easter egg: digitar "house party" no Chat abre 8 armaduras genéricas em pixel art entrando 1 por quadro; não vai ao modelo | `frontend/screens/house_party.py` (novo), `frontend/app.py` |
| 9 | Comandos novos `/vault` e `/config` no `/help` | `frontend/commands.py` |

**Decisões:** o nível do mic é lido no próprio stream que o `speech_recognition` usa (nada de abrir um 2º dispositivo). A janela de boot não espera o Ollama (pode levar até 120 s): ele aquece em segundo plano. Labels com `[  OK  ]` usam `markup=False` — o Textual lia o selo como tag e o apagava. O modelo do Ollama segue só no `.env` (o `/config` mostra, não troca).

**Testes novos:** `test_tui_phase34.py`: RMS (silêncio, cheio, meio), `_LevelTap` (áudio intacto, limite de 8×/s, repasse do resto do stream), `user_prefs` (padrão, passo com limite, lixo no banco), `run_boot` (etapas, falha, fim), barra de voz com nível, `/config` persistindo, `/vault` (busca, radar parado, nota indo ao modelo sem sujar o histórico), boot fechando sozinho, CRT antes do `exit`, `Ctrl+Q` duplo e o easter egg.

---

**Data:** 2026-11-05
**Escopo:** Fase 2 de 4 das novas telas 16-bit: telas de dados (`/status`, `/skills`, `/log` e save slots) + ajustes da Fase 1 após comparar capturas reais da TUI com o canvas "JARVIS TUI".

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | Base das telas cheias: barra do topo com selo, corpo e linha única telemetria + atalhos; `Esc` volta. Atalhos da conversa (modo, nova, sessões, regenerar, voz) somem dentro delas | `frontend/screens/base.py` (novo, `JarvisScreen`), `frontend/app.py` (`check_action`) |
| 2 | `/status`: CPU, RAM, GPU e REDE com gráfico de barras dos últimos 2 min (cor muda com a carga), mini-orb pixel-art recolorida pela carga, top processos e uptime em worker | `frontend/screens/status.py` (novo), `frontend/sprites.py` (`bar_chart`, `load_level`), `frontend/app.py` (`telemetry_history`), `backend/core/SystemInfo.py` (`upload_bps`/`download_bps`) |
| 3 | `/skills` sem argumento abre a grade de cartuchos: ícone, INTENT, categoria e ON/OFF; desligado fica "fora do slot". Enter/clique alterna a skill, `c` a categoria inteira. `/skills on|off X` continua | `frontend/screens/skills.py` (novo), `frontend/app.py` |
| 4 | `/log`: buffer em memória dos últimos 500 registros, filtros TODOS/DEBUG/INFO/WARN/ERROR (`f` cicla), pausa no espaço, linhas novas mais claras e a timeline do último turno com skill (VOZ → INTENT → SKILL → ✓ → FALA) | `frontend/screens/log.py` (novo), `backend/core/logger.py` (`RingBufferHandler`, `stacklevel=2` p/ registrar o módulo de origem), `frontend/app.py` (`last_skill_turn`) |
| 5 | Save slots no `Ctrl+O`: cada sessão em 2 linhas, com barra do tamanho, nº de mensagens e prévia da última fala; `p` fixa, `Del Del` apaga (não apaga a aberta) | `frontend/widgets.py` (`SessionPicker`), `backend/services/sessions.py` (`msg_count`, `last_message`, `delete_session`) |
| 6 | Ajustes da Fase 1: `[  OK  ]` verde; barras ▰▱ da linha de status em ciano (vermelho no crítico); títulos do Markdown brancos e em negrito; bloco de código com filete ciano e o nome da linguagem no topo; selo de skill colorido (`■ [INTENT] [ OK ]` / `[ FAIL ]` / `[ ▚▚ ]`); véu vermelho no protocolo crítico (o hatch de scanline "furava" a barra do topo) | `frontend/widgets.py` (`StatusLine`, `CodeFence`, `JarvisMarkdown`, `MessageView`), `frontend/jarvis.tcss` |
| 7 | O app passa a procurar seus widgets sempre na tela da conversa (`main_screen`): telemetria e alertas não quebram com uma tela cheia aberta | `frontend/app.py` |

**Decisões:** as telas cheias são `Screen` (não modal) para terem a própria linha de status. Animação de encaixe do cartucho ficou como deslocamento de 1 linha (sem timer). O save slot continua em lista (1 coluna) para manter o filtro por título e a navegação por setas.

**Testes novos:** em `test_tui_app.py`, `/status` (histórico, faixa de carga, `Esc` volta, atalhos da conversa desativados), `/skills` (clique alterna o cartucho), `/log` (filtro WARN e timeline do turno de voz) e save slots (tamanho, prévia, fixar, apagar); `test_sessions_service.py` (`msg_count`, `last_message`, `delete_session`); `test_tui_sprites.py` (`bar_chart`, `load_level`). Espera dos testes de voz subiu para 10 s (rodando a suíte inteira, o turno de voz passava dos 5 s).

---

**Data:** 2026-11-05
**Escopo:** Fase 1 de 4 das novas telas 16-bit: base de sprites/efeitos e as telas atuais harmonizadas com o canvas "JARVIS TUI" (telas 1–4 revisadas).

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | Base de sprites pixel-art (alerta, mini-orb, rosto, armadura, radar com 8 quadros) no mesmo formato do `orb.py`, mais efeitos de texto: barra de blocos `▰▱`, sparkline `▁…█`, quadros do desligamento CRT e revelar por scanline | `frontend/sprites.py` (novo) |
| 2 | Widget `PixelSprite`: pinta qualquer grade em meio-bloco com cores `px--*` do tema; timer a 8 fps só com `animated=True`. Pintura em meio-bloco extraída para `paint_grid`, reaproveitada pela `JarvisOrb` | `frontend/widgets.py`, `frontend/jarvis.tcss` |
| 3 | Linha de status com barras de bloco (`CPU ▰▰▱▱▱ 41%`) e `▚ pensando…` | `frontend/app.py` |
| 4 | Selo de skill estilo cartucho: `▚ [INTENT] executando…` → `■ [INTENT] ✓/✗`; saudação começa com `[  OK  ]` | `frontend/app.py` |
| 5 | Protocolo crítico: ícone de alerta em pixel art, título `AÇÃO CRÍTICA`, contagem regressiva em 30 blocos, scanlines vermelhas atrás do diálogo (`hatch`), borda dupla e `▶` no botão de encerrar | `frontend/widgets.py` (`ConfirmScreen`), `frontend/jarvis.tcss` |
| 6 | Trocar sessão: borda dupla ciano, título em caixa alta, número de slot (`01`, `02`…) e `▶` na sessão atual | `frontend/widgets.py` (`SessionPicker`), `frontend/jarvis.tcss` |
| 7 | Bordas duplas no input, na barra de voz e no painel da orb do Copilot; estado da orb com `▶` | `frontend/jarvis.tcss`, `frontend/widgets.py` (`CopilotHero`) |

**Decisões:** novas cores entram como variáveis `$j-ok`, `$j-warn`, `$j-deep`, `$j-pale`, `$j-scanline`. Sprites ficam em lógica pura (testável) e o widget só mapeia código → cor. Fases seguintes: telas de dados (status, skills, log, save slots), depois vault/config/voz (RMS real) e por fim boot, shutdown CRT e easter egg.

**Testes novos:** `test_tui_sprites.py` (sprites com linhas pares e códigos válidos, recolor, radar com 8 quadros distintos, `block_bar`, `sparkline`, CRT colapsando até 1 ponto, scanline) e, em `test_tui_app.py`, ícone 16×6 e barra de 30 blocos no `ConfirmScreen`, telemetria com barras e `▶ 01` na sessão atual do picker.

---

**Data:** 2026-11-04
**Escopo:** Copilot passa a ser **só por voz**, com orb pixel-art 16×16 (ouvindo / pensando / respondendo); telemetria e atalhos numa **linha só**. Segue a revisão do canvas "JARVIS TUI".

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | Copilot só voz: o input dá lugar à barra de voz; entrar no Copilot liga a voz, voltar ao Chat desliga. `Ctrl+T`/`/voice` alternam entre Chat e Copilot | `frontend/app.py`, `frontend/widgets.py` (`VoiceBar`) |
| 2 | Voz usa o mesmo pipeline de stream do Copilot (`_run_turn`): selo `[SKILL] ✓`, resposta em tempo real, fala no fim. Grava na sessão atual (aparece no `Ctrl+O`), com cabeçalho `voz · HH:MM` | `frontend/app.py` |
| 3 | Orb pixel-art: grade 16×16 em meio-bloco (16×8 células). Ouvindo = bola azul + anel branco parado; pensando = tudo branco pulsando em degraus; respondendo = falha percorrendo o anel. Timer só roda nos estados animados | `frontend/orb.py` (novo), `frontend/widgets.py` (`JarvisOrb`, `CopilotHero`), `frontend/jarvis.tcss` |
| 4 | Rodapé em 1 linha: `Footer` dentro do `#statusbar` (telemetria à esquerda, atalhos à direita); `^t` some no Copilot; `Sair` volta a ser o último | `frontend/app.py`, `frontend/jarvis.tcss` |
| 5 | Protocolo crítico: a classe `-critical` agora vai para a tela da conversa (antes caía no modal se ele já estivesse aberto); modal tem a mesma linha única com `s`/`n` e foca "Manter"; barra de voz pede "sim" ou "não" | `frontend/app.py`, `frontend/widgets.py`, `frontend/jarvis.tcss` |
| 6 | Voz injetável (`JarvisApp(voice=...)`) e loop de voz encerra junto com o app | `frontend/app.py` |

**Decisões:** comandos `/` só existem no Chat (no Copilot não há campo de texto). "Ouvindo" cobre todo o tempo com o microfone aberto: o `listen()` não avisa quando a fala começa.

**Testes novos:** `test_tui_orb.py` (grade 16×16 simétrica, pensando só branco e pulsando, falha do anel percorre os 8 oitavos, meio-bloco 16×8) e, em `test_tui_app.py`, Copilot só voz, `Ctrl+T`, turno de voz completo (stream + selo + fala + sessão), orb pensando até a 1ª saída, rodapé em 1 linha e crítico com modal aberto.

---

**Data:** 2026-11-03
**Escopo:** Interface trocada por uma TUI de terminal (Textual), na nova pasta `frontend/` (pacote Python). Frontend React/PyWebView removido. Modos **Chat** e **Copilot** alternados com `Shift+Tab`; voz opcional. Visual segue o canvas de design "JARVIS TUI".

---

## Resumo

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | TUI Textual: chat em Markdown com streaming, sessões, anexos, telemetria em 1 linha, alertas | `frontend/app.py`, `frontend/widgets.py`, `frontend/commands.py`, `frontend/jarvis.tcss` (novos), `backend/main.py` |
| 2 | Modos Chat (sem skills) e Copilot (skills + confirmação de ação crítica) | `services/brain.py`, `services/chat.py`, `prompts/mode_chat.md`, `prompts/mode_copilot.md` (novos) |
| 3 | Voz opcional e lazy: mic/pyttsx3/pygame só abrem com `/voice` | `services/listen.py`, `services/speak.py`, `core/alerts.py`, `core/state.py` |
| 4 | SQL de sessões e toggles de skills saíram da bridge | `services/sessions.py`, `services/skill_settings.py` (novos) |
| 5 | Logger não escreve no stdout com a TUI ativa | `core/logger.py` |
| 6 | Remoção do HUD: React/Vite em `frontend/`, `core/bridge.py`, `escape_js`, `pywebview` | `core/__init__.py`, `core/utils.py`, `core/uploads.py`, `requirements.txt`, CI, dependabot |
| 7 | `frontend/` reaproveitada para a TUI + design aprovado aplicado | `frontend/*`, `services/brain.py` (`on_route`), `services/sessions.py` (hora local), `backend/tests/__init__.py`, `pyproject.toml` |

---

## 7. Pasta `frontend/` e design aplicado

**Pasta:** a TUI saiu de `backend/tui/` para `frontend/` na raiz, como pacote Python `frontend`. `backend/main.py` põe a raiz no `sys.path` e importa `frontend.app`; `boot.bat` não muda. `backend/tests/__init__.py` faz o mesmo para os testes. `frontend/pyproject.toml` herda o ruff do backend (com `known-first-party` para `core`, `services`, `frontend`...), e o CI passou a rodar `ruff check ../frontend` e `compileall` nela.

**Design (canvas "JARVIS TUI"):**
- Barra superior em 4 partes: marca, selo do modo (CHAT branco / COPILOT escuro sobre ciano), título da sessão e info à direita: "sessão N de M" no Chat, "skills ativas: N" no Copilot, "⚠ PROTOCOLO CRÍTICO" no estado crítico.
- Cabeçalhos com hora (`você › 14:02`); no Copilot a resposta ganha o selo da skill: `[AUDIO_CONTROL] executando…` → `✓` (ou `✗` em erro). Para isso `execute_command_stream` ganhou `on_route(intent)`, chamado quando a mensagem vira skill.
- Paleta revisada para contraste (cinza `#8593ab`, azul do usuário `#6aa8ff`), barra de status dividida (telemetria à esquerda, dica à direita) e footer com teclas em ciano.
- **Trocar sessão:** campo de filtro por título (Enter abre o primeiro, ↓ vai para a lista), `●` atual, `★` fixada e coluna de quando (`HH:MM`, `ontem`, `dd/mm`).
- **Confirmação crítica:** botões reais `s · Encerrar` / `n · Manter` e contagem "Expira em N s"; sem resposta, fecha como "não" no prazo da ação.

**Bugs corrigidos no caminho:**
- O badge `[APP_CONTROL]` sumia do cabeçalho: o markup do Textual lê colchetes em MAIÚSCULAS como tag e o `escape` dele não cobre esse caso. O cabeçalho agora é montado com `Content.assemble`.
- Horários vinham em UTC (o SQLite grava `CURRENT_TIMESTAMP` em UTC): `sessions.to_local()` converte para a hora local no histórico e na lista de sessões.

**Testes novos:** selo da skill no Copilot (e ausência no Chat), barra superior (selo, "sessão N de M", "skills ativas", crítico), filtro do seletor de sessões, confirmação que expira como "não" e que aceita `s`, `format_when`, `to_local`.

---

## 1. TUI (Textual)

**Por quê:** o HUD (React 19 + Three.js + Framer Motion dentro do WebView2) pesava demais em RAM/GPU. A TUI roda no próprio terminal, 100% Python.

**Layout:** barra superior (modo + título da sessão + aviso crítico), log de mensagens (JARVIS em Markdown), barra de anexo, input, barra de status (CPU/RAM/GPU, voz, modelo) e footer com atalhos.

**Atalhos:** `Shift+Tab` modo · `Ctrl+N` nova sessão · `Ctrl+O` sessões · `Ctrl+R` regenerar · `Ctrl+T` voz · `Esc` interrompe o stream · `↑` (input vazio) edita a última mensagem · `Ctrl+Q` sair.

**Comandos:** `/help`, `/new`, `/sessions`, `/rename`, `/pin`, `/regen`, `/edit`, `/attach <caminho>`, `/detach`, `/mode`, `/voice`, `/skills [on|off X]`, `/clear`, `/quit`. `//texto` envia mensagem começando com barra.

**Streaming:** worker em thread consome `execute_command_stream` e re-renderiza a bolha no máximo a cada 50 ms. Histórico salvo no SQLite igual ao HUD antigo (sessões antigas continuam abrindo).

**Anexos:** `/attach` de imagem vai junto com a próxima mensagem (modelo de visão); áudio é transcrito pelo Whisper e cai no input, como no HUD.

**Telemetria:** polling a cada 3 s (`TELEMETRY_INTERVAL`) numa linha — sai o stream push delta-gated da bridge.

**Fora do escopo:** KaTeX (o terminal mostra LaTeX em bloco de código), reator animado, legendas.

## 2. Modos Chat e Copilot

- `execute_command_stream(..., mode="chat"|"copilot")`. **Chat** classifica com `skip_skills=True` e nunca executa skill (antes o chat do HUD executava skills sem querer). **Copilot** libera as skills.
- Prompt do modo saiu de string Python para `prompts/mode_chat.md` / `prompts/mode_copilot.md`.
- Ação crítica (ex: matar processo pesado) abre um modal `s/n` na TUI → `brain.confirm_pending_action()`. A lógica duplicada de confirmação em `execute_command`/`execute_command_stream` virou uma função só.

## 3. Voz opcional e lazy

- `state.voice_enabled` (começa `False`). `/voice` ou `Ctrl+T` liga o loop de voz antigo do `main.py`, agora numa thread daemon que espelha transcrição e resposta no log.
- `services/listen.py`: `Ear()` não é mais criado no import (`get_ear()` lazy); `ear_pause/resume` são no-op sem ouvido.
- `services/speak.py`: pyttsx3/pygame/edge-tts inicializados na 1ª fala; `speak()` só exibe o texto (via `state.announce`) quando a voz está desligada. Removido `typewriter_effect` (escrevia no stdout e corromperia a TUI).
- `core/alerts.py` e `services/brain.py`: import tardio dos sentidos; `scan_system_hardware()` saiu do import do brain e roda em thread no boot.

## 4–5. Serviços extraídos e logger

- `services/sessions.py`: histórico, editar/regenerar, título, pin e sessões recentes (todas as conexões fecham em `finally`).
- `services/skill_settings.py`: listar e ligar/desligar skills/categorias.
- `core/logger.py`: `log.use_tui(handler)` remove o handler de console; WARNING+ vira notificação na TUI; arquivo de log continua.

## 6. Removido

O app React/Vite inteiro de `frontend/` (a pasta agora guarda a TUI), `core/bridge.py` (+ `docs/core/bridge.md`), `core.utils.escape_js` (+ `tests/test_utils.py`), `read_upload_as_data_url`, `pywebview` do `requirements.txt`, stub `webview` dos testes, job `frontend` do CI e o bloco npm do dependabot. Settings `TELEMETRY_*_DELTA` removidos.

## Testes

- Novos: `test_tui_app.py` (Pilot: Shift+Tab, stream + log no banco, Copilot, `/new` e `Ctrl+N`, regenerar, comando desconhecido), `test_tui_commands.py`, `test_mode_routing.py`, `test_sessions_service.py`, `test_lazy_imports.py`.
- `test_alerts_cache.py` passou a mockar `alerts._announce`.
- Resultado: **152 passam**; 11 falhas em `test_work_macros_spotify.py` já existiam antes desta mudança (funções `_sanitize_spotify_uri`/`_is_playing_title` ausentes) — por isso o `pytest` segue comentado no CI. `ruff check` limpo em `backend/` e `frontend/`.
- **Não medido:** consumo de RAM/CPU antes × depois. **Não testado ao vivo:** voz, Ollama real e skills reais na TUI (testes usam stream fake).

---

## Mudança anterior

**Data:** 2026-09-28
**Escopo:** Multimodalidade no Chat Mode — upload de imagem (análise via modelo de visão local) e upload de áudio (transcrição local via Whisper).

---

## Resumo

| # | Feature | Arquivos |
|---|---------|----------|
| 1 | Upload de imagem no chat → resposta via modelo de visão Ollama (Moondream) | `core/config.py`, `core/llm.py`, `services/chat.py`, `services/brain.py`, `core/bridge.py`, `core/database.py`, `core/uploads.py` (novo), `prompts/vision_context.md` (novo) |
| 2 | Upload de áudio no chat → transcrição local via faster-whisper, preenchendo a caixa de texto | `core/config.py`, `core/transcription.py` (novo), `core/uploads.py` (novo), `core/bridge.py` |
| 3 | Frontend: anexar/arrastar imagem ou áudio, preview real de imagem, botão de clipe único | `ChatInput.jsx`, `ChatPanel.jsx`, `MessageList.jsx`, `AttachmentPreview.jsx` (novo), `BridgeAPI.js` |

---

## 1. Upload de imagem — análise via modelo de visão

**O quê:** usuário anexa/arrasta uma imagem no Chat Mode e faz uma pergunta sobre ela (ex: "o que é isso?", "descreve o erro nessa screenshot"). A resposta é gerada por um modelo de visão local via Ollama (**Moondream** por padrão, configurável) e streamada na UI exatamente como uma resposta de texto normal.

**Backend:**
- `core/config.py`: novos settings `OLLAMA_VISION_MODEL` (default `moondream`), `OLLAMA_VISION_KEEP_ALIVE` (default `5m` — não fica residente na VRAM como o modelo de chat principal), `TIMEOUT_VISION`, `DIR_UPLOADS`, `MAX_UPLOAD_SIZE_MB`, `ALLOWED_IMAGE_MIME`/`ALLOWED_AUDIO_MIME`.
- `core/llm.py`: `query_ollama`/`query_ollama_stream` ganharam `model=` e `keep_alive=` opcionais (default preserva comportamento atual).
- `core/uploads.py` (novo): `save_base64_upload()` valida mime/tamanho e grava o anexo em `backend/uploads/<kind>/`; `read_upload_as_data_url()` relê um anexo salvo pra reconstruir preview ao reabrir sessão antiga.
- `prompts/vision_context.md` (novo): instrução curta e dedicada pro modelo de visão — não reusa o system prompt completo do JARVIS (personalidade/telemetria/histórico), já que modelos pequenos como Moondream degradam com contexto irrelevante.
- `services/chat.py`: `ask_local_ai_stream()` ganhou parâmetro `images=None`; quando presente, monta uma lista de mensagens mínima (`vision_context.md` + pergunta + imagem) e chama `query_ollama_stream(model=OLLAMA_VISION_MODEL, keep_alive=OLLAMA_VISION_KEEP_ALIVE)`.
- `services/brain.py`: `execute_command_stream()` ganhou passthrough `images=None`.
- `core/bridge.py`: `chat_message(text, session_id, images=None)` — salva a(s) imagem(ns) recebida(s) (base64) em disco, loga a interação com referência ao anexo, e repassa pro pipeline de streaming existente (zero mudança no lado de recebimento do frontend).
- `core/database.py`: tabela `history` ganhou colunas `attachment_type`/`attachment_path` (migração automática via `PRAGMA table_info` + `ALTER TABLE`, retrocompatível com bancos existentes). `get_chat_history` (bridge.py) relê imagens do disco como data URL pra reconstruir o preview ao reabrir uma sessão.

**Frontend:**
- `ChatPanel.jsx`: `handleFileChange` reescrito como `processFiles()` — agora lê o `File` de verdade via `FileReader` (base64), em vez de descartá-lo (comportamento anterior só guardava nome/ícone). `handleSend` monta o payload de imagem e chama `chat_message(text, sessionId, imagePayload)`.
- `ChatInput.jsx`: `accept="image/*,audio/*"` no input de arquivo; adicionado drag-and-drop na área do input (spring transition, sem duplicar lógica — reusa `processFiles`).
- `MessageList.jsx` / `AttachmentPreview.jsx` (novo): imagens anexadas agora renderizam thumbnail real (`<img>`) na bolha da mensagem, não só um chip com nome de arquivo.

---

## 2. Upload de áudio — transcrição local via Whisper

**O quê:** usuário anexa um arquivo de áudio no chat. Ao enviar, o áudio **sempre** intercepta o envio (mesmo com texto já digitado) e é transcrito localmente via **faster-whisper** (modelo `base`, PT-BR). O texto preenche a caixa de input — **não é enviado automaticamente**, o usuário revisa e aperta Enviar.

**Backend:**
- `core/config.py`: `WHISPER_MODEL_SIZE` (default `base`), `WHISPER_DEVICE` (`auto`/`cpu`/`cuda`), `WHISPER_COMPUTE_TYPE` (`int8`), `TIMEOUT_TRANSCRIPTION`.
- `core/transcription.py` (novo): `transcribe_audio_file()` — singleton lazy do `WhisperModel` (carrega só na 1ª transcrição, não trava o boot).
- `core/bridge.py`: novo método `transcribe_audio(audio_b64, mime_type, filename)` — síncrono do ponto de vista do frontend (`await callApi(...)`), roda a transcrição numa thread própria com `.join()` internamente (segue a convenção do projeto de I/O pesado rodar em thread). Retorna `{"success": bool, "text"/"error": ...}`. Não loga no histórico nem passa pelo LLM — é uma ação isolada de transcrição.

**Frontend:**
- `ChatPanel.jsx`: `handleSend` — qualquer arquivo de áudio anexado sempre dispara `transcribe_audio(...)` em vez de `chat_message(...)`; resultado é concatenado no `inputValue`.
- `BridgeAPI.js`: mock fallback pra `transcribe_audio` (modo browser-dev sem pywebview).

---

## Dependências novas

`backend/requirements.txt`: `faster-whisper`, `Pillow`.

**Passos manuais necessários antes de testar:**
```bash
ollama pull moondream
cd backend && pip install -r requirements.txt
```

---

## Limitações conhecidas / follow-ups não implementados

- Sem OCR dedicado (Tesseract) — decisão explícita do usuário, só modelo de visão puro (Moondream).
- Envio de múltiplas imagens numa mesma mensagem: só a primeira é persistida com `attachment_path` no histórico (todas são enviadas ao modelo de visão, mas só uma fica referenciada pra preview ao reabrir sessão).
- Sem pré-aviso de "modelo de visão não baixado" — se `ollama pull moondream` nunca rodou, o erro cai no tratamento genérico já existente (`query_ollama_stream`).
- Sem redimensionamento client-side de imagens grandes antes do envio (mitigado por `MAX_UPLOAD_SIZE_MB=15` no backend).

---

# Otimização de performance do frontend — Fase 1: streaming do chat

**Data:** 2026-09-29
**Escopo:** reduzir re-renders e re-parse de markdown/KaTeX durante o streaming de respostas no Chat Mode.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `MessageItem` com `React.memo`; `MarkdownBody` memoizado por texto; plugins do ReactMarkdown como constantes de módulo | `CHAT/MessageList.jsx` |
| 2 | Chunks do stream acumulados num buffer e aplicados 1x por frame (`requestAnimationFrame`); `isDone` faz flush síncrono | `ChatPanel.jsx` |
| 3 | Scroll `auto` durante o streaming (antes: um `smooth` novo por chunk) | `CHAT/MessageList.jsx` |
| 4 | Handlers de editar/regenerar estáveis (leem `messagesRef`), não trocam identidade a cada chunk | `ChatPanel.jsx` |
| 5 | Último-mensagem-do-usuário por loop reverso em `useMemo` (antes: cópia + reverse do array a cada render) | `CHAT/MessageList.jsx` |
| 6 | `JarvisPixelAvatar` memoizado; `animate-pulse` só fora de `idle` (avatares de mensagens antigas ficam estáticos) | `CHAT/JarvisPixelAvatar.jsx` |
| 7 | App passa `hasMessages` (boolean) ao orb em vez de ler `chatMessages.length` várias vezes; `console.log` removido dos listeners quentes (`receiveStatus`, `updateHudState`) | `App.jsx` |
| 8 | Vitest + Testing Library (dev): testes de batching do stream, flush no `isDone`, markdown e scroll | `vite.config.js`, `package.json`, `components/__tests__/chatStreaming.test.jsx` |

**Decisão:** `chatMessages` permanece no `App` (não foi movido para o `ChatPanel`) porque o histórico precisa sobreviver à troca de modo — `ChatPanel` desmonta em talk/code.

**Como testar:** `cd frontend && npm test && npm run lint && npm run build`.

---

# Simplificação da interface e redução de RAM — Fase 2

**Data:** 2026-09-29
**Escopo:** remover a tela CODE e dependências mortas, achatar a UI (sem blur) e deixar o chat minimalista.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | **Removido o modo CODE** e a tela de seleção de modo (boot entra direto em `talk`; troca só pelo header Copilot/Chat) | `App.jsx`, `HeaderNavigation.jsx`, `CORE/NavIcons.jsx`; removidos `CodePanel`, `CODE/*`, `JarvisPixelReactor`, `ModeSelectionScreen` |
| 2 | **Removidas deps sem uso:** `@react-three/postprocessing`, `animejs`, `path`, `@tailwindcss/postcss` | `package.json` |
| 3 | **Orb reescrito:** 1 canvas (antes 2 + `mix-blend-screen`), 140 partículas (antes 320), sem linhas de conexão, sem `blur(60px)`, sem lente com `backdrop-filter`, 10fps em idle / 30fps ativo, pausa com a janela oculta, DPR limitado a 2, `React.memo` | `LiquidAuraReactor.jsx`; removido `ReactorCoreLens` |
| 4 | **Zero `backdrop-filter`** no app (havia ~20 camadas, incluindo a janela inteira) | `App.jsx`, `index.css`, `SkillsSidebar`, `JarvisSubtitles`, `LiveTelemetry`, `StartupScreen`, header, chat |
| 5 | **Chat simplão:** sem avatar, sem bolha do Jarvis (texto direto), bolha simples do usuário, ações em texto (Copiar/Editar/Regenerar), "Pensando…" em vez de bolha animada, input e sidebar chapados | `CHAT/MessageList.jsx`, `ChatInput.jsx`, `ChatSidebar.jsx`, `ChatPanel.jsx`; removido `JarvisPixelAvatar` |
| 6 | `ChatPanel` (markdown + KaTeX) carregado sob demanda com `React.lazy`; `manualChunks` com match exato (antes `includes('react')` puxava react-markdown e lucide) | `App.jsx`, `vite.config.js` |
| 7 | CSS: removidos `@import` do Google Fonts (fonte do sistema, funciona offline), scanline/glitch/tech-grid sem uso, `App.css` órfão; `.hud-critical-mode` anima só `opacity` | `index.css` |
| 8 | CLAUDE.md atualizado: sem modo `code`; Lei 2 agora proíbe `backdrop-filter` | `CLAUDE.md` |

**Bundle (JS carregado no startup):** ~870KB → ~380KB (index 34KB + framer 136KB + react 211KB). O chat (449KB) só carrega ao abrir o modo Chat.

**Observação de RAM:** não foi medida com profiler. As mudanças atacam as maiores fontes prováveis de memória no WebView2 (superfícies de compositing de `backdrop-filter`, canvases com blend, camadas com blur). Comparar antes/depois no Gerenciador de Tarefas (processos `msedgewebview2`).

---

# Ollama: opções de VRAM (`num_ctx` / `num_gpu`) com fallback

**Data:** 2026-09-29
**Escopo:** permitir empurrar o modelo para a VRAM sem risco de derrubar o chat.

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | Novas settings opcionais `OLLAMA_NUM_CTX` e `OLLAMA_NUM_GPU` (vazio = não repassa; comportamento atual preservado). `0` é respeitado (tudo na CPU) | `core/config.py` |
| 2 | `_build_options()` centraliza `options`; `query_ollama`, `query_ollama_stream` e `warm_up_ollama` usam as mesmas opções (evita reload do modelo por opções divergentes) | `core/llm.py` |
| 3 | **Fallback:** se o Ollama recusar `num_gpu` (VRAM insuficiente), a opção é desativada para o processo todo e a chamada repete 1x sem ela. No stream, só repete se nada foi emitido ainda | `core/llm.py` |
| 4 | Testes: opções padrão/configuradas, `num_gpu=0`, fallback normal e stream, sem retry após saída parcial | `tests/test_llm_options.py` |

**Não incluído (a discutir):** as 7 skills que chamam `/api/generate` direto via `requests` (sem `keep_alive`/`options`) ainda não usam essas opções. Enquanto isso, se `OLLAMA_NUM_CTX`/`OLLAMA_NUM_GPU` forem ativados, uma chamada de skill pode causar reload do modelo por divergência de opções.

**Servidor (variáveis do Windows, reiniciar o Ollama):** `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_FLASH_ATTENTION=1`.
