import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Optional

from .config import settings
from .logger import log


class DatabaseManager:
    """Gerencia a persistência de dados do JARVIS (Memória de Longo Prazo e Identidade)."""
    
    def __init__(self):
        self.db_path = settings.DB_PATH
        self._initialize_tables()

    def _get_connection(self):
        """Cria uma conexão robusta com o banco de dados.

        busy_timeout (por conexão) + WAL (gravado no arquivo uma vez, em
        `_initialize_tables`) eliminam o 'database is locked' sob múltiplas
        threads (telemetria + TUI + workers). check_same_thread=False libera o
        acesso multi-thread (cada chamada abre/fecha sua própria conexão).
        """
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA busy_timeout=5000")
            return conn
        except sqlite3.Error as e:
            log.critical(f"Falha catastrófica ao conectar ao banco de dados: {e}")
            raise

    @contextmanager
    def connection(self):
        """Context manager: garante commit/rollback/close sem try/finally manual.

        Uso: `with db.connection() as conn:` → commita ao sair; faz rollback e
        propaga em caso de erro SQL; sempre fecha (evita conexões presas entre threads).
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize_tables(self):
        """Cria a estrutura de tabelas (Config, Histórico e Hardware)."""
        try:
            with self.connection() as conn:
                # WAL é persistente no arquivo: basta ligar uma vez, não a cada conexão.
                conn.execute("PRAGMA journal_mode=WAL")
                cursor = conn.cursor()
                # 1. Config (Estado da aplicação: skills ativas/inativas, preferências de UI)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS config (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 2. Histórico (Logs de Conversa com session_id)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL DEFAULT 'default',
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 3. Hardware (Identidade da Máquina)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS hardware (
                        component TEXT PRIMARY KEY,
                        description TEXT NOT NULL,
                        detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 4. Sessions (Título customizado e Fixação de Chats)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        is_pinned INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 5. Histórico do clipboard (services/clip_history.py) — digest único: recopiar só sobe o item
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS clipboard_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind TEXT NOT NULL,
                        content TEXT NOT NULL,
                        digest TEXT NOT NULL UNIQUE,
                        copied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 6. Lembretes por pedido (services/reminders.py) — due_at em hora local ISO
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reminders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        text TEXT NOT NULL,
                        due_at TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        fired_at TEXT
                    )
                ''')

                # 7. Softwares que o usuário manteve no Vigia de rede (services/net_trust.py)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS net_trusted_apps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        name_key TEXT NOT NULL,
                        exe TEXT NOT NULL DEFAULT '',
                        exe_key TEXT NOT NULL DEFAULT '',
                        kind TEXT,
                        reason TEXT,
                        decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(name_key, exe_key)
                    )
                ''')

                # 8. Apelidos de contato de e-mail confirmados (services/email_contacts.py)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS email_contacts (
                        alias TEXT PRIMARY KEY,
                        address TEXT NOT NULL,
                        last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 9. Web Watch: páginas, preços e repositórios vigiados (services/web_watch.py)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS web_watches (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind TEXT NOT NULL,
                        target TEXT NOT NULL,
                        label TEXT NOT NULL DEFAULT '',
                        target_price REAL,
                        last_value TEXT,
                        last_hash TEXT,
                        last_checked TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(kind, target)
                    )
                ''')

                # Migração automática e retrocompatível: garante que banco existente ganhe a coluna session_id
                cursor.execute("PRAGMA table_info(history)")
                columns = [col[1] for col in cursor.fetchall()]
                if "session_id" not in columns:
                    cursor.execute("ALTER TABLE history ADD COLUMN session_id TEXT NOT NULL DEFAULT 'default'")
                    log.info("Migração de banco executada: coluna 'session_id' adicionada à tabela history.")

                # Garante que bancos com a tabela antiga ganhem a coluna is_pinned
                cursor.execute("PRAGMA table_info(sessions)")
                session_cols = [col[1] for col in cursor.fetchall()]
                if "is_pinned" not in session_cols:
                    cursor.execute("ALTER TABLE sessions ADD COLUMN is_pinned INTEGER DEFAULT 0")
                    log.info("Migração de banco executada: coluna 'is_pinned' adicionada à tabela sessions.")

                # Anexos de chat (imagem/áudio) — colunas nullable, path relativo a DIR_UPLOADS
                cursor.execute("PRAGMA table_info(history)")
                columns = [col[1] for col in cursor.fetchall()]
                if "attachment_type" not in columns:
                    cursor.execute("ALTER TABLE history ADD COLUMN attachment_type TEXT")
                    log.info("Migração de banco executada: coluna 'attachment_type' adicionada à tabela history.")
                if "attachment_path" not in columns:
                    cursor.execute("ALTER TABLE history ADD COLUMN attachment_path TEXT")
                    log.info("Migração de banco executada: coluna 'attachment_path' adicionada à tabela history.")
                # Modo da TUI em que a mensagem foi trocada (chat/copilot) — mostrado nos save slots
                if "mode" not in columns:
                    cursor.execute("ALTER TABLE history ADD COLUMN mode TEXT")
                    log.info("Migração de banco executada: coluna 'mode' adicionada à tabela history.")

                # Tipo do valor de config: 0 = texto cru, 1 = JSON. NULL = linha antiga
                # (get_config mantém o comportamento legado de tentar json.loads).
                cursor.execute("PRAGMA table_info(config)")
                config_cols = [col[1] for col in cursor.fetchall()]
                if "is_json" not in config_cols:
                    cursor.execute("ALTER TABLE config ADD COLUMN is_json INTEGER")
                    log.info("Migração de banco executada: coluna 'is_json' adicionada à tabela config.")

                # Cria índice na coluna session_id para consultas super rápidas (agora que a coluna 100% existe)
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_session ON history(session_id)')
                # Histórico do chat para a IA: WHERE session_id ORDER BY id DESC
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_session_id ON history(session_id, id)')

                log.info("Banco de dados verificado (Tabelas: Config, History, Hardware, Sessions).")
        except sqlite3.Error as e:
            log.error(f"Erro ao criar estrutura do banco de dados: {e}")

    # --- MÉTODOS DE HARDWARE ---
    def update_hardware_spec(self, component: str, description: str):
        """
        Salva uma especificação de hardware.
        Ex: component='CPU', description='Intel Core i9-9900K'
        """
        try:
            with self.connection() as conn:
                conn.execute('''
                    INSERT INTO hardware (component, description, detected_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(component) DO UPDATE SET
                        description=excluded.description,
                        detected_at=CURRENT_TIMESTAMP
                ''', (component, description))
        except sqlite3.Error as e:
            log.error(f"Erro ao salvar spec de hardware '{component}': {e}")

    def get_system_specs(self) -> str:
        """
        Retorna todas as specs formatadas como um texto único para o Prompt do Sistema.
        """
        try:
            with self.connection() as conn:
                rows = conn.execute('SELECT component, description FROM hardware').fetchall()

            if not rows:
                return "Especificações de sistema ainda não catalogadas."

            # Formata bonito para o J.A.R.V.I.S ler
            specs_text = "ESPECIFICAÇÕES DO SISTEMA HOSPEDEIRO:\n"
            for component, desc in rows:
                specs_text += f"- {component}: {desc}\n"

            return specs_text
        except sqlite3.Error as e:
            log.error(f"Erro ao ler hardware: {e}")
            return "Erro ao recuperar especificações."

    # --- MÉTODOS DE CONFIG (Estado da aplicação: skills, preferências de UI) ---
    def save_config(self, key: str, value: Any):
        """Grava `value`. String vai crua (volta igual); o resto vai em JSON.

        O tipo fica em `is_json`, para "123", "true" ou "null" salvos como texto
        voltarem como texto em `get_config`.
        """
        if isinstance(value, str):
            stored, is_json = value, 0
        else:
            stored, is_json = json.dumps(value, ensure_ascii=False), 1

        try:
            with self.connection() as conn:
                conn.execute('''
                    INSERT INTO config (key, value, is_json, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value,
                        is_json=excluded.is_json,
                        updated_at=CURRENT_TIMESTAMP
                ''', (key, stored, is_json))
            log.debug(f"Config persistida: [{key}]")
        except sqlite3.Error as e:
            log.error(f"Falha ao salvar config '{key}': {e}")

    def get_config(self, key: str) -> Optional[Any]:
        try:
            with self.connection() as conn:
                result = conn.execute(
                    'SELECT value, is_json FROM config WHERE key = ?', (key,)
                ).fetchone()
        except sqlite3.Error as e:
            log.error(f"Erro ao ler config '{key}': {e}")
            return None
        if not result:
            return None
        data, is_json = result
        if is_json == 0:
            return data
        try:
            return json.loads(data)
        except (TypeError, ValueError):
            if is_json == 1:
                log.warning(f"Config '{key}' marcada como JSON, mas inválida; devolvendo texto.")
            return data  # linha antiga (is_json NULL) com texto que não é JSON

    # --- MÉTODOS DE HISTÓRICO ---
    def log_interaction(self, role: str, content: str, session_id: str = 'default',
                         attachment_type: Optional[str] = None, attachment_path: Optional[str] = None,
                         mode: Optional[str] = None):
        try:
            with self.connection() as conn:
                conn.execute(
                    'INSERT INTO history (role, content, session_id, attachment_type, attachment_path, mode) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (role, content, session_id, attachment_type, attachment_path, mode)
                )
        except sqlite3.Error as e:
            log.error(f"Falha ao registrar histórico para sessão '{session_id}': {e}")

    def delete_history_from(self, session_id: str, message_id: int):
        """Apaga todos os logs de conversa de uma sessão a partir de um ID de mensagem específico."""
        try:
            with self.connection() as conn:
                conn.execute('DELETE FROM history WHERE session_id = ? AND id >= ?', (session_id, message_id))
            log.info(f"Limpeza de histórico executada no SQLite: deletadas mensagens a partir de '{message_id}' na sessão '{session_id}'.")
        except sqlite3.Error as e:
            log.error(f"Falha ao deletar histórico para sessão '{session_id}' a partir de '{message_id}': {e}")

    def update_history_message(self, message_id: int, new_content: str):
        """Atualiza o conteúdo de uma mensagem específica no banco de dados."""
        try:
            with self.connection() as conn:
                conn.execute('UPDATE history SET content = ? WHERE id = ?', (new_content, message_id))
            log.info(f"Mensagem '{message_id}' atualizada no SQLite com o novo prompt.")
        except sqlite3.Error as e:
            log.error(f"Falha ao atualizar mensagem '{message_id}': {e}")

    def search_relevant_context(self, query: str, limit: int = 3):
        stop_words = ["qual", "voce", "sobre", "meu", "minha", "como", "quem", "jarvis"]
        search_terms = [w for w in query.split() if len(w) > 3 and w.lower() not in stop_words]

        if not search_terms: return []

        search_query = " OR ".join(["content LIKE ?" for _ in search_terms])
        params = [f"%{term}%" for term in search_terms] + [limit]

        try:
            with self.connection() as conn:
                return conn.execute(f"SELECT role, content FROM history WHERE ({search_query}) ORDER BY timestamp DESC LIMIT ?", params).fetchall()
        except Exception as e:
            log.error(f"Erro na busca de histórico: {e}")
            return []

# Instância Singleton global
db = DatabaseManager()