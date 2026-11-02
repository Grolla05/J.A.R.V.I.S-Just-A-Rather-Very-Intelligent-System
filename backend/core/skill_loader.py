import importlib.util
import os

from .logger import log


class SkillManager:
    def __init__(self):
        self.skills = {} 
        self.prompts = []

    def load_skills(self):
        skills_root = "skills"
        
        # os.walk percorre a árvore de diretórios (root, dirs, files)
        for root, dirs, files in os.walk(skills_root):
            for filename in files:
                if filename.endswith(".py") and filename != "__init__.py":
                    
                    # Caminho completo (ex: backend/skills/automation/app_control.py)
                    full_path = os.path.join(root, filename)
                    
                    # Nome único para o módulo (usamos o nome do arquivo)
                    module_name = filename[:-3] 
                    
                    try:
                        # Mágica de importação
                        spec = importlib.util.spec_from_file_location(module_name, full_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Anexa metadados de categoria e nome de arquivo
                        module.CATEGORY = os.path.basename(os.path.dirname(full_path))
                        module.FILE_NAME = filename
                        
                        # Verifica o Contrato (INTENT e execute)
                        if hasattr(module, "INTENT") and hasattr(module, "execute"):
                            intent_name = module.INTENT
                            self.skills[intent_name] = module
                            
                            if hasattr(module, "PROMPT_TEXT"):
                                self.prompts.append(module.PROMPT_TEXT)
                            
                            # Mostra de onde veio a skill para facilitar debug
                            log.debug(f"Skill '{intent_name}' carregada de {os.path.relpath(full_path, skills_root)}")

                    except Exception as e:
                        log.error(f"❌ Erro ao carregar skill em {full_path}: {e}")

        log.info("✅ Skills Carregadas com sucesso")
manager = SkillManager()
manager.load_skills()