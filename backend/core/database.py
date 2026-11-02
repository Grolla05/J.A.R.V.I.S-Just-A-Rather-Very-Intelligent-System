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

        WAL + busy_timeout eliminam o 'database is locked' sob múltiplas threads
        (telemetria + brain + bridge). check_same_thread=False libera o acesso
        multi-thread (cada chamada abre/fecha sua própria conexão).
        """
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            return conn
        except sqlite3.Error as e:
            log.critical(f"Falha catastrófica ao conectar ao banco de dados: {e}")
            raise

    @contextmanager
    def connection(self):
        """Context manager: garante commit/rollback/close sem try/finally manual.

        Uso: `with db.connection() as conn:` → commita ao sair; faz rollback e
        propaga em caso de erro SQL; sempre fecha (evita travar o loop PyWebView).
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

                # Cria índice na coluna session_id para consultas super rápidas (agora que a coluna 100% existe)
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_session ON history(session_id)')

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
        if not isinstance(value, str):
            value = json.dumps(value)

        try:
            with self.connection() as conn:
                conn.execute('''
                    INSERT INTO config (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value,
                        updated_at=CURRENT_TIMESTAMP
                ''', (key, value))
            log.debug(f"Config persistida: [{key}]")
        except sqlite3.Error as e:
            log.error(f"Falha ao salvar config '{key}': {e}")

    def get_config(self, key: str) -> Optional[Any]:
        try:
            with self.connection() as conn:
                result = conn.execute('SELECT value FROM config WHERE key = ?', (key,)).fetchone()
            if result:
                data = result[0]
                try:
                    return json.loads(data)
                except Exception:
                    return data
            return None
        except sqlite3.Error as e:
            log.error(f"Erro ao ler config '{key}': {e}")
            return None

    # --- MÉTODOS DE HISTÓRICO ---
    def log_interaction(self, role: str, content: str, session_id: str = 'default',
                         attachment_type: Optional[str] = None, attachment_path: Optional[str] = None):
        try:
            with self.connection() as conn:
                conn.execute(
                    'INSERT INTO history (role, content, session_id, attachment_type, attachment_path) VALUES (?, ?, ?, ?, ?)',
                    (role, content, session_id, attachment_type, attachment_path)
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