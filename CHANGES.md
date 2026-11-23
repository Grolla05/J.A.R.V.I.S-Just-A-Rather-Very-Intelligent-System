# CHANGES.md

Registro das mudanças aplicadas no J.A.R.V.I.S.

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
