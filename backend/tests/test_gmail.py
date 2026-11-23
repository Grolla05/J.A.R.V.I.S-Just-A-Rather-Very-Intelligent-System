"""core.google_auth + core.gmail — OAuth genérico, leitura, MIME, envio e organização. HTTP fake."""
import base64
import email
import os
import tempfile
import unittest
from email import policy
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import gmail, google_auth  # noqa: E402


class Resp:
    def __init__(self, status=200, data=None, text=""):
        self.status_code, self._data, self.text = status, data if data is not None else {}, text

    def json(self):
        return self._data


def _b64(text):
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode().rstrip("=")


MSG = {
    "id": "m1", "threadId": "t1", "labelIds": ["INBOX", "UNREAD", "IMPORTANT"], "snippet": "Segue a prova",
    "payload": {"headers": [
        {"name": "From", "value": "Prof. Ana <ana@uni.br>"},
        {"name": "Subject", "value": "Prova amanhã"},
        {"name": "Date", "value": "Mon, 23 Nov 2026 10:00:00 -0300"},
        {"name": "Message-ID", "value": "<abc@uni.br>"},
    ]},
}


class TestParse(unittest.TestCase):
    def test_parse_message_headers_and_flags(self):
        msg = gmail.parse_message(MSG)
        self.assertEqual((msg["id"], msg["thread_id"]), ("m1", "t1"))
        self.assertEqual((msg["from_name"], msg["from_addr"]), ("Prof. Ana", "ana@uni.br"))
        self.assertEqual(msg["subject"], "Prova amanhã")
        self.assertEqual(msg["message_id"], "<abc@uni.br>")
        self.assertTrue(msg["unread"])
        self.assertIn("IMPORTANT", msg["labels"])

    def test_extract_body_prefers_plain_and_falls_back_to_html(self):
        plain = {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>oi <b>html</b></p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("oi texto")}}]}
        self.assertEqual(gmail.extract_body(plain), "oi texto")
        html = {"mimeType": "text/html", "body": {"data": _b64("<p>Olá <b>mundo</b></p><script>x()</script>")}}
        body = gmail.extract_body(html)
        self.assertIn("Olá", body)
        self.assertIn("mundo", body)
        self.assertNotIn("<p>", body)
        self.assertNotIn("x()", body)

    def test_valid_address(self):
        self.assertTrue(gmail.valid_address("guilherme@empresa.com.br"))
        for bad in ("", "guilherme", "a@b", "x@y.com, z@w.com", "a b@c.com"):
            self.assertFalse(gmail.valid_address(bad), bad)


class TestMime(unittest.TestCase):
    def _decode(self, raw):
        return email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)), policy=policy.default)

    def test_new_message_utf8(self):
        raw = gmail.build_mime("gui@x.com", "Proposta", "Olá, Guilherme! Ação.")
        msg = self._decode(raw)
        self.assertEqual(msg["To"], "gui@x.com")
        self.assertIn("Olá, Guilherme! Ação.", msg.get_payload(decode=True).decode("utf-8"))

    def test_reply_sets_thread_headers(self):
        raw = gmail.build_mime("ana@uni.br", "Prova amanhã", "Confirmo.", reply_to=gmail.parse_message(MSG))
        msg = self._decode(raw)
        self.assertEqual(msg["Subject"], "Re: Prova amanhã")
        self.assertEqual(msg["In-Reply-To"], "<abc@uni.br>")
        self.assertIn("<abc@uni.br>", msg["References"])
        raw2 = gmail.build_mime("ana@uni.br", "Re: Prova", "ok", reply_to={**gmail.parse_message(MSG),
                                                                              "subject": "Re: Prova"})
        self.assertEqual(self._decode(raw2)["Subject"], "Re: Prova")   # não duplica "Re:"

    def test_attachment(self):
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.write(fd, "proposta comercial".encode("utf-8"))
        os.close(fd)
        try:
            msg = self._decode(gmail.build_mime("gui@x.com", "Proposta", "Segue.", attachments=[path]))
            parts = [p for p in msg.walk() if p.get_filename()]
            self.assertEqual(len(parts), 1)
            self.assertEqual(parts[0].get_filename(), os.path.basename(path))
            self.assertEqual(parts[0].get_payload(decode=True), "proposta comercial".encode("utf-8"))
        finally:
            os.remove(path)

    def test_invalid_recipient_raises_gmail_error(self):
        with self.assertRaises(gmail.GmailError):
            gmail.build_mime("guilherme", "x", "y")


class ApiCase(unittest.TestCase):
    def setUp(self):
        self.http = MagicMock()
        self._patches = [patch.object(google_auth, "_requests", return_value=self.http),
                         patch.object(gmail.account, "access_token", return_value="tok")]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()


class TestApi(ApiCase):
    def test_inbox_lists_and_fetches_metadata(self):
        self.http.request.side_effect = [Resp(data={"messages": [{"id": "m1"}]}), Resp(data=MSG)]
        items = gmail.inbox(max_results=5)
        self.assertEqual(items[0]["subject"], "Prova amanhã")
        first = self.http.request.call_args_list[0]
        self.assertEqual(first.args[0], "GET")
        self.assertEqual(first.kwargs["params"]["maxResults"], 5)
        self.assertEqual(first.kwargs["headers"]["Authorization"], "Bearer tok")

    def test_403_insufficient_scope_asks_to_reconnect(self):
        self.http.request.return_value = Resp(403, text="Request had insufficient authentication scopes.")
        with self.assertRaises(gmail.GmailError) as ctx:
            gmail.inbox()
        self.assertIn("Reconecte", str(ctx.exception))

    def test_send_and_draft_bodies(self):
        self.http.request.return_value = Resp(data={"id": "sent1"})
        gmail.send("RAW", thread_id="t1")
        args = self.http.request.call_args
        self.assertEqual(args.args[0], "POST")
        self.assertTrue(args.args[1].endswith("/messages/send"))
        self.assertEqual(args.kwargs["json"], {"raw": "RAW", "threadId": "t1"})
        gmail.save_draft("RAW")
        args = self.http.request.call_args
        self.assertTrue(args.args[1].endswith("/drafts"))
        self.assertEqual(args.kwargs["json"], {"message": {"raw": "RAW"}})

    def test_batch_modify_and_never_delete(self):
        self.http.request.return_value = Resp(204)
        gmail.batch_modify(["m1", "m2"], add=["L1"], remove=["INBOX"])
        args = self.http.request.call_args
        self.assertTrue(args.args[1].endswith("/messages/batchModify"))
        self.assertEqual(args.kwargs["json"], {"ids": ["m1", "m2"], "addLabelIds": ["L1"],
                                               "removeLabelIds": ["INBOX"]})
        self.assertFalse(hasattr(gmail, "delete"))   # exclusão permanente não existe (só Lixeira)

    def test_trash_moves_each_message_and_never_deletes(self):
        self.http.request.return_value = Resp(data={"id": "m1", "labelIds": ["TRASH"]})
        self.assertEqual(gmail.trash(["m1", "m2"]), 2)
        calls = self.http.request.call_args_list
        self.assertEqual([c.args[0] for c in calls], ["POST", "POST"])
        self.assertTrue(calls[0].args[1].endswith("/messages/m1/trash"))
        self.assertTrue(calls[1].args[1].endswith("/messages/m2/trash"))
        self.assertEqual(gmail.trash([]), 0)
        for c in calls:
            self.assertNotIn("delete", c.args[1])

    def test_ensure_label_reuses_or_creates(self):
        self.http.request.side_effect = [Resp(data={"labels": [{"id": "L9", "name": "JARVIS/Urgente"}]})]
        self.assertEqual(gmail.ensure_label("JARVIS/Urgente"), "L9")
        gmail._label_cache.clear()
        self.http.request.side_effect = [Resp(data={"labels": []}), Resp(data={"id": "L10"})]
        self.assertEqual(gmail.ensure_label("JARVIS/Financeiro"), "L10")
        self.assertEqual(self.http.request.call_args.kwargs["json"]["name"], "JARVIS/Financeiro")

    def test_find_contacts_groups_by_address(self):
        def meta(i, sender):
            return Resp(data={"id": i, "threadId": i, "labelIds": [],
                              "payload": {"headers": [{"name": "From", "value": sender},
                                                      {"name": "To", "value": "eu@x.com"}]}})
        self.http.request.side_effect = [
            Resp(data={"messages": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}),
            meta("a", "Guilherme Souza <gui@empresa.com>"), meta("b", "Guilherme Souza <gui@empresa.com>"),
            meta("c", "Guilherme Lima <glima@outra.com>")]
        found = gmail.find_contacts("Guilherme")
        self.assertEqual([c["address"] for c in found], ["gui@empresa.com", "glima@outra.com"])
        self.assertEqual(found[0]["count"], 2)


class TestAccount(unittest.TestCase):
    def test_authorize_url_has_scopes_and_offline(self):
        acc = google_auth.GoogleAccount(["s1", "s2"], "x_secret", "Teste")
        with patch.object(google_auth.settings, "GOOGLE_CLIENT_ID", "cid"):
            url = acc.build_authorize_url("http://127.0.0.1:1/", "chal", "st")
        self.assertIn("scope=s1+s2", url)
        self.assertIn("access_type=offline", url)
        self.assertIn("client_id=cid", url)

    def test_not_connected_raises_friendly_error(self):
        acc = google_auth.GoogleAccount(["s"], "x_secret", "Teste", error_cls=gmail.GmailError,
                                        not_connected="Gmail desconectado")
        with patch.object(google_auth.secrets_store, "get", return_value=None):
            self.assertFalse(acc.is_connected())
            with self.assertRaises(gmail.GmailError) as ctx:
                acc.access_token()
        self.assertIn("desconectado", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
