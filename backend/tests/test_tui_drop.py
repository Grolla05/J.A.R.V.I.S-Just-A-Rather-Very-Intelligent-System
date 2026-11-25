"""TUI — arrastar arquivo para o terminal vira /attach."""
import os
import shutil
import tempfile
import unittest

from tests._stubs import install

install()

from textual import events  # noqa: E402

from frontend.commands import dropped_paths, is_image_path  # noqa: E402
from tests import test_tui_app as base  # noqa: E402  (módulo: o pytest não coleta de novo)

# PNG 1×1 válido — o load_local_file lê o arquivo de verdade.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def _make_dir(test):
    folder = tempfile.mkdtemp()
    test.addCleanup(shutil.rmtree, folder, True)
    return folder


def _write(folder, name, data=_PNG):
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


class TestDroppedPaths(unittest.TestCase):
    def setUp(self):
        self.dir = _make_dir(self)

    def test_caminho_simples(self):
        png = _write(self.dir, "foto.png")
        self.assertEqual(dropped_paths(png), [png])

    def test_caminho_com_aspas_e_espaco(self):
        png = _write(self.dir, "minha foto.png")
        self.assertEqual(dropped_paths(f'"{png}"'), [png])
        self.assertEqual(dropped_paths(png), [png])  # sem aspas, digitado à mão

    def test_varios_arquivos(self):
        a = _write(self.dir, "a b.png")
        b = _write(self.dir, "c.mp3", b"ID3")
        self.assertEqual(dropped_paths(f'"{a}" {b}'), [a, b])

    def test_arquivo_inexistente(self):
        self.assertEqual(dropped_paths(os.path.join(self.dir, "nada.png")), [])

    def test_qualquer_arquivo_existente_e_aceito(self):
        # texto, código, PDF e até tipo desconhecido: quem anexa diz se dá para usar
        for name in ("notas.txt", "main.py", "relatorio.pdf", "pacote.zip"):
            path = _write(self.dir, name, b"oi")
            self.assertEqual(dropped_paths(path), [path])

    def test_caminho_relativo_nao_e_arquivo_solto(self):
        self.assertEqual(dropped_paths("README.md"), [])   # texto comum que por acaso é um arquivo daqui

    def test_texto_comum_com_caminho_no_meio(self):
        png = _write(self.dir, "foto.png")
        self.assertEqual(dropped_paths(f"olha isso {png}"), [])
        self.assertEqual(dropped_paths("bom dia, jarvis"), [])
        self.assertEqual(dropped_paths("   "), [])

    def test_is_image_path(self):
        self.assertTrue(is_image_path(r"C:\x\FOTO.JPG"))
        self.assertFalse(is_image_path(r"C:\x\audio.wav"))


class _Base(base.TestJarvisApp):
    pass


for _name in [n for n in dir(base.TestJarvisApp) if n.startswith("test_")]:
    setattr(_Base, _name, None)


class TestDropInTui(_Base):
    def setUp(self):
        super().setUp()
        self.dir = _make_dir(self)
        self.png = _write(self.dir, "minha foto.png")

    async def test_colar_caminho_anexa_imagem(self):
        app = self._app()
        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt")
            prompt.focus()
            prompt.post_message(events.Paste(f'"{self.png}"'))
            await pilot.pause()
            self.assertIsNotNone(app.pending_image)
            self.assertEqual(app.pending_image["name"], "minha foto.png")
            self.assertEqual(prompt.value, "")

    async def test_colar_texto_comum_vai_para_o_input(self):
        app = self._app()
        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt")
            prompt.focus()
            prompt.post_message(events.Paste("bom dia"))
            await pilot.pause()
            self.assertEqual(prompt.value, "bom dia")
            self.assertIsNone(app.pending_image)

    async def test_enviar_caminho_puro_anexa_sem_mandar_ao_modelo(self):
        app = self._app()
        async with app.run_test() as pilot:
            await self._send(pilot, self.png)
            self.assertIsNotNone(app.pending_image)
            msgs = list(app.query(base.tui_app.MessageView))
            self.assertFalse([m for m in msgs if m.role == "user"])

    async def test_duas_imagens_anexa_a_primeira_e_avisa(self):
        other = _write(self.dir, "outra.png")
        app = self._app()
        async with app.run_test() as pilot:
            notes = []
            app.notify = lambda msg, **kw: notes.append(msg)
            app._attach_dropped([self.png, other])
            await pilot.pause()
            self.assertEqual(app.pending_image["name"], "minha foto.png")
            self.assertTrue(any("Só uma imagem" in n for n in notes))



class TestDropDocuments(_Base):
    def setUp(self):
        super().setUp()
        self.dir = _make_dir(self)
        self.seen = []

    def _doc_app(self):
        def stream(text, session_id, images, mode, on_route=None, force_chat=False):
            self.seen.append({"text": text, "force_chat": force_chat, "images": images})
            yield "ok"
        return base.tui_app.JarvisApp(stream_fn=stream, start_services=False, voice=base.FakeVoice())

    async def test_soltar_codigo_anexa_e_vai_junto_da_mensagem(self):
        code = _write(self.dir, "soma.py", b"def soma(a, b):\n    return a + b\n")
        app = self._doc_app()
        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt")
            prompt.focus()
            prompt.post_message(events.Paste(f'"{code}"'))
            await pilot.pause()
            self.assertEqual([d["name"] for d in app.pending_docs], ["soma.py"])
            self.assertIn("📄 soma.py", str(app.query_one("#attachbar").render()))
            self.assertEqual(prompt.value, "")
            await self._send(pilot, "tem bug aqui?")
            await self._wait_for(pilot, lambda: self.seen)
            sent = self.seen[0]
            self.assertTrue(sent["force_chat"])                 # conteúdo de arquivo nunca vira skill
            self.assertIn("def soma(a, b):", sent["text"])
            self.assertIn("[Arquivo: soma.py]", sent["text"])
            self.assertIn("tem bug aqui?", sent["text"])
            self.assertEqual(app.pending_docs, [])
            user = [m for m in app.query(base.tui_app.MessageView) if m.role == "user"][-1]
            self.assertEqual(user.text, "tem bug aqui?")      # a bolha (e o histórico) guardam só a mensagem
            self.assertIn("anexo: soma.py", user.meta)

    async def test_imagem_e_documento_juntos(self):
        png = _write(self.dir, "tela.png")
        txt = _write(self.dir, "log.txt", b"ERRO 42")
        app = self._doc_app()
        async with app.run_test() as pilot:
            app._attach_dropped([png, txt])
            await pilot.pause()
            self.assertIsNotNone(app.pending_image)
            await self._send(pilot, "o que houve?")
            await self._wait_for(pilot, lambda: self.seen)
            self.assertIn("ERRO 42", self.seen[0]["text"])
            self.assertTrue(self.seen[0]["images"])               # a imagem segue junto

    async def test_arquivo_sensivel_ou_binario_nao_anexa(self):
        env = _write(self.dir, ".env", b"OPENAI_KEY=abc")
        exe = _write(self.dir, "app.zip", b"PK\x03\x04\x00\x00binario")
        app = self._doc_app()
        async with app.run_test() as pilot:
            notes = []
            app.notify = lambda msg, **kw: notes.append(msg)
            app._attach_dropped([env, exe])
            await pilot.pause()
            self.assertEqual(app.pending_docs, [])
            self.assertTrue(any("segredos" in n for n in notes))
            self.assertTrue(any("não suportado" in n.lower() or "não é" in n for n in notes))

    async def test_detach_e_limite_de_documentos(self):
        paths = [_write(self.dir, f"n{i}.md", b"# nota") for i in range(4)]
        app = self._doc_app()
        async with app.run_test() as pilot:
            notes = []
            app.notify = lambda msg, **kw: notes.append(msg)
            app._attach_dropped(paths)
            await pilot.pause()
            self.assertEqual(len(app.pending_docs), base.tui_app.MAX_DOCS)
            self.assertTrue(any("No máximo" in n for n in notes))
            await self._send(pilot, "/detach")
            self.assertEqual(app.pending_docs, [])


if __name__ == "__main__":
    unittest.main()
