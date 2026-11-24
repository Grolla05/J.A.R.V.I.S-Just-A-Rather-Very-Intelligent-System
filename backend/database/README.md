# Banco de dados (SQLite)

O JARVIS guarda o estado local num SQLite (`jarvis_memory.db`), gerenciado por `core/database.py` (`from core.database import db`). A memória de longo prazo fica no Obsidian; o SQLite guarda histórico, sessões, preferências, specs da máquina, clipboard, lembretes, softwares mantidos no Vigia de rede e contatos de e-mail (8 tabelas).

**Local do arquivo:** `settings.DB_PATH`
- Dev: `backend/database/jarvis_memory.db`
- Instalado: `%APPDATA%\JARVIS\database\jarvis_memory.db` (`JARVIS_DATA_DIR`)

## Tabelas

### `config` — chave/valor

| Coluna | Tipo | |
|---|---|---|
| `key` | TEXT PK | |
| `value` | TEXT | JSON serializado por `save_config` (listas, números, bools, textos) |
| `updated_at` | TIMESTAMP | |

Chaves em uso:

| Chave | Dono | Conteúdo |
|---|---|---|
| `disabled_skills`, `disabled_categories` | `services/skill_settings.py` | listas de INTENT / categorias desligadas em `/skills` |
| `pref_<nome>` | `services/user_prefs.py` | preferências do `/config` (`pref_tts_voice`, `pref_briefing_auto`, `pref_news_ai`…) |
| `briefing_last_date` | `core/briefing.py` | data do último briefing (automático 1× por dia) |
| `news_sources` | `core/news.py` | fontes de notícias do briefing ("G1, BBC, CNN Brasil, …") |
| `commute_home`, `commute_work`, `place_<local>`, `places_index` | `core/traffic.py` | locais cadastrados com `/rota` |
| `commute_alert_last` | `core/traffic.py` | último aviso de saída (evita repetir) |
| `dnd_restore` | `services/focus.py` | estado dos toasts do Windows a restaurar ao sair do Não Perturbe |
| `insights_pending`, `insights_seen` | `services/insights.py` | ideias na fila (Obsidian fora do ar) e as já gravadas |
| `reminders_fired`, `reminders_geo_cache` | `services/reminders.py` | avisos de evento já dados e cache de geocodificação |
| `net_baseline` | `services/net_guard.py` | linha de base do Vigia de rede |
| `email_vip` | `services/mailbox.py` | remetentes VIP (`/email vip`) |
| `email_signature` | `services/email_compose.py` | assinatura dos e-mails (`/email assinatura`) |
| `remote_session:<canal>:<id>` | `services/remote_chat.py` | sessão atual de cada usuário da ponte Telegram/Discord |

### `history` — mensagens

| Coluna | Tipo | |
|---|---|---|
| `id` | INTEGER PK | autoincremento |
| `session_id` | TEXT | sessão: `chat_<hex>` na TUI (Chat e Copilot), `voice_<token>` no modo voz standalone |
| `role` | TEXT | `user` ou `assistant` |
| `content` | TEXT | texto da mensagem |
| `timestamp` | TIMESTAMP | **UTC** — mostre com `sessions.to_local()` |
| `attachment_type` | TEXT | `image`/`audio` (nullable) |
| `attachment_path` | TEXT | caminho relativo a `DIR_UPLOADS` (nullable) |
| `mode` | TEXT | `chat` ou `copilot` (mostrado nos save slots) |

Índice `idx_history_session` em `session_id`.

### `sessions` — metadados

| Coluna | Tipo | |
|---|---|---|
| `id` | TEXT PK | id da sessão |
| `title` | TEXT | título (automático ou `/rename`) |
| `is_pinned` | INTEGER | 1 = fixada (aparece primeiro em `Ctrl+O`) |
| `created_at` | TIMESTAMP | UTC |

### `hardware` — specs da máquina

| Coluna | Tipo | |
|---|---|---|
| `component` | TEXT PK | `CPU`, `GPU`, `RAM`, `Motherboard`… |
| `description` | TEXT | texto do WMI |
| `detected_at` | TIMESTAMP | último scan (a cada boot, em thread) |

Usada para responder perguntas de hardware sem o LLM inventar (`db.get_system_specs()`).

### `clipboard_history` — histórico do clipboard (`services/clip_history.py`)

| Coluna | Tipo | |
|---|---|---|
| `id` | INTEGER PK | autoincremento |
| `kind` | TEXT | tipo do conteúdo (link, erro, código, texto…) |
| `content` | TEXT | o que foi copiado (nunca o que tem cara de senha/token) |
| `digest` | TEXT UNIQUE | recopiar o mesmo texto só atualiza `copied_at` |
| `copied_at` | TIMESTAMP | UTC |

Só enche com o **Monitor de clipboard** ligado.

### `reminders` — lembretes por pedido (`services/reminders.py`)

| Coluna | Tipo | |
|---|---|---|
| `id` | INTEGER PK | autoincremento |
| `text` | TEXT | assunto ("tirar a roupa da máquina") |
| `due_at` | TEXT | hora **local** ISO |
| `created_at` | TIMESTAMP | UTC |
| `fired_at` | TEXT | quando foi avisado (nullable) |

### `net_trusted_apps` — softwares mantidos no Vigia de rede (`services/net_trust.py`)

| Coluna | Tipo | |
|---|---|---|
| `id` | INTEGER PK | autoincremento |
| `name` / `name_key` | TEXT | nome do processo e a forma normalizada |
| `exe` / `exe_key` | TEXT | caminho do executável e a forma normalizada (`UNIQUE(name_key, exe_key)`) |
| `kind`, `reason` | TEXT | tipo do achado e motivo |
| `decided_at` | TIMESTAMP | UTC |

Sobrevive ao `/rede reset`; `/rede mantidos` lista e `/rede esquecer <n>` remove.

### `email_contacts` — apelidos de contato (`services/email_contacts.py`)

| Coluna | Tipo | |
|---|---|---|
| `alias` | TEXT PK | apelido ("guilherme") |
| `address` | TEXT | e-mail confirmado |
| `last_used` | TIMESTAMP | UTC |

Gravado por `/email contato <apelido> <e-mail>` ou quando o usuário escolhe um contato.

## Regras

- Toda operação fecha a conexão em `finally`.
- Coluna nova: `PRAGMA table_info` + `ALTER TABLE` em `_initialize_tables` (bancos antigos migram sozinhos).
- UPSERT com `ON CONFLICT(key) DO UPDATE SET` — nunca checar se existe antes.
- SQL de sessão fica em `services/sessions.py`, nunca na TUI.
