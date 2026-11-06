"""Boot do Ollama — ensure_ollama_running sonda a API e, se o servidor local
estiver offline, roda `ollama serve` e espera a API responder. Nunca propaga erro."""
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.ollama_server as srv


class TestHelpers(unittest.TestCase):
    def test_base_url_normalizes_scheme_and_slash(self):
        self.assertEqual(srv._base_url("localhost:11434/"), "http://localhost:11434")
        self.assertEqual(srv._base_url("http://127.0.0.1:11434"), "http://127.0.0.1:11434")

    def test_is_local_host(self):
        self.assertTrue(srv.is_local_host("http://localhost:11434"))
        self.assertTrue(srv.is_local_host("127.0.0.1:11434"))
        self.assertTrue(srv.is_local_host("http://0.0.0.0:11434"))
        self.assertFalse(srv.is_local_host("http://192.168.0.10:11434"))

    def test_is_running_true_on_http_200(self):
        resp = MagicMock(status=200)
        resp.__enter__.return_value = resp
        with patch.object(srv._opener, "open", return_value=resp) as opened:
            self.assertTrue(srv.is_ollama_running("http://localhost:11434"))
        self.assertEqual(opened.call_args[0][0], "http://localhost:11434/api/version")

    def test_is_running_false_when_refused(self):
        err = urllib.error.URLError(ConnectionRefusedError())
        with patch.object(srv._opener, "open", side_effect=err):
            self.assertFalse(srv.is_ollama_running("http://localhost:11434"))

    def test_find_executable_falls_back_to_localappdata(self):
        with patch.object(srv.shutil, "which", return_value=None), \
             patch.dict(srv.os.environ, {"LOCALAPPDATA": r"C:\X"}), \
             patch.object(srv.os.path, "isfile", return_value=True):
            path = srv.find_ollama_executable()
        self.assertTrue(path.endswith("ollama.exe"))

    def test_start_server_runs_serve_detached(self):
        with patch.object(srv.subprocess, "Popen") as popen:
            srv.start_ollama_server("ollama")
        args, kwargs = popen.call_args
        self.assertEqual(args[0], ["ollama", "serve"])
        self.assertIs(kwargs["stdout"], srv.subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], srv.subprocess.DEVNULL)


class TestWaitUntilReady(unittest.TestCase):
    def test_returns_true_once_api_answers(self):
        with patch.object(srv, "is_ollama_running", side_effect=[False, False, True]), \
             patch.object(srv.time, "sleep"):
            self.assertTrue(srv.wait_until_ready(timeout=5, interval=0))

    def test_stops_early_if_process_dies(self):
        process = MagicMock()
        process.poll.return_value = 1
        with patch.object(srv, "is_ollama_running", return_value=False) as probe:
            self.assertFalse(srv.wait_until_ready(timeout=60, process=process))
        self.assertEqual(probe.call_count, 2)  # 1 sonda no laço + a última


class TestEnsureRunning(unittest.TestCase):
    def setUp(self):
        self.settings = patch.multiple(
            srv.settings, OLLAMA_HOST="http://localhost:11434",
            OLLAMA_AUTOSTART=True, OLLAMA_START_TIMEOUT=5,
        )
        self.settings.start()

    def tearDown(self):
        self.settings.stop()

    def test_already_running_does_not_start(self):
        with patch.object(srv, "is_ollama_running", return_value=True), \
             patch.object(srv, "start_ollama_server") as start:
            status, _ = srv.ensure_ollama_running()
        self.assertEqual(status, "running")
        start.assert_not_called()

    def test_offline_starts_server_and_waits(self):
        with patch.object(srv, "is_ollama_running", return_value=False), \
             patch.object(srv, "find_ollama_executable", return_value="ollama"), \
             patch.object(srv, "start_ollama_server") as start, \
             patch.object(srv, "wait_until_ready", return_value=True) as wait:
            status, _ = srv.ensure_ollama_running()
        self.assertEqual(status, "started")
        start.assert_called_once_with("ollama")
        self.assertEqual(wait.call_args[0][0], 5)  # usa OLLAMA_START_TIMEOUT

    def test_offline_and_not_installed(self):
        with patch.object(srv, "is_ollama_running", return_value=False), \
             patch.object(srv, "find_ollama_executable", return_value=None), \
             patch.object(srv, "start_ollama_server") as start:
            status, detail = srv.ensure_ollama_running()
        self.assertEqual(status, "failed")
        self.assertIn("não instalado", detail)
        start.assert_not_called()

    def test_server_never_answers(self):
        with patch.object(srv, "is_ollama_running", return_value=False), \
             patch.object(srv, "find_ollama_executable", return_value="ollama"), \
             patch.object(srv, "start_ollama_server"), \
             patch.object(srv, "wait_until_ready", return_value=False):
            status, _ = srv.ensure_ollama_running()
        self.assertEqual(status, "failed")

    def test_popen_error_is_swallowed(self):
        with patch.object(srv, "is_ollama_running", return_value=False), \
             patch.object(srv, "find_ollama_executable", return_value="ollama"), \
             patch.object(srv, "start_ollama_server", side_effect=OSError("denied")):
            status, _ = srv.ensure_ollama_running()
        self.assertEqual(status, "failed")

    def test_remote_host_is_not_started(self):
        with patch.object(srv.settings, "OLLAMA_HOST", "http://10.0.0.5:11434"), \
             patch.object(srv, "is_ollama_running", return_value=False), \
             patch.object(srv, "start_ollama_server") as start:
            status, _ = srv.ensure_ollama_running()
        self.assertEqual(status, "failed")
        start.assert_not_called()

    def test_autostart_disabled(self):
        with patch.object(srv.settings, "OLLAMA_AUTOSTART", False), \
             patch.object(srv, "is_ollama_running", return_value=False), \
             patch.object(srv, "start_ollama_server") as start:
            status, _ = srv.ensure_ollama_running()
        self.assertEqual(status, "failed")
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
