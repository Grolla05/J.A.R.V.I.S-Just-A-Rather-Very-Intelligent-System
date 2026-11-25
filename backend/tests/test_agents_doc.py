"""AGENTS.md enxuto: tamanho sob controle, seções essenciais e links para docs/ válidos."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
DOCS = ROOT / "docs"

# Links Markdown `[texto](alvo)`; alvos com espaço não existem no projeto.
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")

MAX_AGENTS_LINES = 150

ESSENTIAL_SECTIONS = (
    "## O que é este projeto",
    "## Instalação de dependências",
    "## Como rodar o projeto",
    "## Como rodar os testes",
    "## Workflow obrigatório de desenvolvimento",
)

# Cada tema que saiu do AGENTS.md mora em um destes arquivos.
EXPECTED_DOCS = (
    "agente-residente.md",
    "alertas.md",
    "arquitetura.md",
    "banco-de-dados.md",
    "decisoes-arquiteturais.md",
    "estrutura.md",
    "fluxos.md",
    "integracoes-oauth.md",
    "personalidade.md",
    "politica-de-privacidade.md",
    "regras-backend.md",
    "skills.md",
    "termos-de-uso.md",
    "tui.md",
    "variaveis-ambiente.md",
)

# Comandos que quem abre o AGENTS.md precisa achar sem sair dele.
ESSENTIAL_COMMANDS = (
    "pip install -r requirements.txt",
    "python main.py",
    "python -m pytest",
    "ruff check .",
)


def _local_links(path):
    """Alvos locais (sem http/mailto/âncora pura) dos links do arquivo, já resolvidos."""
    targets = []
    for raw in LINK_RE.findall(path.read_text(encoding="utf-8")):
        if raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        targets.append((raw, (path.parent / raw.split("#", 1)[0]).resolve()))
    return targets


class AgentsDocTests(unittest.TestCase):
    def test_agents_e_enxuto(self):
        lines = AGENTS.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), MAX_AGENTS_LINES,
                             f"AGENTS.md com {len(lines)} linhas: mova o excesso para docs/")

    def test_secoes_essenciais(self):
        text = AGENTS.read_text(encoding="utf-8")
        for section in ESSENTIAL_SECTIONS:
            self.assertIn(section, text, f"falta a seção '{section}' no AGENTS.md")

    def test_comandos_essenciais(self):
        text = AGENTS.read_text(encoding="utf-8")
        for command in ESSENTIAL_COMMANDS:
            self.assertIn(command, text, f"falta o comando '{command}' no AGENTS.md")

    def test_links_do_agents_existem(self):
        for raw, target in _local_links(AGENTS):
            self.assertTrue(target.exists(), f"AGENTS.md aponta para '{raw}', que não existe")

    def test_agents_linka_todos_os_docs(self):
        linked = {target for _, target in _local_links(AGENTS)}
        for name in EXPECTED_DOCS:
            self.assertIn((DOCS / name).resolve(), linked, f"AGENTS.md não linka docs/{name}")

    def test_docs_existem_e_nao_sao_vazios(self):
        for name in EXPECTED_DOCS:
            path = DOCS / name
            self.assertTrue(path.is_file(), f"docs/{name} não existe")
            self.assertGreater(len(path.read_text(encoding="utf-8").strip()), 200, f"docs/{name} vazio")

    def test_links_dos_docs_existem(self):
        for path in sorted(DOCS.glob("*.md")):
            for raw, target in _local_links(path):
                self.assertTrue(target.exists(), f"{path.name} aponta para '{raw}', que não existe")


if __name__ == "__main__":
    unittest.main()
