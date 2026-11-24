# Banco de dados — SQLite e Obsidian

Memória do J.A.R.V.I.S: SQLite local (`database.py`) e o vault do Obsidian (longo prazo). Regras gerais do backend em [`regras-backend.md`](regras-backend.md); resumo do projeto em [`AGENTS.md`](../AGENTS.md).

## SQLite (`database.py`)

- Toda operação SQL **deve** terminar com `conn.close()` em bloco `finally`
- Novas colunas: sempre adicionar fallback `PRAGMA table_info` + `ALTER TABLE` para bancos antigos
- Arquivo gerado em `backend/database/jarvis_memory.db` com 8 tabelas: `config`, `history`, `sessions`, `hardware`, `clipboard_history`, `reminders`, `net_trusted_apps`, `email_contacts`
- UPSERT via `ON CONFLICT(key) DO UPDATE SET` — nunca checar existência manualmente antes de inserir
- Acesso: `from core.database import db` → `db.log_interaction()`, `db.get_config()`, `db.save_config()`, `db.update_hardware_spec()`
- Sessões/histórico do chat: `from services import sessions` (não escrever SQL de sessão na TUI). O mesmo vale para `services/clip_history.py` e `services/reminders.py`: a TUI só chama as funções

## Obsidian (memória de longo prazo)

- O Obsidian funciona como cofre semântico de **longo prazo** — não substitui o SQLite, complementa
- Memórias efêmeras da IA ficam em `🚀 Projetos/J.A.R.V.I.S/Memória/{key}.md` (`MEMORY_NOTE_PATH`; o path sempre passa por `urllib.parse.quote`)
- **Nunca sobrescreve** notas existentes — preserva edições manuais do usuário no vault
- Ideias e brainstorms vão para `🧠 Brainstorms/J.A.R.V.I.S — Insights AAAA-MM.md` (`INSIGHTS_NOTE_PATH`), sempre por `obsidian.append_note()` (POST = append; `note_exists()` distingue 404 de Obsidian fora do ar). Com o Obsidian fora, `services/insights.py` enfileira em `insights_pending` e grava depois
- RAG em 2 camadas via `core/obsidian.py`:
  - **Camada 1**: palavras de perfil pessoal (`_PROFILE_KEYWORDS`) → puxa `Sobre mim.md` inteiro
  - **Camada 2**: palavras do **assunto** (`search_keywords`: sem palavras do pedido como acesse/leia/nota/obsidian; nome próprio primeiro) → busca via REST (`obsidian.search_scored`, que é **POST** — GET dá 404 = vazio) → ranking local (`_rank`: caminho que cita as palavras > nota principal da pasta > score) → `_main_note` lê `Pasta/Pasta.md` quando a pasta é o assunto
  - Pedido explícito de nota sem resultado (`asks_vault`) → `prompts/vault_not_found.md`: o JARVIS diz que não achou em vez de inventar. Detalhes: `backend/docs/core/obsidian.md`
- Acesso: `from core.obsidian import obsidian, get_vault_context`
  - `obsidian.save_memory(key, value)` → salva nota no vault
  - `obsidian.get_memory(key)` → lê primeira linha útil da nota
  - `get_vault_context(text)` → retorna `(filename, context_str)` para injetar no prompt
- Paths com acentos **devem** passar por `urllib.parse.quote(..., encoding="utf-8")` — sem isso: 404
