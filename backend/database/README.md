# 🗄️ Camada de Persistência (Database J.A.R.V.I.S.)

Este diretório contém a lógica de memória de longo prazo do assistente, utilizando **SQLite3** nativo como motor de banco de dados. Arquitetura desenhada para **Persistência Transparente** — salva estados e históricos sem bloquear o processamento de áudio ou IA.

## 📋 Estrutura de Dados (Esquema)

O banco `jarvis_memory.db` é composto por quatro tabelas:

---

### 1. Tabela `hardware` (Identidade da Máquina)

Especificações de hardware detectadas pelo `hardware.py` via PowerShell/WMI. Persiste entre reinicializações para evitar alucinação da IA sobre specs do sistema.

```text
+-------------------+----------------------------+---------------------+
|  component (PK)   |        description         |     detected_at     |
|      [TEXT]       |          [TEXT]            |     [TIMESTAMP]     |
+-------------------+----------------------------+---------------------+
| "CPU"             | "Intel Core i9-9900K"      | 2025-12-18 10:00:00 |
| "GPU"             | "NVIDIA RTX 4070"          | 2025-12-18 10:00:01 |
| "RAM"             | "32 GB DDR5"               | 2025-12-18 10:00:01 |
+-------------------+----------------------------+---------------------+
```

- **`component`**: Identificador do componente (Primary Key): `CPU`, `GPU`, `RAM`, `Motherboard`
- **`description`**: Descrição legível retornada pelo WMI
- **`detected_at`**: Timestamp da última varredura (atualizado a cada boot)

---

### 2. Tabela `history` (Memória Episódica)

Trilha completa de conversação por sessão, usada como contexto para a IA.

```text
+---------+-------------+--------------------------------+--------------------+--------------------+
| id (PK) |  session_id |    role     |     content      |      timestamp     |
|  [INT]  |   [TEXT]    |   [TEXT]    |      [TEXT]      |     [TIMESTAMP]    |
+---------+-------------+-------------+------------------+--------------------+
|    1    | "voice_abc" | "user"      | "Olá, status?"   | 2025-12-18 10:30:01|
|    2    | "voice_abc" | "assistant" | "Sistemas online" | 2025-12-18 10:30:05|
+---------+-------------+-------------+------------------+--------------------+
```

- **`session_id`**: Agrupa mensagens por sessão (voz usa `voice_<token>`; chat usa UUID gerado pelo frontend)
- **`role`**: `user` ou `assistant`
- **`content`**: Transcrição integral da mensagem

---

### 3. Tabela `sessions` (Metadados de Sessões)

Armazena título, estado de pin e timestamp de cada sessão de chat.

```text
+----------------+-------------------+-----------+---------------------+
|  id (PK)       |      title        | is_pinned |     created_at      |
|   [TEXT]       |      [TEXT]       |   [INT]   |     [TIMESTAMP]     |
+----------------+-------------------+-----------+---------------------+
| "session-uuid" | "Conversa sobre X"|     0     | 2025-12-18 10:00:00 |
+----------------+-------------------+-----------+---------------------+
```

- **`id`**: UUID gerado pelo frontend
- **`title`**: Título editável pelo usuário via `update_session_title()`
- **`is_pinned`**: `0` ou `1` — sessões fixadas aparecem primeiro na sidebar

---

### 4. Tabela `config` (Configuração de Runtime)

Estado de features e skills que deve persistir entre reinicializações.

```text
+---------------------+----------+---------------------+
|       key (PK)      |  value   |     updated_at      |
|        [TEXT]       |  [TEXT]  |     [TIMESTAMP]     |
+---------------------+----------+---------------------+
| "skill_OPEN_APP"    | "true"   | 2025-12-18 10:00:00 |
| "skill_AUDIO_CTRL"  | "false"  | 2025-12-18 10:01:00 |
+---------------------+----------+---------------------+
```

- Usado por `is_skill_enabled()` em `services/intent.py`
- Modificado via `services/skill_settings.set_enabled()` (comando `/skills on|off` na TUI)

---

## ⚙️ Funcionamento Integrado

1. **Inicialização Automática**: `DatabaseManager` cria arquivo e tabelas no boot se não existirem (`settings.DB_PATH`)
2. **Lógica de UPSERT**: `save_memory()` usa `ON CONFLICT(key) DO UPDATE` — sem erros de duplicata
3. **Observabilidade**: Todas as transações reportadas ao `logger.py` — escritas em DEBUG, falhas em ERROR/CRITICAL
4. **Ciclo de Vida no `main.py`**:
   - Boot: consulta `user_name` para saudação personalizada
   - Input: grava comando reconhecido imediatamente
   - Output: grava resposta antes da síntese de voz

## 🛠️ Especificações Técnicas

- **Motor**: SQLite3 nativo
- **Encoding**: UTF-8
- **Localização**: `backend/database/jarvis_memory.db` (definida em `config.py`)
