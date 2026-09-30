import json
import threading
import time
from pathlib import Path

from .config import settings
from .logger import log
from .utils import escape_js


class JarvisAPI:
    """
    Ponte de comunicação Bidirecional:
    - Frontend -> Backend (Comandos do usuário)
    - Backend -> Frontend (Alertas proativos do sistema)
    """
    def __init__(self, system_monitor_instance):
        self.sys_monitor = system_monitor_instance
        self._window = None
        self._is_maximized = True
        self.boot_greeting_fn = None  # set by main.py after init
        self._telemetry_streaming = False
        self._last_telemetry = None  # {cpu, ram, gpu} do último push (delta gate)

    def set_window(self, window):
        """Referência da janela para comandos e notificações push"""
        self._window = window

    def on_initial_mode_selected(self, mode):
        """Called once when user picks a mode from the boot ModeSelectionScreen."""
        self.set_active_mode(mode)
        if mode == "talk" and callable(self.boot_greeting_fn):
            import threading
            threading.Thread(target=self.boot_greeting_fn, daemon=True).start()

    def set_active_mode(self, mode):
        """Muda o estado do ouvido baseado no modo ativo no frontend."""
        try:
            from services.listen import ear_pause, ear_resume
            if mode == "talk":
                ear_resume()
                log.info("Modo TALK ativado: Microfone LIGADO.")
            else:
                ear_pause()
                log.info(f"Modo {mode.upper()} ativado: Microfone MUTADO.")
        except ImportError as e:
            log.error(f"Erro ao importar controle de ouvido: {e}")

    # --- TELEMETRIA EM TEMPO REAL (Consumindo a instância compartilhada) ---
    def get_telemetry(self):
        """
        Retorna os dados de hardware para o LiveTelemetry.jsx.
        Usa o mesmo objeto que o cérebro usa, garantindo consistência.
        """
        try:
            return {
                "cpu": self.sys_monitor.get_cpu_detailed(),
                "ram": self.sys_monitor.get_ram_usage(),
                "gpu": self.sys_monitor.get_gpu_info(),
                "net": self.sys_monitor.get_network_speed(),
                "sys": self.sys_monitor.get_system_general(),
                "battery": self.sys_monitor.get_battery_status(),
                "disk": self.sys_monitor.get_disk_io(),
                "storage": self.sys_monitor.get_disk_space() # Adicionado o novo método
            }
        except Exception as e:
            log.error(f"Erro na ponte de telemetria: {e}")
            return None

    # --- TELEMETRIA PUSH (delta-gated, substitui o polling de 1s do frontend) ---
    def start_telemetry_stream(self, interval=None):
        """Inicia o loop que empurra telemetria à UI apenas quando há mudança
        relevante. Idempotente (não sobe dois loops)."""
        if self._telemetry_streaming:
            return
        self._telemetry_streaming = True
        interval = interval or settings.TELEMETRY_INTERVAL
        threading.Thread(target=self._telemetry_loop, args=(interval,), daemon=True).start()
        log.info(f"📡 Stream de telemetria push iniciado ({interval}s, delta-gated)")

    def _should_push(self, cpu, ram, gpu):
        """True se 1º envio ou se algum sensor cruzou seu threshold de delta."""
        last = self._last_telemetry
        if last is None:
            return True
        return (
            abs(cpu - last["cpu"]) > settings.TELEMETRY_CPU_DELTA
            or abs(ram - last["ram"]) > settings.TELEMETRY_RAM_DELTA
            or abs(gpu - last["gpu"]) > settings.TELEMETRY_GPU_DELTA
        )

    def _telemetry_loop(self, interval):
        while self._telemetry_streaming:
            try:
                data = self.get_telemetry()
                if data and self._window:
                    cpu = data["cpu"].get("usage", 0) or 0
                    ram = data["ram"].get("percent", 0) or 0
                    gpu = data["gpu"].get("load", 0) or 0
                    if self._should_push(cpu, ram, gpu):
                        self._last_telemetry = {"cpu": cpu, "ram": ram, "gpu": gpu}
                        # JSON válido é expressão JS válida — sem escape manual de string.
                        payload = json.dumps(data)
                        js = f"if(window.receiveTelemetry){{window.receiveTelemetry({payload})}}"
                        self._window.evaluate_js(js)
            except Exception as e:
                log.error(f"Erro no loop de telemetria push: {e}")
            time.sleep(interval)

    # --- NOTIFICAÇÃO PROATIVA (BACKEND -> UI) ---
    def send_frontend_alert(self, level, message):
        """
        Envia um evento para o React reagir sem o usuário pedir.
        Ex: Pulsar vermelho se level='CRITICAL'
        """
        if self._window:
            # Dispara um CustomEvent no JavaScript
            safe_level = escape_js(level)
            safe_message = escape_js(message)
            js_code = f"""
            window.dispatchEvent(new CustomEvent('JARVIS_SYS_ALERT', {{
                detail: {{ level: '{safe_level}', message: '{safe_message}' }}
            }}));
            """
            self._window.evaluate_js(js_code)
            log.info(f"⚡ Alerta enviado para UI: [{level}] {message}")

    # --- CONTROLE DE SISTEMA ---
    def shutdown(self):
        log.warning("Comando de desligamento recebido via UI.")
        if self._window:
            self._window.destroy()

    def minimize(self):
        if self._window:
            self._window.minimize()

    def toggle_maximize(self):
        if self._window:
            if self._is_maximized:
                self._window.restore()
                self._is_maximized = False
            else:
                self._window.maximize()
                self._is_maximized = True
            
    def set_hud_state(self, is_critical):
        """
        Sincroniza o estado de emergência do HUD (Vermelho/Azul).
        True = Ativa modo de alerta.
        False = Volta ao normal.
        """
        if self._window:
            state_js = "true" if is_critical else "false"
            # Chama uma função JS específica para alternar classes CSS
            js_code = f"if(window.updateHudState) {{ window.updateHudState({state_js}); }}"
            try:
                self._window.evaluate_js(js_code)
                log.info(f"Visual HUD State alterado para: {'CRITICO' if is_critical else 'NORMAL'}")
            except Exception as e:
                log.error(f"Falha ao atualizar HUD visual: {e}")

    # --- GERENCIAMENTO DE SKILLS DINÂMICAS ---
    def get_skills(self):
        """
        Retorna todas as skills disponíveis no backend catalogadas por categoria,
        com seus respectivos estados ativos/inativos de 1 para 1 e em grupo.
        """
        try:
            from core import db, manager
            disabled_skills = db.get_config("disabled_skills") or []
            disabled_categories = db.get_config("disabled_categories") or []
            
            result = []
            # Categorias mapeadas e estendidas com ícones e labels
            categories_map = {
                "automation": {"label": "Automation", "icon": "⚡"},
                "system": {"label": "System", "icon": "⚙️"},
                "IoT": {"label": "IoT Control", "icon": "🏠"},
                "productivity": {"label": "Productivity", "icon": "📅"},
                "web": {"label": "Web Intelligence", "icon": "🌐"}
            }
            
            for intent, module in manager.skills.items():
                cat_folder = getattr(module, "CATEGORY", "system")
                cat_info = categories_map.get(cat_folder, {"label": cat_folder.capitalize(), "icon": "⚙️"})
                
                category_enabled = cat_folder not in disabled_categories
                skill_enabled = intent not in disabled_skills and category_enabled
                
                skill_data = {
                    "id": intent,
                    "name": intent.replace("_", " ").title(),
                    "desc": getattr(module, "PROMPT_TEXT", "").split(":")[-1].strip() if hasattr(module, "PROMPT_TEXT") else "Rotina quântica de comandos.",
                    "fileName": getattr(module, "FILE_NAME", ""),
                    "enabled": skill_enabled,
                    "categoryEnabled": category_enabled,
                    "category": cat_folder
                }
                
                # Busca ou cria a categoria estrutural no resultado
                cat_item = next((item for item in result if item["id"] == cat_folder), None)
                if not cat_item:
                    cat_item = {
                        "id": cat_folder,
                        "label": cat_info["label"],
                        "icon": cat_info["icon"],
                        "enabled": category_enabled,
                        "skills": []
                    }
                    result.append(cat_item)
                
                cat_item["skills"].append(skill_data)
                
            return result
        except Exception as e:
            log.error(f"Erro ao buscar skills do backend: {e}")
            return []

    def toggle_skill(self, skill_id, enabled):
        """Liga ou desliga uma skill 1 a 1 no banco de dados SQLite."""
        try:
            from core import db
            disabled_skills = db.get_config("disabled_skills") or []
            if not enabled:
                if skill_id not in disabled_skills:
                    disabled_skills.append(skill_id)
            else:
                if skill_id in disabled_skills:
                    disabled_skills.remove(skill_id)
            db.save_config("disabled_skills", disabled_skills)
            log.info(f"Skill '{skill_id}' alternada para: {'ATIVA' if enabled else 'INATIVA'}")
            return True
        except Exception as e:
            log.error(f"Erro ao alternar ativação de skill '{skill_id}': {e}")
            return False

    def toggle_category(self, category_id, enabled):
        """Liga ou desliga um grupo de skills completo (categoria) no banco de dados SQLite."""
        try:
            from core import db
            disabled_categories = db.get_config("disabled_categories") or []
            if not enabled:
                if category_id not in disabled_categories:
                    disabled_categories.append(category_id)
            else:
                if category_id in disabled_categories:
                    disabled_categories.remove(category_id)
            db.save_config("disabled_categories", disabled_categories)
            log.info(f"Categoria de Skills '{category_id}' alternada para: {'ATIVA' if enabled else 'INATIVA'}")
            return True
        except Exception as e:
            log.error(f"Erro ao alternar ativação de categoria '{category_id}': {e}")
            return False

    def chat_message(self, text, session_id, images=None):
        """
        Recebe uma mensagem de texto do frontend (modo Chat), opcionalmente
        com imagens anexadas (lista de {'mime':..., 'data': base64, 'name':...}).
        Processa via execute_command_stream() e empurra a resposta de volta à UI em pedaços (streaming).
        Roda em thread separada para não bloquear a janela do pywebview.
        """
        import threading
        def _process():
            try:
                from core import db
                from core.uploads import save_base64_upload
                from services.brain import execute_command_stream

                log.info(f"💬 [CHAT STREAM] Mensagem recebida de Felipe na sessão '{session_id}': '{text}'")

                b64_list = []
                attachment_type = None
                attachment_path = None
                if images:
                    for idx, img in enumerate(images):
                        saved = save_base64_upload(
                            img.get("data", ""), img.get("mime", ""),
                            img.get("name") or f"imagem_{idx}.png", kind="image"
                        )
                        if saved:
                            b64_list.append(img["data"])
                            if attachment_path is None:
                                attachment_type = "image"
                                attachment_path = str(saved.relative_to(settings.DIR_UPLOADS))

                # Salva o log de interação do usuário (com referência ao anexo, se houver)
                db.log_interaction("user", text, session_id, attachment_type, attachment_path)

                full_response = ""
                is_first = True

                # Executa o processador cognitivo em stream com o session_id ativo
                for chunk in execute_command_stream(text, session_id=session_id, images=b64_list or None):
                    full_response += chunk
                    
                    if self._window:
                        # Escapa caracteres especiais para a avaliação JS segura
                        safe_chunk = escape_js(chunk)
                        
                        # Dispara evento com chunk atual e indicação se é o primeiro chunk
                        js_code = f"if(window.receiveChatStream) {{ window.receiveChatStream('{safe_chunk}', {'true' if is_first else 'false'}, false); }}"
                        self._window.evaluate_js(js_code)
                        is_first = False
                
                # Salva o log de interação da resposta do JARVIS
                if full_response:
                    db.log_interaction("assistant", full_response, session_id)
                
                # Envia sinalizador de término
                if self._window:
                    js_code = "if(window.receiveChatStream) { window.receiveChatStream('', false, true); }"
                    self._window.evaluate_js(js_code)
                    
            except Exception as e:
                log.error(f"Erro no pipeline de processamento streaming do Chat: {e}")
                
        threading.Thread(target=_process, daemon=True).start()

    def transcribe_audio(self, audio_b64, mime_type, filename):
        """
        Recebe um áudio (base64, sem prefixo data:) do frontend, salva em
        disco, transcreve via Whisper local e retorna o texto diretamente —
        chamada síncrona, não passa pelo pipeline de chat/LLM. A UI preenche
        a caixa de texto com o resultado; não envia nada sozinho.

        A transcrição roda numa thread própria (join) para seguir a convenção
        do projeto de toda I/O pesada da JarvisAPI rodar em threading.Thread,
        mesmo retornando o resultado de forma síncrona pro callApi do frontend.
        """
        result = {"success": False, "error": "Falha desconhecida na transcrição."}

        def _process():
            try:
                from core.transcription import transcribe_audio_file
                from core.uploads import save_base64_upload

                saved = save_base64_upload(audio_b64, mime_type, filename, kind="audio")
                if not saved:
                    result["error"] = "Arquivo de áudio inválido ou tipo não suportado."
                    return

                text = transcribe_audio_file(str(saved))
                if text is None:
                    result["error"] = "Falha na transcrição do áudio."
                    return

                result["success"] = True
                result["text"] = text
                del result["error"]
            except Exception as e:
                log.error(f"Erro em transcribe_audio: {e}")
                result["error"] = str(e)

        t = threading.Thread(target=_process, daemon=True)
        t.start()
        t.join(timeout=settings.TIMEOUT_TRANSCRIPTION)
        return result

    def get_chat_history(self, session_id, limit=50):
        """
        Retorna o histórico de conversas do banco de dados para a sessão selecionada, formatado para a UI.
        """
        try:
            from core import db
            from core.uploads import read_upload_as_data_url
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, role, content, timestamp, attachment_type, attachment_path FROM history
                WHERE session_id = ?
                ORDER BY timestamp DESC LIMIT ?
            ''', (session_id, limit))
            rows = cursor.fetchall()
            conn.close()

            # Reverte para ordem cronológica
            rows.reverse()

            messages = []
            for row_id, role, content, timestamp, attachment_type, attachment_path in rows:
                try:
                    time_part = timestamp.split(' ')[1][:5] if ' ' in timestamp else ""
                except Exception:
                    time_part = ""

                message = {
                    "id": row_id,
                    "sender": "user" if role == "user" else "jarvis",
                    "text": content,
                    "time": time_part
                }

                if attachment_type == "image" and attachment_path:
                    data_url = read_upload_as_data_url(attachment_path)
                    if data_url:
                        display_name = Path(attachment_path).name.split("_", 1)[-1]
                        message["attachments"] = [{
                            "id": f"{row_id}-att",
                            "name": display_name,
                            "kind": "image",
                            "icon": "🖼️",
                            "glow": "purple",
                            "previewUrl": data_url,
                        }]

                messages.append(message)
            return messages
        except Exception as e:
            log.error(f"Erro ao recuperar histórico de chat para a sessão '{session_id}': {e}")
            return []

    def delete_history_from(self, session_id, message_id):
        """
        Apaga todos os logs de conversa de uma sessão a partir de um ID de mensagem específico no SQLite.
        """
        try:
            from core import db
            db.delete_history_from(session_id, message_id)
            log.info(f"Histórico da sessão '{session_id}' apagado a partir da mensagem '{message_id}'.")
            return True
        except Exception as e:
            log.error(f"Erro ao apagar histórico da sessão '{session_id}' a partir da mensagem '{message_id}': {e}")
            return False

    def update_history_message(self, message_id, new_content):
        """
        Atualiza o conteúdo de uma mensagem específica no banco de dados SQLite.
        """
        try:
            from core import db
            db.update_history_message(message_id, new_content)
            log.info(f"Mensagem '{message_id}' atualizada no banco de dados SQLite.")
            return True
        except Exception as e:
            log.error(f"Erro ao atualizar mensagem '{message_id}': {e}")
            return False

    def update_session_title(self, session_id, new_title):
        """
        Insere ou atualiza o título customizado de uma sessão no banco de dados SQLite.
        """
        try:
            from core import db
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sessions (id, title) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET title = excluded.title
            ''', (session_id, new_title))
            conn.commit()
            conn.close()
            log.info(f"Título da sessão '{session_id}' atualizado para: '{new_title}'")
            return True
        except Exception as e:
            log.error(f"Erro ao atualizar título da sessão '{session_id}': {e}")
            return False

    def toggle_session_pin(self, session_id, is_pinned):
        """
        Fixa ou desafixa uma sessão de chat no banco de dados SQLite.
        """
        try:
            from core import db
            conn = db._get_connection()
            cursor = conn.cursor()
            
            # Garante que temos um título para pinar
            cursor.execute('SELECT title FROM sessions WHERE id = ?', (session_id,))
            row = cursor.fetchone()
            if row:
                title = row[0]
            else:
                cursor.execute('''
                    SELECT content FROM history
                    WHERE session_id = ? AND role = 'user'
                    ORDER BY id ASC LIMIT 1
                ''', (session_id,))
                prompt_row = cursor.fetchone()
                title = prompt_row[0] if prompt_row else "Nova conversa"
            
            cursor.execute('''
                INSERT INTO sessions (id, title, is_pinned) VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET is_pinned = excluded.is_pinned
            ''', (session_id, title, 1 if is_pinned else 0))
            conn.commit()
            conn.close()
            log.info(f"Sessão '{session_id}' pin alternado para: {is_pinned}")
            return True
        except Exception as e:
            log.error(f"Erro ao alternar fixação da sessão '{session_id}': {e}")
            return False

    def get_recent_sessions(self, limit=12):
        """
        Retorna as últimas sessões textuais de chat reais gravadas no SQLite.
        O título da sessão e o estado de pinagem são extraídos do banco com
        fallback retrocompatível para o primeiro prompt de usuário enviado.
        """
        try:
            from core import db
            conn = db._get_connection()
            cursor = conn.cursor()
            
            # Busca IDs das sessões de chat reais mais recentes ordenados pela atividade
            cursor.execute('''
                SELECT h.session_id, MAX(h.timestamp) as last_active
                FROM history h
                WHERE h.session_id NOT LIKE 'voice_%'
                GROUP BY h.session_id
                ORDER BY last_active DESC
                LIMIT ?
            ''', (limit,))
            session_rows = cursor.fetchall()
            
            recent_sessions = []
            for s_id, _ in session_rows:
                # Tenta buscar metadados customizados salvos na tabela sessions
                cursor.execute('SELECT title, is_pinned FROM sessions WHERE id = ?', (s_id,))
                session_row = cursor.fetchone()
                
                if session_row:
                    title = session_row[0]
                    is_pinned = bool(session_row[1])
                else:
                    # Fallback para o primeiro prompt do usuário
                    cursor.execute('''
                        SELECT content FROM history
                        WHERE session_id = ? AND role = 'user'
                        ORDER BY id ASC LIMIT 1
                    ''', (s_id,))
                    prompt_row = cursor.fetchone()
                    title = prompt_row[0] if prompt_row else "Nova conversa"
                    is_pinned = False
                    
                recent_sessions.append({
                    "id": s_id,
                    "title": title,
                    "is_pinned": is_pinned
                })
                
            conn.close()
            return recent_sessions
        except Exception as e:
            log.error(f"Erro ao obter sessões recentes: {e}")
            return []