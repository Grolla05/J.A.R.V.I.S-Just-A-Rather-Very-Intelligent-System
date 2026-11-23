# CHANGES.md

Registro das mudanças aplicadas no J.A.R.V.I.S.

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
