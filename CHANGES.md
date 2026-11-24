# CHANGES.md

Registro das mudanças aplicadas no J.A.R.V.I.S.

## Vigilância Cibernética: JARVIS como administrador, bloqueio de entrada e saída e automático

**Data:** 2026-11-24
**Escopo:** Item "Vigilância Cibernética — bloqueio de acessos suspeitos" do Brainstorm. Antes, `/rede bloquear <ip>` criava só regra de **saída** e só funcionava com o JARVIS elevado (que nunca estava).

### JARVIS sempre como administrador, sem UAC a cada abertura

- **`backend/core/elevation.py`** (novo): cria por XML duas tarefas agendadas com "privilégios mais altos": `\JARVIS\Agente` (no logon **só deste usuário**, sessão interativa, sem o limite de 72 h do Agendador) e `\JARVIS\TUI` (sob demanda, só instalado). O agente elevado abre a TUI e a ponte já elevadas. Com a tarefa, o valor `JARVIS` do `HKCU\…\Run` sai (senão subiriam dois agentes); remover devolve o Run
- **Um UAC só**: checkbox nova no instalador ("Executar como administrador") ou `/config` → SISTEMA → **Executar como administrador** (pede o UAC via `ShellExecute runas`). As duas passam por `agent.py --elevation-install|--elevation-remove`, que prepara o ambiente antes de importar o `core`. Instalar também troca o agente não elevado que estiver rodando pelo da tarefa
- **`core/autostart.py`**: com a tarefa, "Iniciar com o Windows" (bandeja e `/config`) habilita/desabilita a tarefa em vez do Run
- **`installer/jarvis.cmd`**: não elevado e com a tarefa `\JARVIS\TUI` → `schtasks /Run` (TUI elevada, sem UAC)
- **`installer/jarvis.iss`**: tarefa `admin`; Run e início do agente só sem ela; desinstalar apaga as tarefas (pede UAC só se existirem). Compila com o ISCC (`Successful compile`); o setup completo não foi rodado

> ⚠️ **Trade-off de segurança:** com isso, tudo que o JARVIS faz roda como administrador (skills de teclado/mouse, apps, e qualquer conteúdo da web, clipboard ou e-mail que convença o modelo). Mitigações mantidas: firewall só com argv fixo, encerrar/apagar/enviar continuam pedindo confirmação, nunca texto do LLM em `shell=True`. Efeito colateral do Windows (UIPI): **arrastar arquivo do Explorer para o terminal elevado não funciona** — use `/attach <caminho>`

### Firewall: entrada e saída, lista e desbloqueio

- **`backend/core/firewall.py`** (novo): `validate_ip` (nunca LAN, loopback, multicast ou reservado), `block_ip_commands` (duas regras: `dir=in` e `dir=out`), `block_program_inbound_command` (entrada de um `.exe` com caminho absoluto), `delete_rule_command` (só apaga regras com o prefixo `JARVIS bloqueio`), `run_commands` (lista, sem shell, sem janela)
- **`services/net_guard.py`**: `block_ip` cria entrada **e** saída; bloqueios ficam em `config.net_blocks`; `blocks_text` e `unblock` (`/rede bloqueios`, `/rede desbloquear <n|ip>`, com `ConfirmScreen`). Sem admin, a resposta aponta o `/config`
- `/status` → PERÍMETRO mostra `firewall admin ✓ · N bloqueios`

### Bloqueio automático

- O juiz (`prompts/judge_connection.md`, agora com o caminho do executável) responde **SEGURO | SUSPEITO | PERIGOSO**. PERIGOSO = sinal forte de malware (nome que imita processo do Windows, executável em pasta temporária, ferramenta conhecida de RAT/mineração). Na dúvida, SUSPEITO
- PERIGOSO + pref nova **`net_autoblock`** (ROTINAS → SEGURANÇA, ligada por padrão) + JARVIS elevado → bloqueia na hora (talker: IP em entrada e saída; listener: entrada do executável) e avisa com `/rede desbloquear <n>`. **Encerrar o processo continua pedindo confirmação**
- Sem admin nunca bloqueia sozinho; avisa uma vez por sessão que falta o admin. SUSPEITO segue o fluxo antigo

### Testes

- `tests/test_firewall.py` (novo, 12): validação de IP, entrada+saída, programa só com caminho absoluto, só apaga regra do JARVIS, para no 1º erro, XML da tarefa (usuário, nível mais alto, sem prazo), estado da tarefa (pt-BR), instalar/remover, recusa sem admin, autostart pela tarefa
- `tests/test_net_guard.py`: PERIGOSO bloqueia entrada e saída e ainda pede para encerrar; listener bloqueia o exe; sem admin nunca bloqueia e avisa uma vez; pref desligada; SUSPEITO nunca bloqueia; lista e desbloqueio por número/IP; erros
- `tests/test_hotkey_agent.py`: autostart pelo Run sem tarefa

## Perímetro de Rede: fabricante, nome e MAC privado de celular

**Data:** 2026-11-24
**Escopo:** Item "Perímetro de Rede — detecção de dispositivos estranhos" do Brainstorm. O vigia já avisava de aparelho novo e troca do MAC do roteador, mas só guardava `{mac: ip}` e todo celular com MAC privado virava "aparelho novo" a cada troca.

### O que mudou

- **`backend/core/oui.py`** (novo) + **`backend/core/data/oui.tsv.gz`** (40.554 fabricantes da IEEE, 385 KB, versionado): `vendor(mac)` com nome curto ("Intel Corporate" → "Intel"), `is_private(mac)` (bit 0x02). Nada sai do PC. Atualizar: `python tools/update_oui.py` (`backend/tools/update_oui.py`, novo; Wireshark ou IEEE)
- **`backend/core/netwatch.py`**:
  - Aparelho na base vira `{mac: {"ip", "vendor", "name", "private"}}`; base antiga `{mac: ip}` continua valendo (sem migração)
  - `identify_device` (só para aparelho novo, cache por MAC): fabricante + nome por DNS reverso (prazo de 2 s) e, sem ele, `nbtstat -A` (pt/en)
  - **MAC privado**: aparelho novo com bit 0x02 que bate com um privado da base — mesmo nome ou, sem nome dos dois lados, mesmo IP — vira `MAC_ROTATED` e só atualiza a base. MAC de fábrica nunca conta como rotação. Privado novo de verdade avisa com dica para fixar o MAC no Wi-Fi do aparelho
  - Alerta: `Aparelho novo na rede: 192.168.0.23 — Samsung Electronics (Galaxy-S23) (mac).`; troca do roteador mostra fabricante antigo → novo e reforça a suspeita se o fabricante mudou
- **`services/net_guard.py`**: `MAC_ROTATED` entra em silêncio; privado novo com prioridade normal (o resto segue alta; roteador, crítica); `/rede` lista IP · fabricante (nome) · MAC
- **`frontend/app.py`**: o vigia da TUI passa `identify=identify_device` (os testes ficam sem rede)

### Verificação

- Na rede real, o roteador aparece como "TELLESCOM INDUSTRIA E COMERCIO EM TELECOMUNICACAO (menuvivofibra.br)"
- Os `26.x.x.x` do ARP são pares da VPN Radmin (adaptador virtual, MAC privado) — já entravam antes; agora aparecem como "MAC privado"
- `tests/test_oui.py` (novo, 6) e 11 testes novos em `tests/test_netwatch.py` (base antiga, nome e fabricante no alerta, rotação por nome e por IP, MAC fixo nunca é rotação, roteador com fabricante, `nbtstat` pt/en, resolução que nunca levanta, cache por MAC, vigia repassa o `identify`) + 2 em `tests/test_net_guard.py`

## Consumo Energético em tempo real

**Data:** 2026-11-24
**Escopo:** Item "Consumo Energético — monitoramento em tempo real" do Brainstorm de Melhorias. Watts na linha de status e no `/status`, kWh e custo por dia e por mês, dado real no Chat e no briefing, skill `POWER_REPORT`.

### Como mede

Desktop não tem sensor do consumo total, então é **estimativa com a GPU medida**:
- **GPU NVIDIA:** watts reais do `nvidia-smi --query-gpu=power.draw` (lista, sem shell, sem janela, timeout 2 s, cache 3 s). Sem `nvidia-smi`, a GPU entra como 0 e o texto diz "sem leitura"
- **CPU:** `TDP × (15 % + 85 % × carga)`
- **Resto do PC:** base fixa `POWER_BASE_W`
- **Tomada:** soma dividida pela eficiência da fonte `POWER_PSU_EFF`

`power.meter` integra W × tempo em kWh por dia e grava em `config.power_daily` a cada 5 min e ao fechar a TUI (guarda 31 dias). Intervalo > 60 s entre amostras (PC suspenso, TUI travada) não conta. Atravessar a meia-noite divide o consumo entre os dois dias. Só conta com a TUI aberta.

### Arquivos

| Arquivo | Mudança |
|---------|---------|
| `backend/core/power.py` | **Novo**: `gpu_watts`, `estimate`, `PowerMeter` (thread-safe), `summary_text` |
| `backend/core/config.py`, `env.example`, `docs/variaveis-ambiente.md` | `POWER_TARIFF_KWH` (0,85), `POWER_BASE_W` (45), `POWER_CPU_TDP_W` (65), `POWER_PSU_EFF` (0,85), todas com padrão |
| `frontend/app.py` | Telemetria soma `⚡ 142W` e alimenta o medidor por `app._power_fn` (só com `start_services`; testes injetam fake); grava o dia ao sair |
| `frontend/screens/status.py`, `frontend/jarvis.tcss` | Medidor **ENERGIA** na largura toda (grade 2×3), escala pelo pico (mín. 200 W), detalhe "hoje X kWh · R$ · mês R$" |
| `backend/core/SystemInfo.py` | `get_realtime_context` ganha a linha `Consumo:` → o Chat responde watts com dado real |
| `backend/core/briefing.py` | Seção Computador: `ENERGIA → ontem X kWh (R$ Y)` quando houve contagem |
| `backend/skills/system/power_report.py`, `backend/prompts/skills/power_report.md` | **Nova skill** `POWER_REPORT` (Copilot/voz): agora, hoje e mês com custo, sem LLM |

### Testes

- `tests/test_power.py` (novo, 14 testes): estimativa e saneamento, parse do `nvidia-smi`, cache, ausência e erro, integração em kWh, intervalo grande ignorado, meia-noite, gravação periódica e poda, banco quebrado não levanta, resumo e contrato da skill
- `tests/test_tui_app.py`: `⚡` só com o medidor injetado; medidor ENERGIA no `/status`
- `tests/test_briefing.py`: linha ENERGIA no bloco Computador
- Suíte: 1214 passaram. `test_enter_requests_install_and_exits` falhou uma vez na suíte completa em paralelo e passou sozinho e em 3 rodadas da TUI sob `-n auto`: instabilidade de tempo, não relacionada

## Documentação conferida contra o código

**Data:** 2026-11-24
**Escopo:** Revisão de toda a documentação do repositório (e do vault do Obsidian) contra o código atual da `DEV`. Nenhum código mudou.

### O que estava desatualizado e foi corrigido

| Arquivo | Correção |
|---------|----------|
| `docs/variaveis-ambiente.md` | Reescrito: agora lista **todas** as variáveis que o `Settings` lê, por área e com o padrão (faltavam 29, entre elas `TIMEOUT_LLM`, `TIMEOUT_API`, `GITHUB_*`, `SPOTIFY_*`, `*_ALLOWED_IDS`, Whisper, visão, Pomodoro). `DEFAULT_LANGUAGE` saiu da lista: é fixo no `Settings`, não vem do `.env` |
| `env.example` | Ganhou as variáveis que faltavam (`OLLAMA_NUM_CTX`/`NUM_GPU`, visão, Whisper, `MAX_UPLOAD_SIZE_MB`, `GLOBAL_HOTKEY`, `TRANSLATE_HOTKEY`); atalhos globais numa seção própria (estavam no meio do Pomodoro); atualização descreve a assinatura Minisign |
| `docs/tui.md` | Tabela com todos os comandos `/`, gerada de `COMMANDS` (faltavam `/rename`, `/pin`, `/regen`, `/detach`, `/gh`, `/focus`, `/silent`, `/clear`, `/quit`) |
| `docs/estrutura.md` | `core/minisign.py` e `installer/sign_release.py`; updater confere SHA-256 **e** assinatura; CI roda também o pytest; regra do `requirements.lock` |
| `docs/arquitetura.md` | Serviços que faltavam (lembretes, insights, clipboard, rede, Gmail, winget, ponte), skills `SOFTWARE_INSTALL` e `EMAIL_MANAGEMENT`, `/email`/`/instalar`/`/baixar`, 8 tabelas, histórico de `CHAT_HISTORY_TURNS` (não 8 mensagens) |
| `backend/core/README.md` | `gmail`, `google_auth`, `winget`, `telegram_bot`, `discord_bot`, `messenger_ctl`, `minisign`; `database` com 8 tabelas; evento `EXPLAIN` |
| `backend/services/README.md` | `mailbox`, `email_*`, `local_files`, `software`, `remote_chat`, `net_trust` |
| `backend/database/README.md` | Tabelas `clipboard_history`, `reminders`, `net_trusted_apps`, `email_contacts` e as chaves da `config` que faltavam |
| `backend/skills/README.md` | `BROWSER_TABS`, `YOUTUBE_CONTROL` e `SCREEN_READ` na tabela |
| `frontend/README.md` | `/email`, `/instalar`, `/baixar`; `/rede mantidos` e `esquecer` |
| `README.md` | Gmail, ponte Telegram/Discord, download pelo winget, clipboard/lembretes/ideias, vigia de rede, `Ctrl+Alt+E`, assinatura do setup; integrações completas; tirado o link para o `CLAUDE.md` (fora do git); testes com `-n auto` |
| `AGENTS.md` | Modo Chat descrito pela lista branca (`productivity` e `web`) |
| `docs/politica-de-privacidade.md`, `docs/termos-de-uso.md` | Atualização confere SHA-256 **e** assinatura Minisign |

### Depois da feature de energia (`2d16201`)

`POWER_REPORT` e `core/power.py` entraram em `docs/estrutura.md`, `docs/arquitetura.md`, `backend/core/README.md`, `backend/skills/README.md` (26 skills), `backend/database/README.md` (chave `power_daily`), `docs/tui.md` e `frontend/README.md` (watts na linha de status, medidor ENERGIA no `/status`) e `README.md`.

### Vault do Obsidian

- Notas novas: `E-mail — Gmail (EMAIL_MANAGEMENT)` e `Ponte Remota e Download Inteligente`.
- Atualizadas: Intent, Brain, Database, Skills — Produtividade e Web, TUI — Comandos, Integrações, Agente Residente, Updater, Vigia de Rede, Config, Arquitetura Ponta a Ponta e a nota do projeto (funcionalidades, progresso pelos PRs #63–#82, estrutura).
- Notas de entrega de 19 a 24/11 marcadas como concluídas, com o PR de cada uma.
- `🧠 Brainstorms/J.A.R.V.I.S — Brainstorm de Melhorias.md`: pendências do classificador e do teste do `/clip` fechadas (PR #82), erros que sobraram, próximos passos (ponte ponta a ponta, PR `DEV` → `main`) e o andamento do consumo de energia.

### Validação

- `pytest tests/test_agents_doc.py tests/test_oauth_connect.py`: 27 passaram.

## Correção: classificador estourando o tempo + cartucho único de e-mail

**Data:** 2026-11-24
**Escopo:** Em toda mensagem (visto pela ponte do Discord, modo Chat) o classificador passava de `TIMEOUT_API` (10 s) e caía em CHAT: skills não disparavam. Causa: gemma2:2b só ~77% na VRAM e prompt do classificador com ~3,4 mil tokens. A janela de contexto **não** foi aumentada: o gemma2:2b tem teto de 8192 e mais contexto = mais KV cache na VRAM (~104 KB/token), o que pioraria a parte que já roda na CPU.

### O que mudou

| Arquivo | Mudança |
|---------|---------|
| `backend/core/config.py` | Novo `TIMEOUT_LLM` (padrão 30 s) para as chamadas curtas ao Ollama. `TIMEOUT_API` (10 s) fica só para HTTP (GitHub, notícias, web, YouTube); os dois agora podem vir do `.env` |
| `backend/services/intent.py` | Classificador usa `TIMEOUT_LLM`. Chat por **lista branca**: `CHAT_ALLOWED_CATEGORIES = ("productivity", "web")` no lugar de `CHAT_BLOCKED_CATEGORIES`; `classify_intent(..., allowed_categories=)` (None = todas, Copilot). Só skills ativas dessas categorias entram no prompt; categoria nova não vaza para o Chat |
| `backend/services/brain.py` | Chat passa `allowed_categories=CHAT_ALLOWED_CATEGORIES` |
| `backend/skills/**` | Chamadas de decisão ao Ollama (app, áudio, abas, teclado, tela, Spotify, macros, YouTube, GitHub, limpeza, segurança) usam `TIMEOUT_LLM` |
| `backend/prompts/classify_intent.md` | Exemplos de skills saíram do prompt base (ficaram só os de MEMORY_READ/WRITE). Prompt base: 5,2 mil → 1,9 mil caracteres. Regra 4 dizia "use CHAT apenas se for saudação", contradizendo a definição de CHAT: no teste real, "me explica recursão em python" virava `SCREEN_READ`. Agora: skill só quando o pedido se encaixa no "Use quando" dela; o resto é CHAT |
| `backend/prompts/skills/*.md` | Cada skill ganhou os seus exemplos no próprio bloco: só entram quando a skill é oferecida (no Chat não aparecem mais exemplos de APP_CONTROL, SPOTIFY, SYSTEM_SECURITY…) |
| `backend/skills/productivity/email_management.py` | Novo cartucho **`EMAIL_MANAGEMENT`** no lugar de `EMAIL_READ`, `EMAIL_SEND`, `EMAIL_TRASH` e `EMAIL_ORGANIZE`. A ação sai da frase por regex (`action_for`, sem nova ida ao modelo): apagar → organizar → enviar/responder → ler. Comportamento igual ao de antes: mesmas confirmações (`pending` com os tipos `EMAIL_SEND`/`EMAIL_TRASH`/`EMAIL_ORGANIZE`), nada é excluído de vez |
| `backend/prompts/skills/email_management.md` | Um bloco só (substitui os 4 `email_*.md`) |
| `env.example` | `TIMEOUT_LLM=30` e `TIMEOUT_API=10` |
| `backend/tests/test_tui_tools.py` | `test_clip_bad_action_and_empty_history` agora usa o banco de teste: lia o histórico de clipboard real do usuário e falhava em quem tinha histórico |

### Tamanho do prompt do classificador (estimado, ~3,5 caracteres/token)

| Mensagem | Modo | Antes | Depois |
|----------|------|-------|--------|
| "me explica recursão em python" (nenhuma KEYWORD) | Chat | ~3.440 | ~2.800 |
| "qual minha agenda amanhã?" | Chat | ~1.660 | ~810 |
| "leia o e-mail 2" | Chat | ~2.000 | ~945 |
| "me explica recursão em python" | Copilot | ~5.190 | ~4.930 |

### Atenção

- Quem tinha desligado alguma `EMAIL_*` em `/skills` precisa desligar `EMAIL_MANAGEMENT` de novo (a chave antiga fica órfã no banco, sem efeito).

### Documentação

`docs/skills.md`, `docs/arquitetura.md` (seção 5.7 e classificador), `docs/fluxos.md`, `docs/estrutura.md`, `backend/skills/README.md`, `backend/services/README.md`, `backend/docs/services/brain.md`, `backend/docs/core/config.md`.

### Validação

- `pytest tests -q -n auto`: todos passam, inclusive o teste do `/clip` que falhava na `DEV`. Novos: lista branca (categoria inventada fica fora do Chat, skill desligada some), timeout do classificador, exemplos no bloco de cada skill, roteamento das 15 frases do cartucho de e-mail.
- `ruff check .` limpo em `backend/` e `frontend/`.
- Ollama real (gemma2:2b, 8192 de contexto, 23%/77% CPU/GPU), 16 frases: com KEYWORD o classificador responde em **2–4 s** (na `DEV`: 6–10 s, e a 1ª estourou os 10 s). Sem KEYWORD (todas as productivity/web): 10–15 s, dentro dos 30 s. Acertos: 14 de 16.
- Erros que sobram (limite do gemma2:2b): "abre o spotify" no Chat vira `SCREEN_READ` (na `DEV` virava `APP_CONTROL`, bloqueado depois pelo `brain`); "qual a capital da França?" vira `WEB_SEARCH` (responde, só que pela busca).

## Correção: busca no vault do Obsidian (RAG) e alucinação sobre notas

**Data:** 2026-11-23
**Escopo:** Pelo Discord, "JARVIS acesse meu obsidian e leia a nota sobre o meu projeto OHMFLOW e me diga do que que ele se trata" virou uma descrição inventada ("sistema de hidrólise em micro-ondas"). O vault estava acessível; o RAG é que nunca trazia a nota. Vale para TUI, voz e ponte Telegram/Discord (todos passam por `get_vault_context`).

### Causas

| # | Causa | Efeito |
|---|-------|--------|
| 1 | `search_scored` / `search` chamavam `GET /search/simple/`. No plugin Local REST API essa rota é **POST**; o GET dá 404, que o `_send` lê como "nota não existe" | A Camada 2 (busca no vault) **sempre** voltava vazia |
| 2 | A consulta pegava as 4 primeiras palavras com mais de 3 letras | Virou `acesse obsidian leia nota`: o nome do projeto ficou de fora |
| 3 | O ranking era só o score do plugin | `System Boost - CHANGES.md` (que só cita "ohmflow") vinha antes das notas do OhmFlow |
| 4 | Sem nota no contexto, nada impedia o modelo de inventar; o prompt de sistema citava a tag `[MEMÓRIA DO VAULT — ...]`, mas o bloco real se chamava `[MEMÓRIA PESSOAL — ...]` | O modelo escreveu a tag e inventou o conteúdo |

### O que mudou

| Arquivo | Mudança |
|---------|---------|
| `backend/core/obsidian.py` | Busca por **POST** com timeout de 15 s (`SEARCH_TIMEOUT_S`; a 1ª busca com o índice frio passava de 5 s). `search_keywords()`: ignora palavras do pedido (`_REQUEST_WORDS`: acesse, leia, nota, obsidian, diga, sobre, projeto…), põe nome próprio/sigla (com maiúscula) primeiro e só ignora "jarvis" quando é chamado ("JARVIS, …"), não quando é o assunto. `_rank()`: caminho que cita as palavras > nota principal da pasta > score. `_main_note()`: se a pasta é o assunto (`🚀 Projetos/OhmFlow/…`), lê `OhmFlow.md`/`index.md`, a não ser que o nome da nota cite outra palavra da pergunta ("arquitetura" → `OhmFlow - 02 Arquitetura.md`). Busca com vários termos vazia → tenta só o principal. `asks_vault()`: detecta pedido explícito de nota/projeto/vault |
| `backend/services/brain.py` | Passa `vault_missing=True` quando o usuário pediu uma nota e o vault não trouxe nada |
| `backend/services/chat.py` | `vault_missing` → bloco `vault_not_found.md`. Temperatura 0,1 também quando há nota do vault ou o aviso de nota não achada |
| `backend/prompts/vault_not_found.md` | Novo: "não encontrei essa nota, qual o nome exato?", sem inventar. Escrito como instrução simples, sem tag — o gemma2:2b copiava o bloco com tag palavra por palavra |
| `backend/prompts/vault_memory.md` | Tag alinhada com o prompt de sistema: `[MEMÓRIA DO VAULT — nota]` |
| `backend/prompts/system_prompt.md` | Regra 6: sem bloco do vault, não leu nota nenhuma — nunca inventar conteúdo nem escrever a tag |
| `backend/tests/test_vault_search.py` | Novo (21 testes): POST, palavras do assunto, ranking, nota principal × nota do tema, nova tentativa, `asks_vault`, aviso e temperatura, flag no `brain` |

### Documentação

| Arquivo | Mudança |
|---------|---------|
| `backend/docs/core/obsidian.md` | Reescrito: ainda descrevia o `ObsidianMCPClient`/`uvx` (removidos em 19/11). Agora: cliente REST, busca POST e score negativo, as duas camadas do RAG passo a passo, aviso de nota não encontrada e como manter `_REQUEST_WORDS` |
| `backend/core/README.md` | Linha do `obsidian.py` atualizada; tirado `mcp_client` do exemplo de import e o "prepara o cliente MCP" |
| `backend/services/README.md` | `build_messages` inclui `vault_not_found.md` |
| `backend/docs/services/brain.md` | Passo 5 do pipeline com `vault_missing` |
| `docs/banco-de-dados.md` | Camada 2 descrita como está agora (assunto, POST, ranking, nota principal, aviso) |
| `docs/arquitetura.md` | Fluxo do Chat cita o aviso de nota não encontrada |

### Validação

- `pytest tests -q -n auto`: 1192 passaram. A única falha (`test_tui_tools.py::TestClipCommand::test_clip_bad_action_and_empty_history`) já falha na `DEV` sem estas mudanças.
- `ruff check .` limpo em `backend/` e `frontend/`.
- Vault real: a pergunta original agora lê `🚀 Projetos/OhmFlow/OhmFlow.md`; "arquitetura do OhmFlow" lê `OhmFlow - 02 Arquitetura.md`; "projeto System Boost" lê `System Boost.md`.
- Ollama (gemma2:2b): a resposta sobre o OhmFlow sai da nota (C99, Windows, SQLite, desfazer/refazer, instalador); nota inexistente → "Não encontrei nenhuma nota relacionada ao projeto Xyzabc no vault…".

### Pendente (fora deste escopo)

- O classificador estoura `TIMEOUT_API` (10 s) em toda mensagem: o gemma2:2b só cabe ~77% na VRAM e o prompt do classificador tem ~3,4 mil tokens. Toda mensagem cai em CHAT (skills não disparam pela ponte). O Ollama limita o gemma2 a 8192 de contexto, mesmo com o servidor em 32k.

## Refatoração do AGENTS.md: documentação dividida em `docs/`

**Data:** 2026-11-23
**Escopo:** O `AGENTS.md` tinha 493 linhas e misturava o essencial (rodar, testar, instalar, workflow) com regras detalhadas de backend, TUI, banco e alertas. Agora ele é um arquivo de entrada de 92 linhas, e o restante mora em `docs/`, um assunto por arquivo. Nenhuma regra foi alterada: o conteúdo foi movido como estava.

### O que ficou no `AGENTS.md`

| Seção | Observação |
|-------|------------|
| O que é este projeto | Resumo, cérebro, modos, repositório e dev |
| Mapa da documentação (`docs/`) | Tabela assunto → arquivo, com o aviso de ler o arquivo do assunto antes de alterar código |
| Instalação de dependências | venv, `requirements.txt` + `requirements-dev.txt`, `.env` na raiz, Ollama e plugin do Obsidian |
| Como rodar o projeto | `python main.py`, `--copilot` e `python -m services.brain` |
| Como rodar os testes | Suíte inteira (`-n auto`), só a feature e `ruff check .` |
| Workflow obrigatório de desenvolvimento | Os 10 passos, boas práticas e a regra de consultar o Obsidian primeiro |

### Para onde foi o resto

| Arquivo novo | Conteúdo que veio do `AGENTS.md` |
|--------------|----------------------------------|
| `docs/estrutura.md` | Árvore do repositório e "Modo instalado (`JARVIS_DATA_DIR`)" |
| `docs/regras-backend.md` | Logging, Ollama, Prompts, Threading, Sentidos (voz), Estado global e Configurações |
| `docs/banco-de-dados.md` | SQLite (`database.py`) e Obsidian (memória de longo prazo) |
| `docs/skills.md` | Contrato obrigatório e "Como criar uma nova skill" |
| `docs/tui.md` | Modos, Atalhos e comandos, Visual, Badge de skill e Testes da TUI |
| `docs/alertas.md` | Alertas, vigia de rede e Não Perturbe |
| `docs/agente-residente.md` | Agente residente e atualização automática |
| `docs/fluxos.md` | Fluxo de um comando de voz e de uma mensagem no Chat |
| `docs/variaveis-ambiente.md` | Bloco de variáveis do `.env` |
| `docs/personalidade.md` | Tom e personalidade do JARVIS |
| `docs/decisoes-arquiteturais.md` | Tabela de decisões e razões |

### Ajustes feitos no caminho

- Numeração do workflow: o passo "110" virou "10".
- Instalação e testes: `requirements-dev.txt` (pytest, pytest-xdist, ruff), `-n auto` e `--copilot`, que antes não estavam no `AGENTS.md`.
- Removida a lista "Principais pacotes do `requirements.txt`" (cópia parcial e desatualizada; a fonte é o próprio `requirements.txt`).
- `docs/estrutura.md`: a linha de `docs/` na árvore lista os arquivos novos.
- `docs/arquitetura.md`: o link para `CLAUDE.md` (arquivo local, ignorado pelo git, que não existe no CI nem em quem clona) passou a apontar para `AGENTS.md` e `regras-backend.md`. O teste `test_links_dos_docs_existem` achou esse link quebrado no CI.
- Os arquivos novos linkam entre si e para o `AGENTS.md`; o teste abaixo confere todos os links.

### Termos de Uso e Política de Privacidade (novos)

| Arquivo | Conteúdo |
|---------|----------|
| `docs/termos-de-uso.md` | 15 seções: escopo, licença MIT, requisitos e contas de terceiros, ações no PC (com confirmação), erros da IA, uso aceitável, serviços de terceiros, atualizações, chaves, sem garantia, limitação de responsabilidade, marcas, encerramento, lei aplicável e contato |
| `docs/politica-de-privacidade.md` | 12 seções: o que fica no PC (uma linha por dado), o que é local, o que sai do PC (uma linha por recurso e destino), recursos sensíveis, controles, retenção, segurança e direitos (LGPD) |

- Escritos a partir do código, não de um modelo genérico: fluxos conferidos em `listen.py`, `speak.py`, `weather.py`, `web.py`, `secrets_store.py`, `user_prefs.py`, `database.py` e `SECURITY.md`.
- A política diz abertamente: o **áudio de toda fala vai ao Google** com a voz ligada (antes da palavra de ativação); a **localização por IP usa `http://ip-api.com`** (HTTP, sem criptografia); os **logs não têm expurgo automático**; o `.env` e o JSON de reserva dos tokens são texto.
- `AGENTS.md` ganhou duas linhas no mapa da documentação (92 linhas). `docs/regras-backend.md` ganhou a seção **Privacidade**: nova integração externa ou dado novo no disco exige atualizar a política.
- Revisão jurídica: são textos-base para um projeto pessoal e de código aberto; se o JARVIS for distribuído amplamente, vale uma revisão de advogado.

### Testes

**Novo:** `backend/tests/test_agents_doc.py`: `AGENTS.md` com no máximo 150 linhas; seções essenciais e comandos de instalar, rodar e testar presentes; todo link do `AGENTS.md` e dos `docs/*.md` aponta para arquivo que existe; o `AGENTS.md` linka todos os 15 arquivos de `docs/`; nenhum deles está vazio.

## Lixeira do Gmail por pedido e Agenda por semana, mês e ano

**Data:** 2026-11-23
**Escopo:** Duas melhorias em cima do PR #78:
1. Pedir ao JARVIS para apagar um e-mail agora move a mensagem para a **Lixeira do Gmail**, depois de confirmação. Usa o mesmo escopo `gmail.modify`, sem mudança no Google Cloud.
2. Correção da Agenda. "Qual compromisso eu tenho essa semana?" respondia "Agenda livre hoje.", porque a skill só entendia dias. Agora ela entende semana, fim de semana, mês e ano.

### 1. E-mail para a Lixeira

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `gmail.trash(ids)`: `POST /messages/{id}/trash` por mensagem. O Gmail esvazia a Lixeira sozinho em 30 dias, então dá para desfazer. Exclusão permanente continua sem existir no JARVIS (exigiria o escopo total `https://mail.google.com/`) | `backend/core/gmail.py` |
| 2 | Serviço `email_trash`. O que apagar vem **só da fala do usuário**: números da última lista mostrada ("apaga os e-mails 2 e 5") ou uma categoria clara ("as promoções", "as notificações de rede social"). Sem número nem categoria ("apaga meus e-mails"), pergunta quais e não arma nada. A confirmação (120 s, até 50 e-mails) lista assunto e remetente: **sim** move, **não** mantém. Depois de mover, os e-mails saem da lista vista (a numeração muda) | `backend/services/email_trash.py` (novo) |
| 3 | Skill `EMAIL_TRASH` (productivity: Chat, Copilot e ponte), com aviso `# ⚠️ ACESSO SENSÍVEL`, prompt próprio e exemplos no classificador. `EMAIL_ORGANIZE` ganha "NÃO use para apagar e-mails específicos" | `backend/skills/productivity/email_trash.py` (novo), `backend/prompts/skills/email_trash.md` (novo), `backend/prompts/skills/email_organize.md`, `backend/prompts/classify_intent.md` |
| 4 | `/email apagar <n…|promoções>` na TUI. A confirmação abre no `ConfirmScreen` | `frontend/app.py`, `frontend/commands.py` |

### 2. Agenda por período

| # | Mudança | Arquivos |
|---|---------|----------|
| 1 | `resolve_period(texto)` devolve o tipo de período (dia, intervalo ou próxima reunião), início, fim e rótulo. Períodos entendidos: **semana** (de hoje até domingo), **fim de semana**, **mês** (de hoje até o fim do mês), **ano** (de hoje até 31/12) e os próximos ("próxima semana", "semana que vem", "próximo mês", "mês que vem", "próximo ano"), que pegam o período inteiro. Palavras dentro de outras não contam ("ano" em "anota"). Sem período, vale o `resolve_day` de antes | `backend/core/google_calendar.py` |
| 2 | `events_range(início, fim)` pagina a API (`pageToken`, até 250 eventos); `events(dia)` passa a usá-la | `backend/core/google_calendar.py` |
| 3 | `format_range` agrupa por dia: `- **qua 25/11** · 09:00 Daily · 14:00 Dentista`, com o intervalo no cabeçalho ("3 eventos nesta semana (25/11 a 29/11)"). Um evento que começou antes do período (férias) entra no primeiro dia. Acima de 40 eventos, mostra "… e mais N" | `backend/core/google_calendar.py` |
| 4 | Skill `CALENDAR` usa o período; as palavras-chave do pré-filtro ganham mês, ano, fim de semana e marcado | `backend/skills/productivity/calendar_agenda.py` |
| 5 | O contexto da Agenda no Chat usa o mesmo período, com o dia em cada linha (`- qui 26/11 10:00–11:00 Reunião`). O prompt passa a dizer "Período consultado" | `backend/services/live_context.py`, `backend/prompts/calendar_context.md` |
| 6 | Prompt da skill e exemplos do classificador com semana e mês | `backend/prompts/skills/calendar.md`, `backend/prompts/classify_intent.md` |

### Documentação

- `AGENTS.md`: `google_calendar` com períodos, `gmail.trash`, `email_trash`, `/email apagar`.
- `docs/arquitetura.md`: Lixeira em 5.7 e nova seção 5.7.1, Agenda por período.
- `docs/integracoes-oauth.md`: Lixeira no Gmail e aviso para **não** marcar `https://mail.google.com/`.
- `backend/skills/README.md`: `EMAIL_TRASH` e o `CALENDAR` com períodos.

### Testes

**Novos:**
- `test_calendar_periods.py`: semana, próxima semana, fim de semana, mês, próximo mês, ano, próximo ano, dias como antes, "ano" dentro de "anota"; paginação e limite do `events_range`; agrupamento por dia, evento em andamento, lista vazia e longa; o caso do print ("qual compromisso eu tenho essa semana?") na skill e no contexto do Chat.
- `test_email_trash.py`: seleção por números e por categoria; frase vaga não apaga nada; só move depois do "sim"; "não" mantém; lista vazia busca antes; confirmação ocupada; erro do Gmail; não conectado; contrato da skill.

**Ajustados:**
- `test_gmail.py`: `trash` move cada mensagem e nunca chama exclusão; `delete` continua sem existir.
- `test_tui_tools.py`: `/email apagar 2 3`.
