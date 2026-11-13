"""Atualização automática no logon: Release do GitHub, download conferido e setup."""
import hashlib
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import autostart, updater  # noqa: E402
from core.config import settings  # noqa: E402
from tests.test_hotkey_agent import FakeWinreg  # noqa: E402

REPO = "dono/jarvis"
PAYLOAD = b"setup-bytes" * 100
SHA = hashlib.sha256(PAYLOAD).hexdigest()
URL = f"https://github.com/{REPO}/releases/download/v1.2.0/JARVIS-Setup.exe"


# `requests` é stub (MagicMock) nos testes: exceções de verdade para o updater
class NetError(Exception):
    pass


class FakeRequests(types.SimpleNamespace):
    RequestException = NetError
    ConnectionError = NetError
    HTTPError = NetError


requests = FakeRequests()


class FakeResp:
    def __init__(self, status=200, data=None, body=b""):
        self.status_code = status
        self._data = data
        self._body = body

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, size):
        for i in range(0, len(self._body), 7):
            yield self._body[i:i + 7]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def release(tag="v1.2.0", url=URL, digest=f"sha256:{SHA}", size=len(PAYLOAD), name="JARVIS-Setup.exe", **extra):
    asset = {"name": name, "browser_download_url": url, "size": size}
    if digest is not None:
        asset["digest"] = digest
    return {"tag_name": tag, "assets": [asset], **extra}


def fake_get(api_data=None, api_status=200, body=PAYLOAD, fail_times=0):
    calls = {"api": 0}

    def get(url, **_kw):
        if url.startswith("https://api.github.com/"):
            calls["api"] += 1
            if calls["api"] <= fail_times:
                raise requests.ConnectionError("sem rede")
            return FakeResp(api_status, api_data)
        return FakeResp(200, body=body)
    get.calls = calls
    return get


class TestVersions(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("1.10.0"), (1, 10, 0))
        for bad in ("", "1.2", "0.0.0-dev", "vX.Y.Z", None):
            self.assertIsNone(updater.parse_version(bad))
        self.assertTrue(updater.is_newer("1.10.0", "1.9.9"))
        self.assertFalse(updater.is_newer("1.2.0", "1.2.0"))
        self.assertFalse(updater.is_newer("1.1.9", "1.2.0"))
        self.assertFalse(updater.is_newer("lixo", "1.0.0"))


class TestFetchLatest(unittest.TestCase):
    def test_valid_release(self):
        info = updater.fetch_latest(fake_get(release()), repo=REPO)
        self.assertEqual(info, {"version": "1.2.0", "url": URL, "size": len(PAYLOAD), "sha256": SHA})

    def test_no_release_or_asset(self):
        self.assertIsNone(updater.fetch_latest(fake_get(api_status=404), repo=REPO))
        self.assertIsNone(updater.fetch_latest(fake_get(release(name="outro.zip")), repo=REPO))
        self.assertIsNone(updater.fetch_latest(fake_get(release(prerelease=True)), repo=REPO))
        self.assertIsNone(updater.fetch_latest(fake_get(release(tag="nightly")), repo=REPO))

    def test_rejects_foreign_url_and_missing_digest(self):
        with self.assertRaises(updater.UpdateError):
            updater.fetch_latest(fake_get(release(url="https://evil.example/JARVIS-Setup.exe")), repo=REPO)
        with self.assertRaises(updater.UpdateError):
            updater.fetch_latest(fake_get(release(url=f"https://github.com/outro/{REPO}/releases/download/x")),
                                 repo=REPO)
        with self.assertRaises(updater.UpdateError):
            updater.fetch_latest(fake_get(release(digest=None)), repo=REPO)


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def info(self, **kw):
        return {"version": "1.2.0", "url": URL, "size": len(PAYLOAD), "sha256": SHA, **kw}

    def test_ok(self):
        path = updater.download(self.info(), self.dir, fake_get())
        self.assertEqual(path.read_bytes(), PAYLOAD)

    def test_hash_mismatch_deletes_file(self):
        with self.assertRaises(updater.UpdateError):
            updater.download(self.info(sha256="0" * 64), self.dir, fake_get())
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_size_mismatch(self):
        with self.assertRaises(updater.UpdateError):
            updater.download(self.info(size=3), self.dir, fake_get())
        self.assertEqual(list(self.dir.iterdir()), [])


class FakeReg(FakeWinreg):
    REG_DWORD = 4


class TestEnabled(unittest.TestCase):
    def test_registry_wins_over_env_default(self):
        reg = FakeReg()
        with patch.object(updater, "_winreg", return_value=reg), patch.object(settings, "AUTO_UPDATE", True):
            self.assertTrue(updater.is_enabled())          # sem valor: padrão do .env
            self.assertTrue(updater.set_enabled(False))
            self.assertFalse(updater.is_enabled())
            self.assertTrue(updater.set_enabled(True))
            self.assertTrue(updater.is_enabled())
        with patch.object(updater, "_winreg", return_value=None), patch.object(settings, "AUTO_UPDATE", False):
            self.assertFalse(updater.is_enabled())


class TestCheckAndUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(updater, "_requests", return_value=requests),
            patch.object(settings, "IS_INSTALLED", True),
            patch.object(settings, "DIR_DATA", Path(self.tmp.name)),
            patch.object(settings, "VERSION", "1.1.0"),
            patch.object(settings, "UPDATE_REPO", REPO),
            patch.object(updater, "is_enabled", return_value=True),
        ]
        for p in self.patches:
            p.start()
        self.notify = MagicMock()
        self.popen = MagicMock()
        self.sleeps = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def run_check(self, get, tui_open=False):
        return updater.check_and_update(self.notify, lambda: tui_open, self.sleeps.append, get=get, popen=self.popen)

    def test_dev_mode_does_nothing(self):
        get = fake_get(release())
        with patch.object(settings, "IS_INSTALLED", False):
            self.assertEqual(self.run_check(get), "dev")
        self.assertEqual(get.calls["api"], 0)

    def test_disabled(self):
        with patch.object(updater, "is_enabled", return_value=False):
            self.assertEqual(self.run_check(fake_get(release())), "disabled")

    def test_up_to_date(self):
        with patch.object(settings, "VERSION", "1.2.0"):
            self.assertEqual(self.run_check(fake_get(release())), "up-to-date")
        self.popen.assert_not_called()
        self.notify.assert_not_called()

    def test_offline_retries_then_gives_up(self):
        get = fake_get(release(), fail_times=99)
        self.assertEqual(self.run_check(get), "offline")
        self.assertEqual(self.sleeps, list(updater.RETRY_DELAYS))
        self.assertEqual(get.calls["api"], len(updater.RETRY_DELAYS) + 1)

    def test_network_comes_back(self):
        get = fake_get(release(), fail_times=2)
        self.assertEqual(self.run_check(get), "installing")
        self.assertEqual(self.sleeps, list(updater.RETRY_DELAYS[:2]))

    def test_deferred_when_tui_open(self):
        self.assertEqual(self.run_check(fake_get(release()), tui_open=True), "deferred")
        self.popen.assert_not_called()

    def test_installs_newer_release(self):
        self.assertEqual(self.run_check(fake_get(release())), "installing")
        argv = self.popen.call_args[0][0]
        self.assertTrue(argv[0].endswith("JARVIS-Setup-1.2.0.exe"))
        self.assertEqual(argv[1:], list(updater.SETUP_ARGS))
        self.assertIn("/UPDATE", argv)
        self.assertEqual(Path(argv[0]).read_bytes(), PAYLOAD)
        marker = json.loads((updater.updates_dir() / updater.MARKER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(marker, {"version": "1.2.0", "from": "1.1.0"})

    def test_bad_download_never_runs_setup(self):
        get = fake_get(release(), body=b"adulterado")
        self.assertEqual(self.run_check(get), "failed")
        self.popen.assert_not_called()
        self.assertFalse((updater.updates_dir() / updater.MARKER_NAME).exists())

    def test_invalid_release_fails_without_retry(self):
        get = fake_get(release(digest=None))
        self.assertEqual(self.run_check(get), "failed")
        self.assertEqual(get.calls["api"], 1)

    def test_old_setups_are_cleaned(self):
        updates = updater.updates_dir()
        updates.mkdir(parents=True)
        (updates / "JARVIS-Setup-1.0.0.exe").write_bytes(b"x")
        with patch.object(settings, "VERSION", "1.2.0"):
            self.run_check(fake_get(release()))
        self.assertFalse((updates / "JARVIS-Setup-1.0.0.exe").exists())

    def test_announce_result(self):
        notify = MagicMock()
        self.assertIsNone(updater.announce_result(notify))
        updater.updates_dir().mkdir(parents=True)
        marker = updater.updates_dir() / updater.MARKER_NAME
        marker.write_text(json.dumps({"version": "1.2.0"}), encoding="utf-8")
        with patch.object(settings, "VERSION", "1.2.0"):
            self.assertEqual(updater.announce_result(notify), "updated")
        self.assertFalse(marker.exists())
        self.assertIn("1.2.0", notify.call_args[0][0])
        marker.write_text(json.dumps({"version": "1.3.0"}), encoding="utf-8")
        self.assertEqual(updater.announce_result(MagicMock()), "not-updated")

    def test_successful_update_deletes_old_setup(self):
        updates = updater.updates_dir()
        updates.mkdir(parents=True)
        (updates / "JARVIS-Setup-1.2.0.exe").write_bytes(b"x")
        (updates / updater.CACHE_NAME).write_text("{}", encoding="utf-8")
        (updates / updater.MARKER_NAME).write_text(json.dumps({"version": "1.2.0"}), encoding="utf-8")
        with patch.object(settings, "VERSION", "1.2.0"):
            self.assertEqual(updater.announce_result(MagicMock()), "updated")
        self.assertEqual(list(updates.iterdir()), [])

    def test_install_latest_waits_for_tui_to_close(self):
        open_checks = iter([True, True, False])
        status = updater.install_latest(self.notify, lambda: next(open_checks, False), self.sleeps.append,
                                        get=fake_get(release()), popen=self.popen)
        self.assertEqual(status, "installing")
        self.assertEqual(self.sleeps, [1, 1])
        self.popen.assert_called_once()


class TestCheckAvailable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(updater, "_requests", return_value=requests),
            patch.object(settings, "IS_INSTALLED", True),
            patch.object(settings, "DIR_DATA", Path(self.tmp.name)),
            patch.object(settings, "VERSION", "1.1.0"),
            patch.object(settings, "UPDATE_REPO", REPO),
            patch.object(updater, "is_enabled", return_value=True),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_newer_release(self):
        self.assertEqual(updater.check_available(fake_get(release()), now=1000),
                         {"version": "1.2.0", "current": "1.1.0"})

    def test_same_or_older_is_not_offered(self):
        with patch.object(settings, "VERSION", "1.2.0"):
            self.assertIsNone(updater.check_available(fake_get(release()), now=1000))
        with patch.object(settings, "VERSION", "1.3.0"):  # distinta, mas mais velha: sem downgrade
            self.assertIsNone(updater.check_available(fake_get(release()), now=1000, use_cache=False))

    def test_cache_skips_github_until_ttl(self):
        get = fake_get(release())
        updater.check_available(get, now=1000)
        self.assertIsNotNone(updater.check_available(get, now=1000 + 60))
        self.assertEqual(get.calls["api"], 1)
        updater.check_available(get, now=1000 + updater.CACHE_TTL_S + 1)
        self.assertEqual(get.calls["api"], 2)

    def test_cache_from_older_install_is_ignored(self):
        get = fake_get(release())
        updater.check_available(get, now=1000)
        with patch.object(settings, "VERSION", "1.2.0"):  # acabou de atualizar
            self.assertIsNone(updater.check_available(get, now=1001))
        self.assertEqual(get.calls["api"], 2)

    def test_never_raises_and_respects_dev_and_toggle(self):
        self.assertIsNone(updater.check_available(fake_get(release(), fail_times=99), now=1000))
        self.assertIsNone(updater.check_available(fake_get(release(digest=None)), now=1000, use_cache=False))
        with patch.object(settings, "IS_INSTALLED", False):
            self.assertIsNone(updater.check_available(fake_get(release()), now=1000, use_cache=False))
        with patch.object(updater, "is_enabled", return_value=False):
            self.assertIsNone(updater.check_available(fake_get(release()), now=1000, use_cache=False))

    def test_retries_on_logon(self):
        sleeps = []
        get = fake_get(release(), fail_times=2)
        info = updater.check_available(get, now=1000, use_cache=False, retries=(15, 45, 90), sleep=sleeps.append)
        self.assertEqual(info["version"], "1.2.0")
        self.assertEqual(sleeps, [15, 45])


class TestRequestInstall(unittest.TestCase):
    def test_signal_reaches_running_agent(self):
        start = MagicMock()
        self.assertEqual(updater.request_install(lambda: True, start), "agent")
        start.assert_not_called()

    def test_spawns_agent_when_none_running(self):
        self.assertEqual(updater.request_install(lambda: False, lambda: True), "spawned")
        self.assertEqual(updater.request_install(lambda: False, lambda: False), "failed")

    def test_errors_become_failed(self):
        def boom():
            raise OSError("sem Win32")
        self.assertEqual(updater.request_install(boom, lambda: True), "failed")


class TestAgentWiring(unittest.TestCase):
    def setUp(self):
        import agent
        self.agent = agent

    def run_it(self, from_logon, available=None, tui_open=False):
        upd = MagicMock()
        upd.check_available.return_value = available
        launch = MagicMock()
        result = self.agent.run_update_check(from_logon, upd, MagicMock(), lambda: tui_open, lambda s: None, launch)
        return result, upd, launch

    def test_only_checks_on_logon(self):
        result, upd, launch = self.run_it(from_logon=False)
        self.assertIsNone(result)
        upd.announce_result.assert_called_once()
        upd.check_available.assert_not_called()
        launch.assert_not_called()

    def test_logon_with_update_opens_tui(self):
        info = {"version": "1.2.0", "current": "1.1.0"}
        result, upd, launch = self.run_it(from_logon=True, available=info)
        self.assertEqual(result, "prompted")
        launch.assert_called_once()
        self.assertFalse(upd.check_available.call_args.kwargs["use_cache"])
        result, _u, launch = self.run_it(from_logon=True, available=info, tui_open=True)
        self.assertEqual(result, "deferred")
        launch.assert_not_called()

    def test_logon_without_update_stays_quiet(self):
        result, _u, launch = self.run_it(from_logon=True, available=None)
        self.assertEqual(result, "no-update")
        launch.assert_not_called()

    def test_install_exits_agent_only_when_setup_runs(self):
        upd = MagicMock()
        for status, exits in (("installing", 1), ("failed", 0)):
            upd.install_latest.return_value = status
            exit_agent = MagicMock()
            self.assertEqual(self.agent.run_install(upd, MagicMock(), lambda: False, lambda s: None, exit_agent),
                             status)
            self.assertEqual(exit_agent.call_count, exits)

    def test_install_flag_matches_updater(self):
        self.assertEqual(self.agent.INSTALL_FLAG, updater.INSTALL_FLAG)


class TestAutostartLogonFlag(unittest.TestCase):
    def test_command_has_logon_flag(self):
        self.assertTrue(autostart.agent_command().endswith(" --logon"))

    def test_old_value_is_migrated(self):
        reg = FakeWinreg()
        with patch.object(autostart, "_winreg", return_value=reg):
            self.assertFalse(autostart.ensure_logon_flag())          # sem valor: não liga sozinho
            self.assertNotIn("JARVIS", reg.values)
            reg.values["JARVIS"] = '"pythonw.exe" "agent.py"'
            self.assertTrue(autostart.ensure_logon_flag())
            self.assertIn("--logon", reg.values["JARVIS"])
            self.assertFalse(autostart.ensure_logon_flag())          # já migrado


if __name__ == "__main__":
    unittest.main()
