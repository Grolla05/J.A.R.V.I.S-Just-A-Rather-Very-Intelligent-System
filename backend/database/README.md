# Banco de dados (SQLite)

O JARVIS guarda o estado local num SQLite (`jarvis_memory.db`), gerenciado por `core/database.py` (`from core.database import db`). A memória de longo prazo fica no Obsidian; o SQLite guarda histórico, sessões, preferências e specs da máquina.

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
| `pref_<nome>` | `services/user_prefs.py` | preferências do `/config` (`pref_tts_voice`, `pref_briefing_auto`…) |
| `briefing_last_date` | `core/briefing.py` | data do último briefing (automático 1× por dia) |
| `news_sources` | `core/news.py` | fontes de notícias do briefing ("G1, BBC, …") |
| `commute_home`, `commute_work`, `place_<local>`, `places_index` | `core/traffic.py` | locais cadastrados com `/rota` |
| `commute_alert_last` | `core/traffic.py` | último aviso de saída (evita repetir) |
| `dnd_restore` | `services/focus.py` | estado dos toasts do Windows a restaurar ao sair do Não Perturbe |

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

## Regras

- Toda operação fecha a conexão em `finally`.
- Coluna nova: `PRAGMA table_info` + `ALTER TABLE` em `_initialize_tables` (bancos antigos migram sozinhos).
- UPSERT com `ON CONFLICT(key) DO UPDATE SET` — nunca checar se existe antes.
- SQL de sessão fica em `services/sessions.py`, nunca na TUI.
