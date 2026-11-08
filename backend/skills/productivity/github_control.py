"""Skill GITHUB — PRs, issues, último commit, CI e criação de issue (com confirmação).

Frases comuns são entendidas sem LLM (`parse_fast`); o resto vai ao Ollama com
`skills/github_decision.md` (JSON). Criar issue nunca executa direto: deixa a
ação em `state.pending_critical_action['on_confirm']` e pergunta — o "sim" (voz)
ou o ConfirmScreen da TUI (30 s) resolve via `brain.confirm_pending_action`.
"""
import json
import re
import time

import core.state as state
from core import github_client
from core.config import settings
from core.logger import log
from core.prompts import load_prompt

INTENT = "GITHUB"
PROMPT_TEXT = load_prompt("skills/github.md")

CONFIRM_TIMEOUT = 30  # s — igual ao ConfirmScreen
_REPO_RE = re.compile(r"\b([\w.-]+/[\w.-]+)\b")
_CREATE_RE = re.compile(r"\b(cria|crie|criar|abre|abra|abrir|nova|novo|registra|registre)\b.*\bissues?\b", re.I)


def _find_repo(text):
    match = _REPO_RE.search(text or "")
    return match.group(1) if match else None


def _issue_title(text):
    """Título depois de ':' (ou de 'issue'), sem o repositório."""
    _, sep, after = text.partition(":")
    if not sep:
        after = re.split(r"\bissues?\b", text, maxsplit=1, flags=re.I)[-1]
    after = re.sub(r"\b(no|em|in)\s+[\w.-]+/[\w.-]+", "", after)
    return after.strip(" .,-\"'")


def parse_fast(command):
    """Decisão sem LLM para as frases óbvias. None = deixa para o modelo."""
    text = (command or "").strip()
    low = text.lower()
    repo = _find_repo(text)
    if _CREATE_RE.search(low):
        return {"action": "create_issue", "repo": repo, "title": _issue_title(text), "body": ""}
    if re.search(r"\b(prs?|pull requests?)\b", low):
        return {"action": "open_prs", "repo": repo}
    if "commit" in low:
        return {"action": "last_commit", "repo": repo}
    if re.search(r"\b(ci|build|actions?|pipeline|workflow)\b", low):
        return {"action": "ci", "repo": repo}
    if re.search(r"\bissues?\b", low):
        return {"action": "issues", "repo": repo}
    return None


def _ask_llm(command):
    from core.llm import query_ollama
    prompt = load_prompt("skills/github_decision.md", command=command,
                         default_repo=settings.GITHUB_DEFAULT_REPO or "(nenhum)")
    raw = query_ollama([{"role": "user", "content": prompt}], format="json",
                       temperature=0, timeout=settings.TIMEOUT_API)
    try:
        return json.loads(raw) if raw else None
    except (TypeError, ValueError):
        log.warning(f"[GITHUB] Decisão inválida do modelo: {raw!r}")
        return None


def request_issue(repo, title, body=""):
    """Prepara a criação da issue e devolve a pergunta de confirmação."""
    title = (title or "").strip()
    if not title:
        return "Qual o título da issue, Senhor? Ex.: \"cria uma issue: corrigir o boot\"."
    try:
        repo_name = github_client._repo_name(repo)
    except github_client.GitHubError as e:
        return str(e)
    question = f"Criar a issue \"{title}\" em {repo_name}?"
    state.pending_critical_action = {
        "type": "GITHUB_CREATE_ISSUE",
        "target": repo_name,
        "question": question,
        "timeout": time.time() + CONFIRM_TIMEOUT,
        "on_confirm": lambda: github_client.create_issue(repo_name, title, body),
    }
    return f"{question} Diga **sim** para confirmar."


def execute(entity, command):
    if not github_client.is_configured():
        return github_client.NO_TOKEN
    decision = parse_fast(command) or _ask_llm(command) or {}
    action = decision.get("action")
    repo = decision.get("repo") or None
    if action == "create_issue":
        return request_issue(repo, decision.get("title") or entity, decision.get("body", ""))
    if action in ("open_prs", "issues", "last_commit", "ci"):
        return github_client.run_read(action, repo)
    return "Não entendi o que fazer no GitHub, Senhor. PRs, issues, último commit, CI ou criar issue?"
