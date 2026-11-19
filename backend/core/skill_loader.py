"""Auto-discovery das skills (plug-and-play).

As skills ficam em `backend/skills/<categoria>/*.py` e são carregadas na
primeira vez que alguém lê `manager.skills` / `manager.prompts` (ou chama
`manager.ensure_loaded()`, que é o que a etapa de skills do boot faz). Importar
este módulo não executa nenhuma skill.
"""
import importlib.util
import os
import threading
from pathlib import Path

from .logger import log

# Absoluto: não depende do diretório de onde o JARVIS foi aberto.
SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"


class SkillManager:
    def __init__(self, skills_root=None):
        self.skills_root = Path(skills_root) if skills_root else SKILLS_ROOT
        self._skills = {}
        self._prompts = []
        self._loaded = False
        self._lock = threading.RLock()

    # Leitura preguiçosa: o 1º acesso carrega. Atribuir (testes) marca como carregado.
    @property
    def skills(self):
        self.ensure_loaded()
        return self._skills

    @skills.setter
    def skills(self, value):
        self._loaded = True
        self._skills = value

    @property
    def prompts(self):
        self.ensure_loaded()
        return self._prompts

    @prompts.setter
    def prompts(self, value):
        self._loaded = True
        self._prompts = value

    def ensure_loaded(self):
        """Carrega as skills uma única vez (thread-safe)."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            # Marca antes: uma skill que leia `manager` durante o import não recursa
            self._loaded = True
            self.load_skills()

    def load_skills(self):
        root_dir = self.skills_root
        if not root_dir.is_dir():
            log.warning(f"Pasta de skills não encontrada: {root_dir}")
            return

        # os.walk em ordem alfabética: com INTENT repetido, vence sempre o mesmo arquivo
        for root, dirs, files in os.walk(root_dir):
            dirs.sort()
            for filename in sorted(files):
                if not filename.endswith(".py") or filename == "__init__.py":
                    continue
                full_path = os.path.join(root, filename)
                module_name = filename[:-3]
                try:
                    spec = importlib.util.spec_from_file_location(module_name, full_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Anexa metadados de categoria e nome de arquivo
                    module.CATEGORY = os.path.basename(os.path.dirname(full_path))
                    module.FILE_NAME = filename

                    # Verifica o Contrato (INTENT e execute)
                    if not (hasattr(module, "INTENT") and hasattr(module, "execute")):
                        continue
                    intent_name = module.INTENT
                    existing = self._skills.get(intent_name)
                    if existing is not None:
                        log.warning(
                            f"INTENT duplicado '{intent_name}' em {os.path.relpath(full_path, root_dir)}; "
                            f"mantendo a skill de {getattr(existing, 'CATEGORY', '?')}/"
                            f"{getattr(existing, 'FILE_NAME', '?')}."
                        )
                        continue
                    self._skills[intent_name] = module
                    if hasattr(module, "PROMPT_TEXT"):
                        self._prompts.append(module.PROMPT_TEXT)
                    log.debug(f"Skill '{intent_name}' carregada de {os.path.relpath(full_path, root_dir)}")
                except Exception as e:
                    log.error(f"❌ Erro ao carregar skill em {full_path}: {e}")

        log.info(f"✅ {len(self._skills)} skills carregadas de {root_dir}")


manager = SkillManager()
