import asyncio
import json
import urllib.parse
from typing import Optional

import requests

from .config import settings
from .logger import log

# Subpasta de mem\u00f3ria dentro do projeto JARVIS no vault.
# N\u00e3o usa emoji para garantir compatibilidade total com urllib no Windows.
MEMORY_NOTE_PATH = "Projetos/J.A.R.V.I.S/Mem\u00f3ria/{key}.md"


class ObsidianClient:
    def __init__(self):
        self.base = settings.OBSIDIAN_HOST
        self.headers = {
            "Authorization": f"Bearer {settings.OBSIDIAN_API_KEY}",
            "Content-Type": "text/markdown"
        }

    def _req(self, method, path, **kwargs):
        try:
            r = requests.request(method, f"{self.base}{path}",
                                 headers=self.headers, timeout=5, **kwargs)
            if r.status_code == 404:
                return None  # Nota não existe — comportamento normal
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            log.warning(f"Obsidian inacessível: {e}")
            return None

    def search(self, query: str, limit: int = 5) -> str:
        """Busca no vault e retorna trechos relevantes concatenados."""
        encoded = urllib.parse.quote(query, safe="", encoding="utf-8")
        r = self._req("GET", f"/search/simple/?query={encoded}&contextLength=200")
        if not r:
            return ""
        results = r.json()[:limit]
        parts = []
        for item in results:
            fname = item.get("filename", "")
            for m in item.get("matches", [])[:2]:
                ctx = m.get("context", "")
                if ctx:
                    parts.append(f"[{fname}]: {ctx}")
        return "\n".join(parts)

    def get_file(self, path: str) -> Optional[str]:
        """Lê conteúdo de uma nota pelo caminho."""
        encoded = urllib.parse.quote(path, safe="", encoding="utf-8")
        r = self._req("GET", f"/vault/{encoded}")
        return r.text if r else None

    def get_memory(self, key: str) -> Optional[str]:
        """Lê fato do usuário de Projetos/JARVIS/Memoria/{key}.md"""
        content = self.get_file(MEMORY_NOTE_PATH.format(key=key))
        if not content:
            return None
        lines = content.strip().split("\n")
        in_front = False
        for line in lines:
            if line.strip() == "---":
                in_front = not in_front
                continue
            if not in_front and line.strip():
                return line.strip()
        return None

    def save_memory(self, key: str, value: str) -> bool:
        """Escreve fato do usuário como nota Markdown — apenas se ainda não existir no vault.
        Nota já existente = usuário editou manualmente → não sobrescrever."""
        if self.get_memory(key) is not None:
            log.info(f"Obsidian: nota '{key}' já existe, mantendo versão do vault.")
            return True
        from datetime import datetime
        content = f"---\nkey: {key}\nupdated_at: {datetime.now().strftime('%Y-%m-%d')}\n---\n{value}\n"
        path = MEMORY_NOTE_PATH.format(key=key)
        encoded = urllib.parse.quote(path, safe="", encoding="utf-8")
        r = self._req("PUT", f"/vault/{encoded}", data=content.encode("utf-8"))
        return r is not None


obsidian = ObsidianClient()


class ObsidianMCPClient:
    """Acesso completo ao vault via MCP usando stdio e uvx."""

    def __init__(self):
        self._tools_cache = None
        import os

        from mcp.client.stdio import StdioServerParameters
        
        env = os.environ.copy()
        env["OBSIDIAN_API_KEY"] = settings.OBSIDIAN_API_KEY
        
        # Prepara host e port a partir da string (ex: http://127.0.0.1:27123 ou 127.0.0.1)
        host_str = settings.OBSIDIAN_HOST.replace("http://", "").replace("https://", "").strip()
        if ":" in host_str:
            host, port = host_str.split(":", 1)
        else:
            host = host_str
            port = "27123" # Porta padrao do Local REST API se não fornecida
        env["OBSIDIAN_HOST"] = host
        env["OBSIDIAN_PORT"] = port

        self._server_params = StdioServerParameters(
            command="uvx",
            args=["mcp-obsidian"],
            env=env
        )

    def _run(self, coro):
        try:
            return asyncio.run(coro)
        except RuntimeError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()

    async def _list_tools(self) -> list:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        async with stdio_client(self._server_params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                result = await session.list_tools()
                return result.tools

    async def _call_tool(self, name: str, args: dict) -> str:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        async with stdio_client(self._server_params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                result = await session.call_tool(name, args)
                return "\n".join(
                    c.text for c in result.content if hasattr(c, "text") and c.text
                )

    @property
    def tools(self) -> list:
        if self._tools_cache is None:
            try:
                self._tools_cache = self._run(self._list_tools())
                log.info(f"Obsidian MCP: {len(self._tools_cache)} ferramentas disponíveis.")
            except Exception as e:
                log.warning(f"Obsidian MCP: falha ao listar tools: {e}")
                self._tools_cache = []
        return self._tools_cache

    @property
    def tools_schema(self) -> str:
        return "\n".join(f"- {t.name}: {t.description}" for t in self.tools)

    def call(self, name: str, **kwargs) -> str:
        try:
            return self._run(self._call_tool(name, kwargs)) or ""
        except Exception as e:
            log.warning(f"Obsidian MCP call '{name}': {e}")
            return ""


mcp_client = ObsidianMCPClient()


# --- VAULT CONTEXT LOOKUP ---

_PROFILE_FILE = "⚙️ Configurações/🧠 Sobre mim.md"

_PROFILE_KEYWORDS = {
    "nome", "familia", "família", "pai", "mãe", "mae", "irmão", "irmao",
    "quem", "moro", "mora", "localização", "localizacao", "cidade", "fuso",
    "faculdade", "curso", "formação", "formacao", "semestre", "universidade",
    "trabalho", "estágio", "estagio", "empresa", "tuv",
    "linguagem", "programação", "programacao", "stack", "tecnologia",
    "hobby", "hobbies", "música", "musica", "jogo", "jogos", "instrumento", "guitarra",
    "setup", "monitor", "teclado", "mouse", "processador",
    "rotina", "horário", "horario", "objetivo", "meta",
    "linkedin", "github", "age", "nascimento", "identidade",
    "quem sou", "sobre mim", "perfil",
}

_SECTION_KEYWORDS: dict[str, list[str]] = {
    "família":    ["família", "familia", "pai", "mãe", "mae", "irmão", "irmao", "parente", "familiar"],
    "identidade": ["nome", "quem sou", "identidade", "nascimento", "idade"],
    "trabalho":   ["trabalho", "estágio", "estagio", "empresa", "tuv", "cargo"],
    "educação":   ["faculdade", "curso", "universidade", "semestre", "formação"],
    "setup":      ["monitor", "teclado", "mouse", "processador", "pc", "setup"],
    "hobbies":    ["hobby", "hobbies", "música", "musica", "guitarra", "jogo", "jogos"],
    "rotina":     ["rotina", "horário", "horario", "fuso", "cidade", "localização"],
    "contatos":   ["linkedin", "github", "email", "contato"],
}

_STOPWORDS = {
    "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "e", "ou", "que", "qual", "quais",
    "me", "meu", "minha", "meus", "minhas", "eu", "é", "para",
    "por", "com", "como", "quando", "onde", "sei", "sabe", "seria",
    "jarvis", "voce", "você",
}


def extract_relevant_section(content: str, query: str) -> str:
    """
    Extrai a seção mais relevante do markdown para a query.
    Mapeia keywords da query → seção do arquivo → retorna só aquela seção.
    Fallback: primeiros 2000 chars se nenhuma seção bater.
    """
    query_lower = query.lower()

    # Qual categoria de seção a query pede?
    target_keywords = None
    for _section, keywords in _SECTION_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            target_keywords = keywords
            break

    if not target_keywords:
        return content[:2000]

    # Parsear markdown em seções por headers (# / ##)
    lines = content.split('\n')
    sections: list[tuple[str, str]] = []
    current_header: str | None = None
    current_lines: list[str] = []

    for line in lines:
        if line.startswith('#'):
            if current_header is not None:
                sections.append((current_header, '\n'.join(current_lines)))
            current_header = line.lstrip('#').strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_header is not None:
        sections.append((current_header, '\n'.join(current_lines)))

    # Encontrar seção com maior overlap de keywords
    best_header, best_body, best_score = "", "", 0
    for header, body in sections:
        combined = (header + " " + body).lower()
        score = sum(1 for kw in target_keywords if kw in combined)
        if score > best_score:
            best_score = score
            best_header, best_body = header, body

    if best_score > 0:
        extracted = f"## {best_header}\n{best_body.strip()}"
        log.info(f"[VAULT EXTRACT] Seção '{best_header}' extraída (score={best_score}, {len(extracted)} chars)")
        return extracted

    return content[:2000]


def get_vault_context(command: str) -> tuple[str, str]:
    """
    Retorna (filename, content) do arquivo mais relevante no vault.
    Camada 1: keywords pessoais → lê Sobre mim.md diretamente.
    Camada 2: busca semântica → arquivo com maior score.
    Retorna ("", "") se vault inacessível ou sem resultado.
    """
    cmd_lower = command.lower()

    # Camada 1: pergunta pessoal/identidade → perfil completo
    if any(kw in cmd_lower for kw in _PROFILE_KEYWORDS):
        log.info("🔍 [VAULT] Camada 1 — acesso direto ao perfil pessoal")
        content = mcp_client.call("obsidian_get_file_contents", filepath=_PROFILE_FILE)
        if content:
            log.info(f"✅ [VAULT] Lendo: {_PROFILE_FILE}")
            extracted = extract_relevant_section(content, command)
            return (_PROFILE_FILE, extracted)
        log.warning("⚠️ [VAULT] Perfil não encontrado — descendo para Camada 2")

    # Camada 2: busca semântica no vault
    words = cmd_lower.split()
    keywords = [w for w in words if w not in _STOPWORDS and len(w) > 3]
    search_query = " ".join(keywords[:4]) or command

    log.info(f"🔍 [VAULT] Camada 2 — buscando: '{search_query}'")
    search_result_str = mcp_client.call("obsidian_simple_search", query=search_query)

    if search_result_str:
        try:
            results = json.loads(search_result_str)
            if results and isinstance(results, list):
                valid = [r for r in results if not r.get("filename", "").startswith("_templates")]
                if not valid:
                    valid = results

                best = max(valid, key=lambda r: r.get("score", -9999))
                best_file = best.get("filename", "")

                if best_file:
                    log.info(f"[VAULT] Melhor resultado (score={best.get('score', '?')}): {best_file}")
                    content = mcp_client.call("obsidian_get_file_contents", filepath=best_file)
                    if content:
                        extracted = extract_relevant_section(content, command)
                        log.info(f"✅ [VAULT] Contexto injetado ({len(extracted)} chars) de: {best_file}")
                        return (best_file, extracted)
                    log.warning(f"⚠️ [VAULT] '{best_file}' retornou conteúdo vazio.")
        except Exception as e:
            log.error(f"❌ [VAULT] Erro ao processar resultado: {e}")

    log.info("🔍 [VAULT] Nenhum arquivo relevante encontrado.")
    return ("", "")
