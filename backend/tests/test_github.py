"""core.github_client + skill GITHUB — PyGithub mockado, sem rede."""
import importlib.util
import os
import sys
import time
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.state as state  # noqa: E402
from core import github_client  # noqa: E402
from core.config import settings  # noqa: E402

_SKILL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "skills", "productivity", "github_control.py")


def _load_skill():
    spec = importlib.util.spec_from_file_location("github_control", _SKILL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class GitHubCase(unittest.TestCase):
    def setUp(self):
        self._token, self._repo = settings.GITHUB_TOKEN, settings.GITHUB_DEFAULT_REPO
        settings.GITHUB_TOKEN = "tok"
        settings.GITHUB_DEFAULT_REPO = "dono/repo"
        self.gh = MagicMock()
        self.gh.get_user.return_value.login = "felipe"
        github_client._client.update(gh=self.gh, token="tok")
        state.pending_critical_action = None

    def tearDown(self):
        settings.GITHUB_TOKEN, settings.GITHUB_DEFAULT_REPO = self._token, self._repo
        github_client._client.update(gh=None, token=None)
        state.pending_critical_action = None


class TestClient(GitHubCase):
    def test_without_token(self):
        settings.GITHUB_TOKEN = ""
        self.assertEqual(github_client.open_prs(), github_client.NO_TOKEN)
        self.assertIsNone(github_client.summary())

    def test_repo_name_resolution(self):
        self.assertEqual(github_client._repo_name(None), "dono/repo")
        self.assertEqual(github_client._repo_name("outro/x"), "outro/x")
        self.assertEqual(github_client._repo_name("solo"), "felipe/solo")
        settings.GITHUB_DEFAULT_REPO = ""
        self.assertEqual(github_client.open_prs(), github_client.NO_REPO)

    def test_open_prs_lists(self):
        pr = SimpleNamespace(number=7, html_url="https://gh/pr/7", title="Nova skill",
                             user=SimpleNamespace(login="ana"), draft=True)
        repo = self.gh.get_repo.return_value
        repo.full_name = "dono/repo"
        repo.get_pulls.return_value = [pr]
        out = github_client.open_prs()
        self.gh.get_repo.assert_called_with("dono/repo")
        self.assertIn("#7", out)
        self.assertIn("Nova skill", out)
        self.assertIn("rascunho", out)

    def test_open_prs_empty(self):
        self.gh.get_repo.return_value.get_pulls.return_value = []
        self.assertIn("Nenhum PR aberto", github_client.open_prs())

    def test_last_commit(self):
        author = SimpleNamespace(name="Felipe", date=datetime(2026, 11, 8, 9, 30))
        commit = SimpleNamespace(sha="abcdef123", html_url="u",
                                 commit=SimpleNamespace(message="feat: x\n\ncorpo", author=author))
        repo = self.gh.get_repo.return_value
        repo.full_name, repo.default_branch = "dono/repo", "main"
        repo.get_commits.return_value = [commit]
        out = github_client.last_commit()
        self.assertIn("abcdef1", out)
        self.assertIn("feat: x", out)
        self.assertNotIn("corpo", out)

    def test_http_errors_are_translated(self):
        err = Exception("bad creds")
        err.status = 401
        self.gh.get_repo.side_effect = err
        self.assertIn("recusou o token", github_client.ci_status())

    def test_create_issue(self):
        issue = SimpleNamespace(number=12, html_url="https://gh/i/12", title="Bug")
        repo = self.gh.get_repo.return_value
        repo.full_name = "dono/repo"
        repo.create_issue.return_value = issue
        out = github_client.create_issue("dono/repo", "Bug", "corpo")
        repo.create_issue.assert_called_once_with(title="Bug", body="corpo")
        self.assertIn("#12", out)
        self.assertIn("sem título", github_client.create_issue("dono/repo", "  "))

    def test_summary(self):
        self.gh.search_issues.return_value.totalCount = 2
        self.assertIn("2 PR(s)", github_client.summary())

    def test_run_read_unknown(self):
        self.assertIn("desconhecida", github_client.run_read("deploy"))

    def test_get_client_builds_with_token(self):
        github_client._client.update(gh=None, token=None)
        fake = MagicMock()
        with patch.dict(sys.modules, {"github": fake}):
            github_client.get_client()
        fake.Auth.Token.assert_called_once_with("tok")
        fake.Github.assert_called_once()


class TestSkill(GitHubCase):
    def setUp(self):
        super().setUp()
        self.skill = _load_skill()

    def test_parse_fast(self):
        p = self.skill.parse_fast
        self.assertEqual(p("quantos PRs abertos eu tenho?")["action"], "open_prs")
        self.assertEqual(p("qual foi meu último commit no dono/x?"),
                         {"action": "last_commit", "repo": "dono/x"})
        self.assertEqual(p("como está o CI?")["action"], "ci")
        self.assertEqual(p("minhas issues")["action"], "issues")
        created = p("cria uma issue: corrigir o boot no dono/x")
        self.assertEqual(created["action"], "create_issue")
        self.assertEqual(created["title"], "corrigir o boot")
        self.assertEqual(created["repo"], "dono/x")
        self.assertIsNone(p("me conta uma piada"))

    def test_without_token(self):
        settings.GITHUB_TOKEN = ""
        self.assertEqual(self.skill.execute(None, "meus PRs"), github_client.NO_TOKEN)

    def test_read_action_routes(self):
        with patch.object(github_client, "run_read", return_value="lista") as run_read:
            self.assertEqual(self.skill.execute(None, "meus PRs"), "lista")
        run_read.assert_called_once_with("open_prs", None)

    def test_llm_fallback(self):
        with patch("core.llm.query_ollama", return_value='{"action": "ci", "repo": null}'), \
             patch.object(github_client, "run_read", return_value="ci ok") as run_read:
            self.assertEqual(self.skill.execute(None, "deu bom lá no github?"), "ci ok")
        run_read.assert_called_once_with("ci", None)

    def test_llm_garbage(self):
        with patch("core.llm.query_ollama", return_value="não sei"):
            self.assertIn("Não entendi", self.skill.execute(None, "algo no github"))

    def test_create_issue_waits_for_confirmation(self):
        from services.brain import confirm_pending_action
        with patch.object(github_client, "create_issue", return_value="criada") as create:
            out = self.skill.execute(None, "cria uma issue: testar o jarvis")
            create.assert_not_called()
            self.assertIn("testar o jarvis", out)
            pending = state.pending_critical_action
            self.assertEqual(pending["type"], "GITHUB_CREATE_ISSUE")
            self.assertGreater(pending["timeout"], time.time())
            self.assertEqual(confirm_pending_action(True), "criada")
        create.assert_called_once_with("dono/repo", "testar o jarvis", "")
        self.assertIsNone(state.pending_critical_action)

    def test_create_issue_denied(self):
        from services.brain import confirm_pending_action
        with patch.object(github_client, "create_issue") as create:
            self.skill.execute(None, "cria uma issue: x y z")
            self.assertIsNone(confirm_pending_action(False))
        create.assert_not_called()

    def test_create_issue_without_title(self):
        self.assertIn("título", self.skill.execute(None, "cria uma issue"))
        self.assertIsNone(state.pending_critical_action)


if __name__ == "__main__":
    unittest.main()
