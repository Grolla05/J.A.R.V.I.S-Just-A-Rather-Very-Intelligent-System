import urllib.parse
from typing import Optional

import requests

from .config import settings
from .logger import log

# Subpasta de mem\u00f3ria dentro do projeto JARVIS no vault.
# N\u00e3o usa emoji para garantir compatibilidade total com urllib no Windows.
MEMORY_NOTE_PATH = "🚀 Projetos/J.A.R.V.I.S/Mem\u00f3ria/{key}.md"

# Ideias/brainstorms registrados pelo JARVIS (services/insights.py): uma nota por mês.
INSIGHTS_NOTE_PATH = "🧠 Brainstorms/J.A.R.V.I.S — Insights {month}.md"

MEMORY_SAVED = "saved"  # nota criada agora
MEMORY_KEPT = "kept"    # nota já existia: versão do vault mantida, valor novo descartado


class ObsidianClient:
    def __init__(self):
        self.base = settings.OBSIDIAN_HOST
        self.headers = {
            "Authorization": f"Bearer {settings.OBSIDIAN_API_KEY}",
            "Content-Type": "text/markdown"
        }

    def _send(self, method, path, **kwargs):
        """Request cru: None em 404 (nota não existe); levanta se o Obsidian estiver fora."""
        headers = kwargs.pop("headers", self.headers)
        r = requests.request(method, f"{self.base}{path}",
                             headers=headers, timeout=5, **kwargs)
        if r.status_code == 404:
            return None  # Nota não existe — comportamento normal
        r.raise_for_status()
        return r

    def _req(self, method, path, quiet=False, **kwargs):
        try:
            return self._send(method, path, **kwargs)
        except requests.RequestException as e:
            (log.debug if quiet else log.warning)(f"Obsidian inacessível: {e}")
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

    def search_scored(self, query: str, limit: int = 8) -> list:
        """[{'filename', 'score'}], maior score primeiro. Levanta se o Obsidian
        estiver fora (quem chama decide se avisa); [] = nenhum resultado."""
        encoded = urllib.parse.quote(query, safe="", encoding="utf-8")
        r = self._send("GET", f"/search/simple/?query={encoded}&contextLength=80")
        if not r:
            return []
        items = [{"filename": i.get("filename", ""), "score": float(i.get("score", 0) or 0)}
                 for i in r.json() if i.get("filename")]
        items.sort(key=lambda i: i["score"], reverse=True)
        return items[:limit]

    def search_results(self, query: str, limit: int = 8) -> list:
        """Busca estruturada p/ a tela /vault: [{'filename', 'score'}], maior score primeiro."""
        try:
            return self.search_scored(query, limit)
        except (requests.RequestException, ValueError) as e:
            log.warning(f"Obsidian inacessível: {e}")
            return []

    def list_dir(self, path: str = "") -> Optional[list]:
        """Itens de uma pasta do vault (pastas terminam com '/'). None se inacessível."""
        folder = path.strip("/")
        encoded = urllib.parse.quote(folder, safe="/", encoding="utf-8")
        r = self._req("GET", f"/vault/{encoded}/" if folder else "/vault/",
                      headers={**self.headers, "Accept": "application/json"})
        if not r:
            return None
        try:
            return sorted(r.json().get("files", []), key=lambda n: (not n.endswith("/"), n.lower()))
        except ValueError:
            return None

    def get_file(self, path: str, quiet: bool = False) -> Optional[str]:
        """Lê conteúdo de uma nota pelo caminho. quiet=True: Obsidian fora só vai ao log."""
        encoded = urllib.parse.quote(path, safe="", encoding="utf-8")
        r = self._req("GET", f"/vault/{encoded}", quiet=quiet)
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

    def save_memory(self, key: str, value: str) -> Optional[str]:
        """Escreve fato do usuário como nota Markdown — apenas se ainda não existir no vault.
        Nota já existente = usuário editou manualmente → não sobrescrever.

        Retorna MEMORY_SAVED (nota criada), MEMORY_KEPT (já existia; o valor novo foi
        descartado) ou None (falha ao gravar)."""
        if self.get_memory(key) is not None:
            log.info(f"Obsidian: nota '{key}' já existe, mantendo versão do vault.")
            return MEMORY_KEPT
        from datetime import datetime
        content = f"---\nkey: {key}\nupdated_at: {datetime.now().strftime('%Y-%m-%d')}\n---\n{value}\n"
        path = MEMORY_NOTE_PATH.format(key=key)
        encoded = urllib.parse.quote(path, safe="", encoding="utf-8")
        r = self._req("PUT", f"/vault/{encoded}", data=content.encode("utf-8"))
        return MEMORY_SAVED if r is not None else None

    def note_exists(self, path: str) -> Optional[bool]:
        """True/False, ou None se o Obsidian não respondeu (não dá para saber).
        `_req` devolve None tanto para 404 quanto para falha — aqui a diferença importa."""
        encoded = urllib.parse.quote(path, safe="", encoding="utf-8")
        try:
            r = requests.request("GET", f"{self.base}/vault/{encoded}", headers=self.headers, timeout=5)
        except requests.RequestException as e:
            log.warning(f"Obsidian inacessível: {e}")
            return None
        if r.status_code == 404:
            return False
        return True if r.status_code == 200 else None

    def append_note(self, path: str, text: str, header: str = "") -> bool:
        """Anexa `text` ao fim da nota; se ela ainda não existe, cria com `header` antes.
        Sempre POST (append do plugin): nunca reescreve o que já está na nota. Sem
        resposta do Obsidian não escreve nada e devolve False (quem chama enfileira)."""
        exists = self.note_exists(path)
        if exists is None:
            return False
        body = text if exists else f"{header}{text}"
        encoded = urllib.parse.quote(path, safe="", encoding="utf-8")
        return self._req("POST", f"/vault/{encoded}", data=body.encode("utf-8")) is not None


obsidian = ObsidianClient()


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


_search_warned = False


def _warn_vault_down(error):
    """Obsidian fora: avisa uma vez por sessão (WARNING vira notificação na TUI)."""
    global _search_warned
    (log.debug if _search_warned else log.warning)(f"⚠️ [VAULT] Busca indisponível: {str(error)[:160]}")
    _search_warned = True


def get_vault_context(command: str) -> tuple[str, str]:
    """
    Retorna (filename, content) do arquivo mais relevante no vault.
    Camada 1: keywords pessoais → lê Sobre mim.md diretamente.
    Camada 2: busca no vault → arquivo com maior score.
    Tudo pela API REST do plugin Local REST API (sem subprocesso por chamada).
    Retorna ("", "") se vault inacessível ou sem resultado.
    """
    cmd_lower = command.lower()

    # Camada 1: pergunta pessoal/identidade → perfil completo
    if any(kw in cmd_lower for kw in _PROFILE_KEYWORDS):
        log.info("🔍 [VAULT] Camada 1 — acesso direto ao perfil pessoal")
        content = obsidian.get_file(_PROFILE_FILE, quiet=True)
        if content:
            log.info(f"✅ [VAULT] Lendo: {_PROFILE_FILE}")
            extracted = extract_relevant_section(content, command)
            return (_PROFILE_FILE, extracted)
        log.info("[VAULT] Perfil não encontrado — descendo para Camada 2")

    # Camada 2: busca no vault
    words = cmd_lower.split()
    keywords = [w for w in words if w not in _STOPWORDS and len(w) > 3]
    search_query = " ".join(keywords[:4]) or command

    log.info(f"🔍 [VAULT] Camada 2 — buscando: '{search_query}'")
    try:
        results = obsidian.search_scored(search_query)
    except Exception as e:  # Obsidian fechado, porta/chave errada, resposta inválida
        _warn_vault_down(e)
        return ("", "")

    valid = [r for r in results if not r["filename"].startswith("_templates")] or results
    if valid:
        best = valid[0]  # search_scored já ordena pelo score
        best_file = best["filename"]
        log.info(f"[VAULT] Melhor resultado (score={best['score']}): {best_file}")
        content = obsidian.get_file(best_file, quiet=True)
        if content:
            extracted = extract_relevant_section(content, command)
            log.info(f"✅ [VAULT] Contexto injetado ({len(extracted)} chars) de: {best_file}")
            return (best_file, extracted)
        log.warning(f"⚠️ [VAULT] '{best_file}' retornou conteúdo vazio.")

    log.info("🔍 [VAULT] Nenhum arquivo relevante encontrado.")
    return ("", "")
