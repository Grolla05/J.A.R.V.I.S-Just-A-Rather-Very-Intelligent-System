"""core/uploads.py — documento anexado (texto, código, PDF) vira texto para o prompt."""
import io
import os
import shutil
import tempfile
import unittest

from tests._stubs import install

install()

from core import uploads  # noqa: E402


def _pdf_with_text(text):
    """PDF mínimo de uma página com `text` (Helvetica), gerado à mão."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


class TestLoadDocument(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _write(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_text_and_code(self):
        doc = uploads.load_document(self._write("main.py", b"print('ol\xc3\xa1')\r\n"))
        self.assertEqual((doc["kind"], doc["name"], doc["content"]), ("document", "main.py", "print('olá')"))
        self.assertFalse(doc["truncated"])

    def test_windows_1252_text(self):
        doc = uploads.load_document(self._write("notas.txt", "ação".encode("cp1252")))
        self.assertEqual(doc["content"], "ação")

    def test_pdf_text(self):
        doc = uploads.load_document(self._write("relatorio.pdf", _pdf_with_text("Receita anual 42")))
        self.assertIn("Receita anual 42", doc["content"])

    def test_scanned_or_broken_pdf(self):
        with self.assertRaises(ValueError):
            uploads.load_document(self._write("lixo.pdf", b"%PDF-1.4 quebrado"))

    def test_truncates_long_files(self):
        doc = uploads.load_document(self._write("big.log", b"x" * 50), max_chars=10)
        self.assertTrue(doc["truncated"])
        self.assertEqual((len(doc["content"]), doc["chars"]), (10, 50))

    def test_secrets_are_masked(self):
        text = b"usuario=felipe\nAPI_KEY = tk9aZ8bY7cX6dW5eV4fU3gT2hSqR7p\n"
        doc = uploads.load_document(self._write("config.ini", text))
        self.assertIn("usuario=felipe", doc["content"])
        self.assertNotIn("tk9aZ8bY7cX6dW5eV4fU3gT2hSqR7p", doc["content"])

    def test_refuses_sensitive_binary_empty_and_missing(self):
        for name, data in ((".env", b"A=1"), (".env.local", b"A=1"), ("chave.pem", b"-----BEGIN"),
                           ("id_rsa", b"x")):
            with self.assertRaises(ValueError):
                uploads.load_document(self._write(name, data))
        with self.assertRaises(ValueError):
            uploads.load_document(self._write("dados.txt", b"\x00\x01\x02"))
        with self.assertRaises(ValueError):
            uploads.load_document(self._write("vazio.md", b"  \n"))
        with self.assertRaises(ValueError):
            uploads.load_document(os.path.join(self.dir, "nao_existe.txt"))

    def test_load_any_routes_by_type(self):
        self.assertEqual(uploads.load_any(self._write("a.md", b"# oi"))["kind"], "document")
        with self.assertRaises(ValueError) as ctx:
            uploads.load_any(self._write("a.zip", b"PK"))
        self.assertIn("PDF", str(ctx.exception))
        self.assertTrue(uploads.is_document("Dockerfile"))
        self.assertFalse(uploads.is_document("foto.png"))


if __name__ == "__main__":
    unittest.main()
