# TUI — regras e convenções

Regras da interface (Textual, pacote `frontend/`). Leia antes de alterar `frontend/`. Resumo do projeto em [`AGENTS.md`](../AGENTS.md); alertas em [`alertas.md`](alertas.md); agente residente em [`agente-residente.md`](agente-residente.md).

## Modos (`JarvisApp.mode`)

| Modo | Atalho | O que faz |
|------|--------|-----------|
| `chat` | `Shift+Tab` | Conversa **por texto** com o LLM em Markdown. Skills **nunca** executam. Voz desligada |
| `copilot` | `Shift+Tab` / `Ctrl+T` | Agente **só por voz**: input e conversa dão lugar à `VoiceStage` (espectro + orb + fala + VU em dB, como no canvas); mesmo pipeline com skills liberadas + confirmação de ação crítica (`ConfirmScreen`) |

O modo vai para `execute_command_stream(..., mode=)` e escolhe o prompt `mode_chat.md` / `mode_copilot.md`. Entrar no Copilot liga a voz; voltar ao Chat desliga. O loop de voz (`_voice_loop`) usa o **mesmo** `_run_turn` do Chat (stream + selo da skill) e fala a resposta no fim; grava na sessão atual. Comandos `/` só existem no Chat.

## Atalhos e comandos

- `Shift+Tab` modo · `Ctrl+N` nova sessão · `Ctrl+O` sessões · `Ctrl+R` regenerar · `Ctrl+T` vai para o Copilot (voz) — some do rodapé dentro dele · `Esc` cancela a edição → interrompe o stream → sem nada em andamento, sai (CRT; Esc de novo sai já) — fora do rodapé · `↑` com input vazio edita a última mensagem · `Ctrl+K` paleta (`/menu`; binding com `priority=True` porque o `Input` usa Ctrl+K) · `Win+J` (global, via `agent.py`) abre/foca a TUI no Copilot · `Ctrl+Alt+T` (global, `TRANSLATE_HOTKEY`) traduz o texto selecionado em qualquer app (toast da bandeja + clipboard) · `Ctrl+Alt+E` (global, `EXPLAIN_HOTKEY`) explica o código/erro selecionado em qualquer app dentro do Chat (abre a TUI se estiver fechada; o clipboard anterior é devolvido)
- Telemetria e atalhos dividem **uma** linha: o `Footer` vive dentro do `#statusbar` (classe `.statusbar`); o `ConfirmScreen` tem a sua própria linha igual (o Footer só enxerga a Screen dele)
- `JarvisApp` usa `inherit_bindings=False` para "Sair" ficar no fim do rodapé — não volte a herdar sem reordenar
- Telas cheias: `/status` (dashboard), `/skills` (cartuchos), `/log` (buffer do logger + timeline do último turno com skill), `/vault` (Obsidian; "usar no chat" manda a nota como contexto via `prompts/vault_note_context.md`), `/config` (preferências em `services/user_prefs.py`; cada grupo é montado em cards de seção a partir de `screens/settings_rows.py` (`SECTIONS`, rótulos curtos, ajuda ↳ da linha em foco; `PrefRow` com selo ● ON/○ OFF para liga/desliga e pontos de posição nas escolhas; preferência nova entra numa `Section` e no `HELP`); a fala do JARVIS é a `QuipLine` `#cfg-quip` (digitando) na faixa `#cfg-quip-box` do pé — sem caixa de diálogo; animações só por evento (cards entram um a um na troca de grupo, valor novo pisca); SISTEMA tem o campo "Fontes de notícias" com botão Salvar → `core/news.py`; INTEGRAÇÕES = cards de `services/integrations.py`: Enter conecta em worker de thread, card fica AGUARDANDO, Del desconecta com `ConfirmScreen`). Nova integração = uma entrada em `integrations._build()` com `status()`/`connect()`/`disconnect()` que devolvem texto e nunca levantam. Boot: `JarvisApp(boot_fn=core.boot.run_boot)`; `Esc` na conversa toca o CRT (`Esc` de novo sai já). Labels com `[  OK  ]` precisam de `markup=False`. `JarvisScreen._merge_bindings` põe `esc Voltar` no fim do rodapé, como no canvas. Dentro delas os atalhos da conversa ficam desativados; widgets da conversa são sempre buscados em `app.main_screen`
- Não existe `/help`: a paleta `Ctrl+K` lista os comandos (`/`, `/help`, `/h` e `/?` abrem a paleta). `frontend/commands.py` é a fonte única — novo comando entra em `COMMANDS` e em `JarvisApp.run_command`
- `//texto` envia uma mensagem que começa com `/`
- Explicar (`JarvisApp.explain_snippet`): o trecho vira um turno normal do Chat (fica na sessão → dá para continuar perguntando) e vai ao modelo com `force_chat=True` — `execute_command_stream` pula classificador, vault e ação pendente, porque o conteúdo de um trecho nunca pode virar skill nem um "ok" de confirmação. Prompts `explain_code.md` / `explain_error.md` (stack trace → causa, onde olhar, correção, como confirmar). Chegam por ali: o atalho global (agente → `presence.write_explain` + evento `EXPLAIN`; `_take_explain` no sinal e no fim do boot) e `/clip explicar [n]`
- `/clip`: sem argumento age sobre o clipboard atual; `hist` lista o histórico persistente (numerado), `buscar <termo>`, `usar <n>` recopia, `<ação> <n>` age sobre um item, `limpar` apaga (com `ConfirmScreen`). O histórico só enche com o **Monitor de clipboard** ligado e nunca guarda o que tem cara de senha/token (`clip_history.looks_secret`)
- `/ideia <texto>` anota em 🧠 Brainstorms; `/lembrete [<quando> <assunto> | rm <n>]` cria/lista/remove lembretes; `/rede [confiar <n> | bloquear <ip> | mantidos | esquecer <n> | reset]` varre o perímetro (bloquear, esquecer e reset pedem `ConfirmScreen`)
- `/email [ler <n> | responder <n> <texto> | novo <para> <texto> | apagar <n…|promoções> | organizar | vip <e-mail> | contato <apelido> <e-mail> | assinatura <texto>]`: envio, Lixeira e organização sempre mostram rascunho/lista/plano e abrem `ConfirmScreen` (não = rascunho no Gmail; apagar = Lixeira, recuperável por 30 dias). `/instalar <programa>` e `/baixar <programa>`: winget com confirmação. Ferramenta (`tool_reply`) que arma pendência local abre o `ConfirmScreen` sozinha
- Rotinas em segundo plano (só com `start_services`): lembretes num `set_interval(REMINDER_INTERVAL)` próprio (agenda é HTTP: nunca no tick da telemetria) → `reminders.collect()` em worker de thread → `_deliver_reminder` (aviso comum respeita o silêncio e vai ao backlog; `urgent` sempre aparece, sem voz no silêncio); insights no fim de um turno de conversa sem skill (`_insight_fn`, worker `exclusive`); vigia de rede (`core.netwatch.NetworkWatch`, pref `net_monitor`). Testes injetam `app._insight_fn` e fazem patch de `reminders.collect`
- Arrastar arquivo para o terminal = `/attach`: o Windows Terminal cola o caminho; `PromptInput._on_paste` usa `commands.dropped_paths()` (só quando **todo** o texto é caminho absoluto de arquivo existente, de qualquer tipo) e emite `FilesDropped`. Texto, código e PDF (até 3) vão junto da próxima mensagem como contexto (`core/uploads.load_document`, `prompts/file_context.md`, `force_chat` — nunca viram skill). Não chame `super()._on_paste` — o Textual já roda o handler do `Input` pelo MRO (colaria 2×)
- Linha de status: telemetria (com `⚡ NNNW` do consumo, `core/power.py`) · selo de foco (`◷ FOCO 24m 1/4` / `☾ DND` / `[SILENT]`, resolução de minutos, sem timer próprio) · voz. Sem modelo (fica no `/config` → MODELO) e sem "Sair" no rodapé. A saúde (`core.health`, a cada `HEALTH_INTERVAL`, só depois do boot) não aparece no rodapé: fica no `/status` e falha nova vira notificação
- PortAudio não é thread-safe: enumerar o microfone só via `health.check_microphone()` (lock + cache). Crash nativo grava stack em `logs/crash.log` (faulthandler no `main.py`)
- Logo na aba: `core/wt_profile.py` grava o fragment do perfil `JARVIS` do Windows Terminal; launcher e `jarvis.cmd` abrem com `-p JARVIS`
- Paleta: entradas e busca fuzzy são lógica pura em `frontend/commands.py` (`palette_entries`, `filter_entries`); comandos que exigem argumento (`NEEDS_ARG`) só preenchem o input

## Comandos `/`

Lista tirada de `COMMANDS` em `frontend/commands.py` (a fonte única; a paleta `Ctrl+K` mostra a mesma). `//texto` envia uma mensagem que começa com `/`.

| Comando | Faz |
|---|---|
| `/menu` | paleta de comandos, skills e foco (Ctrl+K) |
| `/new` | nova sessão (Ctrl+N) |
| `/sessions` | trocar de sessão (Ctrl+O) |
| `/rename <título>` | renomeia a sessão atual |
| `/pin` | fixa/desafixa a sessão atual |
| `/regen` | regenera a última resposta (Ctrl+R) |
| `/edit` | edita a última mensagem e reenvia (↑ com input vazio) |
| `/attach <caminho>` | imagem → modelo de visão; áudio → transcreve; texto/código/PDF → vai junto da mensagem |
| `/detach` | remove os anexos pendentes |
| `/mode [chat\|copilot]` | troca o modo (Shift+Tab) |
| `/voice` | liga/desliga wake word + voz (Ctrl+T) |
| `/skills [on\|off <skill\|categoria>]` | cartuchos das skills (ou alterna direto) |
| `/status` | dashboard do sistema: CPU, RAM, GPU, rede e processos |
| `/log` | log de atividade com filtros e o último turno do Copilot |
| `/vault [termo]` | memória no Obsidian: árvore, busca e nota no chat |
| `/web <pergunta>` | pesquisa na internet e resume com fontes |
| `/gh [prs\|issues\|commit\|ci] [dono/repo]` | GitHub: PRs, issues, último commit e CI |
| `/briefing` | briefing do dia: clima, agenda, trânsito, máquina e GitHub |
| `/rota [<local> <endereço>]` | cadastra um local fixo (casa, trabalho, faculdade…); sem argumento lista |
| `/clip [explicar\|traduzir\|resumir] [n] · hist · buscar <termo> · usar <n> · limpar` | age sobre o que você copiou ou sobre o histórico (monitor no /config) |
| `/email [ler <n> \| responder <n> <texto> \| novo <para> <texto> \| apagar <n…\|promoções> \| organizar \| vip <e-mail> \| contato <apelido> <e-mail> \| assinatura <texto>]` | Gmail: e-mails por prioridade, ler, responder, escrever e organizar (envio sempre confirmado) |
| `/instalar <programa>` | procura no winget e instala (pede confirmação) |
| `/baixar <programa>` | baixa o instalador pelo winget para Downloads (pede confirmação) |
| `/ideia <texto>` | anota uma ideia em 🧠 Brainstorms no Obsidian (a conversa também registra sozinha) |
| `/lembrete [<quando> <assunto> \| rm <n>]` | lembrete com horário (em 30 min…, às 18h…); sem argumento lista os pendentes |
| `/rede [confiar <n> \| bloquear <ip> \| mantidos \| esquecer <n> \| reset]` | perímetro de rede: aparelhos, portas expostas e programas na internet (vigia no /config) |
| `/focus [min\|stop\|skip\|status]` | pomodoro 25/5 (liga o Não Perturbe no foco) |
| `/dnd [on\|off\|min]` | Não Perturbe: silencia notificações do Windows e alertas |
| `/silent [on\|off]` | Modo Apresentação: mic fechado, voz muda e alertas guardados |
| `/config` | ajustes de voz, microfone e rotinas (menu estilo RPG) |
| `/clear` | limpa a tela (não apaga o histórico) |
| `/quit` | encerra o J.A.R.V.I.S (Esc) |

## Visual

- **Cores só no `frontend/jarvis.tcss`**, como variáveis `$j-*` (prefixo evita sobrescrever variáveis do tema do Textual, como `$panel`)
- Estado crítico → classe `-critical` na tela da conversa (`app.main_screen`, nunca `self.screen`, que pode ser um modal); Copilot → classe `-copilot` (ciano neon)
- Nada de animação contínua: a telemetria é polling a cada `TELEMETRY_INTERVAL` (3 s) numa linha de status. **Única exceção:** a orb do Copilot (`JarvisOrb`, 8 fps) anima só nos estados `pensando`/`respondendo`; em `ouvindo` o timer é parado
- Orb pixel-art: quadros em `frontend/orb.py` (lógica pura, testada); cores via component classes `orb--*` no `jarvis.tcss`
- Streaming re-renderiza o Markdown no máximo a cada 50 ms (`STREAM_FLUSH_S`)

## Badge de skill (Copilot)

- `execute_command_stream(..., on_route=fn)` chama `fn(intent)` quando a mensagem vira skill; a TUI mostra `[INTENT] executando…` → `✓`/`✗` no cabeçalho da resposta
- Cabeçalhos são montados com `Content.assemble`, nunca markup: o Textual lê `[MAIÚSCULAS]` como tag e apaga o badge
- Horários do SQLite estão em UTC: sempre passar por `sessions.to_local()`  antes de mostrar

## Testes da TUI

Testes da TUI ficam em `backend/tests/` (`test_tui_app.py`, `test_tui_commands.py`, `test_tui_orb.py`) e usam `App.run_test()` + Pilot, com `stream_fn` fake, `voice=FakeVoice(...)` e `start_services=False` — sem Ollama, microfone nem hardware. O `tearDown` zera `state.voice_enabled`. `tests/__init__.py` põe a raiz no `sys.path` para importar `frontend`. Lint: `ruff check .` em `backend/` **e** em `frontend/`. Com `NO_COLOR` definido o Textual desenha em cinza.
