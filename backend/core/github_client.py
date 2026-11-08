"""Integração com o GitHub via PyGithub (token pessoal no .env).

Leitura: PRs abertos, issues atribuídas, último commit, status do CI, resumo
para o briefing. Escrita: só `create_issue` — e quem chama (skill / TUI) é
responsável por pedir confirmação antes.

Funções devolvem Markdown pronto para a TUI; erros viram mensagem amigável +
log, nunca exceção para cima. `github` é importado tardiamente (custo de boot).
"""
from itertools import islice

from core.config import settings
from core.logger import log

NO_TOKEN = ("GitHub não configurado, Senhor. Gere um token em github.com/settings/tokens "
            "e coloque em `GITHUB_TOKEN` no `.env`.")
NO_REPO = "Qual repositório, Senhor? Diga `dono/repo` ou defina `GITHUB_DEFAULT_REPO` no `.env`."
LIST_LIMIT = 8

_client = {"gh": None, "token": None}


def _take(paginated, limit):
    """Primeiros `limit` itens de uma PaginatedList. Não use `[:n]`: no PyGithub
    2.x fatiar uma lista vazia lança IndexError."""
    return list(islice(paginated, limit))


class GitHubError(Exception):
    """Erro já traduzido para o usuário."""


def is_configured():
    return bool(settings.GITHUB_TOKEN)


def get_client():
    token = settings.GITHUB_TOKEN
    if not token:
        raise GitHubError(NO_TOKEN)
    if _client["gh"] is None or _client["token"] != token:
        from github import Auth, Github
        _client["gh"] = Github(auth=Auth.Token(token), timeout=settings.TIMEOUT_API)
        _client["token"] = token
    return _client["gh"]


def _repo_name(repo):
    name = (repo or settings.GITHUB_DEFAULT_REPO or "").strip().strip("/")
    if not name:
        raise GitHubError(NO_REPO)
    if "/" not in name:  # só o nome: assume o usuário dono do token
        name = f"{get_client().get_user().login}/{name}"
    return name


def _repo(repo):
    return get_client().get_repo(_repo_name(repo))


def _safe(fn):
    """Converte qualquer falha em texto para o usuário."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except GitHubError as e:
            return str(e)
        except Exception as e:
            log.warning(f"[GITHUB] {fn.__name__} falhou: {e}")
            status = getattr(e, "status", None)
            if status == 401:
                return "O GitHub recusou o token, Senhor. Confira o `GITHUB_TOKEN`."
            if status == 404:
                return "Repositório não encontrado — ou o token não tem acesso a ele."
            return f"O GitHub não colaborou desta vez: `{e}`"
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


@_safe
def open_prs(repo=None):
    """PRs abertos do repositório."""
    r = _repo(repo)
    pulls = _take(r.get_pulls(state="open", sort="updated", direction="desc"), LIST_LIMIT)
    if not pulls:
        return f"Nenhum PR aberto em **{r.full_name}**. Paz rara, Senhor."
    lines = [f"**{len(pulls)} PR(s) aberto(s) em {r.full_name}:**", ""]
    for pr in pulls:
        draft = " _(rascunho)_" if getattr(pr, "draft", False) else ""
        lines.append(f"- [#{pr.number}]({pr.html_url}) {pr.title} — `{pr.user.login}`{draft}")
    return "\n".join(lines)


@_safe
def my_issues():
    """Issues abertas atribuídas ao dono do token (todos os repositórios)."""
    issues = _take(get_client().get_user().get_issues(state="open", filter="assigned"), LIST_LIMIT)
    if not issues:
        return "Nenhuma issue aberta atribuída ao Senhor. Suspeito, mas aceito."
    lines = [f"**{len(issues)} issue(s) atribuída(s):**", ""]
    for issue in issues:
        lines.append(f"- [{issue.repository.full_name}#{issue.number}]({issue.html_url}) {issue.title}")
    return "\n".join(lines)


@_safe
def last_commit(repo=None):
    """Último commit do branch padrão."""
    r = _repo(repo)
    commits = _take(r.get_commits(), 1)
    if not commits:
        return f"**{r.full_name}** ainda não tem commits, Senhor."
    commit = commits[0]
    info = commit.commit
    title = ((info.message or "").splitlines() or ["(sem mensagem)"])[0]
    when = info.author.date.strftime("%d/%m %H:%M") if info.author and info.author.date else "?"
    author = info.author.name if info.author else "?"
    return (f"Último commit em **{r.full_name}** (`{r.default_branch}`):\n\n"
            f"[`{commit.sha[:7]}`]({commit.html_url}) {title} — {author}, {when}")


@_safe
def ci_status(repo=None):
    """Situação das últimas execuções do GitHub Actions."""
    r = _repo(repo)
    runs = _take(r.get_workflow_runs(), 5)
    if not runs:
        return f"Nenhuma execução de CI em **{r.full_name}**."
    icon = {"success": "✓", "failure": "✗", "cancelled": "■", None: "…"}
    lines = [f"**CI de {r.full_name}:**", ""]
    for run in runs:
        mark = icon.get(run.conclusion, "•")
        lines.append(f"- {mark} [{run.name}]({run.html_url}) `{run.head_branch}` — {run.conclusion or run.status}")
    return "\n".join(lines)


@_safe
def create_issue(repo, title, body=""):
    """Cria a issue (a confirmação é responsabilidade de quem chama)."""
    title = (title or "").strip()
    if not title:
        return "Uma issue sem título, Senhor? Nem o GitHub aceita isso."
    r = _repo(repo)
    issue = r.create_issue(title=title, body=body or "")
    log.info(f"[GITHUB] Issue criada: {r.full_name}#{issue.number}")
    return f"Issue criada: [{r.full_name}#{issue.number}]({issue.html_url}) {issue.title}"


def summary():
    """Linhas curtas para o briefing. Sem token / erro → None (briefing ignora)."""
    if not is_configured():
        return None
    try:
        gh = get_client()
        login = gh.get_user().login
        reviews = gh.search_issues(f"is:open is:pr review-requested:{login}").totalCount
        mine = gh.search_issues(f"is:open is:pr author:{login}").totalCount
        issues = gh.search_issues(f"is:open is:issue assignee:{login}").totalCount
        return f"{mine} PR(s) seus abertos, {reviews} aguardando sua revisão, {issues} issue(s) atribuída(s)"
    except Exception as e:
        log.warning(f"[GITHUB] Resumo indisponível: {e}")
        return None


READ_ACTIONS = {
    "open_prs": open_prs,
    "last_commit": last_commit,
    "ci": ci_status,
}


def run_read(action, repo=None):
    """Despacha uma ação de leitura pelo nome ('issues' não usa repo)."""
    if action == "issues":
        return my_issues()
    fn = READ_ACTIONS.get(action)
    if fn is None:
        return "Ação do GitHub desconhecida. Tente: prs, issues, commit ou ci."
    return fn(repo)
