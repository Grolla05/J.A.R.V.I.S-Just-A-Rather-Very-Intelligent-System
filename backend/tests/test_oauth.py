"""core.oauth — PKCE, validade do token e espera do callback no loopback."""
import base64
import hashlib
import unittest
import urllib.parse

from tests._stubs import install

install()

import core.oauth as oauth  # noqa: E402


class _FakeServer:
    """Simula o HTTPServer: cada handle_request entrega o próximo redirect da fila."""

    def __init__(self, paths):
        self.paths = list(paths)
        self.closed = False
        self.timeout = None
        self.handler = None

    def factory(self, _addr, handler):
        self.handler = handler
        return self

    def handle_request(self):
        if not self.paths:
            return
        path = self.paths.pop(0)
        handler = self.handler.__new__(self.handler)
        handler.path = path
        handler.send_response = lambda *_a: None
        handler.send_header = lambda *_a: None
        handler.end_headers = lambda: None
        handler.wfile = type("W", (), {"write": lambda _s, _b: None})()
        handler.do_GET()

    def server_close(self):
        self.closed = True


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 1.0
        return self.t


class TestPkce(unittest.TestCase):
    def test_challenge_is_sha256_of_verifier(self):
        verifier, challenge = oauth.build_pkce_pair()
        self.assertTrue(43 <= len(verifier) <= 128)
        digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        self.assertEqual(challenge, digest)

    def test_token_expired_with_margin(self):
        self.assertTrue(oauth.token_expired(None))
        self.assertTrue(oauth.token_expired(1_000_060, now=1_000_000))
        self.assertFalse(oauth.token_expired(1_000_061, now=1_000_000))


class TestWaitForCode(unittest.TestCase):
    def _wait(self, paths, state="abc", timeout=5):
        server = _FakeServer(paths)
        code = oauth.wait_for_code(state, 1234, timeout, server_factory=server.factory, clock=_Clock())
        self.assertTrue(server.closed)
        return code

    def test_returns_code_when_state_matches(self):
        self.assertEqual(self._wait(["/favicon.ico", "/?code=XYZ&state=abc"]), "XYZ")

    def test_state_mismatch_discards_code(self):
        self.assertIsNone(self._wait(["/?code=XYZ&state=outro"]))

    def test_user_denied(self):
        self.assertIsNone(self._wait(["/?error=access_denied&state=abc"]))

    def test_timeout(self):
        self.assertIsNone(self._wait([], timeout=3))

    def test_busy_port(self):
        def boom(*_a):
            raise OSError("em uso")
        self.assertIsNone(oauth.wait_for_code("s", 1, 1, server_factory=boom))


class TestAuthorize(unittest.TestCase):
    def test_full_flow_passes_redirect_and_challenge(self):
        seen = {}

        def build_url(redirect_uri, challenge, state):
            seen.update(redirect=redirect_uri, challenge=challenge, state=state)
            return "https://provedor/auth?" + urllib.parse.urlencode({"state": state})

        def wait(state, port, timeout):
            seen["port"] = port
            return "CODE" if state == seen["state"] else None

        opened = []
        result = oauth.authorize(build_url, 30, open_browser=opened.append, wait=wait, port=5555)
        code, verifier, redirect = result
        self.assertEqual(code, "CODE")
        self.assertEqual(redirect, "http://127.0.0.1:5555")
        self.assertEqual(seen["port"], 5555)
        self.assertTrue(opened and opened[0].startswith("https://provedor/auth"))
        digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        self.assertEqual(seen["challenge"], digest)

    def test_returns_none_without_code(self):
        self.assertIsNone(oauth.authorize(lambda *a: "u", 1, open_browser=lambda u: None,
                                          wait=lambda *a: None, port=1))


if __name__ == "__main__":
    unittest.main()
