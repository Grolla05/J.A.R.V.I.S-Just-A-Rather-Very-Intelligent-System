# CHANGES.md

Registro das mudanças aplicadas no J.A.R.V.I.S.

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
