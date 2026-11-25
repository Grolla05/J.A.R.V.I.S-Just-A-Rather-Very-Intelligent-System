"""Preenchimento de formulários — services/form_fill.py (perfil, mapeamento, lista negra,
fluxo com confirmação e ajuste) e core/headless.FormSession (thread do navegador com
página falsa). Sem Edge, sem Ollama, sem Obsidian."""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from tests._stubs import install

install()

import core.state as state  # noqa: E402
from core import headless, pending  # noqa: E402
from services import form_fill  # noqa: E402

URL = "https://forms.example.com/inscricao"
NOTE = """# 🧠 Sobre Mim — Felipe Grolla Freitas

## 👤 Identidade

- **Nome completo:** Felipe Grolla Freitas
- **Localização:** Indaiatuba, São Paulo — Brasil
- **Redes:** [GitHub — Grolla05](https://github.com/Grolla05)
- **CPF:** 123.456.789-09
- **Telefone:** ← preencha

- **LinkedIn:** [linkedin.com/in/felipegrolla](https://www.linkedin.com/in/felipegrolla/)
"""
PROFILE = {"name": "Felipe Grolla Freitas", "first_name": "Felipe", "last_name": "Grolla Freitas",
           "email": "felipe@example.com", "city": "Indaiatuba", "state": "São Paulo", "country": "Brasil",
           "github": "https://github.com/Grolla05"}


def field(i, label="", **kw):
    base = {"i": i, "tag": "input", "type": "text", "name": "", "id": "", "label": label, "placeholder": "",
            "autocomplete": "", "required": False, "filled": False, "options": []}
    base.update(kw)
    return base


FIELDS = [
    field(0, "Nome completo", required=True),
    field(1, "", type="email", name="contato"),
    field(2, "Senha", type="password"),
    field(3, "CPF", required=True),
    field(4, "Cidade onde mora"),
    field(5, "Estado", tag="select", options=["Selecione", "Rio de Janeiro", "Sao Paulo"]),
    field(6, "Como conheceu o evento?", required=True),
    field(7, "Perfil profissional"),
    field(8, "Telefone", type="tel"),
]


class TestProfile(unittest.TestCase):
    def test_parse_note(self):
        prof = form_fill.parse_profile_note(NOTE)
        self.assertEqual(prof["name"], "Felipe Grolla Freitas")
        self.assertEqual((prof["first_name"], prof["last_name"]), ("Felipe", "Grolla Freitas"))
        self.assertEqual((prof["city"], prof["state"], prof["country"]), ("Indaiatuba", "São Paulo", "Brasil"))
        self.assertEqual(prof["github"], "https://github.com/Grolla05")
        self.assertEqual(prof["linkedin"], "https://www.linkedin.com/in/felipegrolla/")
        self.assertNotIn("phone", prof)                      # "← preencha" não é valor
        self.assertNotIn("123.456.789-09", " ".join(prof.values()))

    def test_load_profile_sources(self):
        prof = form_fill.load_profile(note=lambda: NOTE, email=lambda: "felipe@example.com",
                                      home=lambda: "Rua X, 10 - Indaiatuba", use_cache=False)
        self.assertEqual(prof["email"], "felipe@example.com")
        self.assertEqual(prof["address"], "Rua X, 10 - Indaiatuba")

        def broken():
            raise RuntimeError("obsidian fora")
        prof = form_fill.load_profile(note=broken, email=lambda: "", home=lambda: "", use_cache=False)
        self.assertEqual(prof, {})


class TestMapping(unittest.TestCase):
    def test_rules_blacklist_and_llm_for_leftovers(self):
        asked = {}

        def llm(fields, keys):
            asked["labels"] = [form_fill.field_label(f) for f in fields]
            asked["keys"] = keys
            return {"6": "email", "7": "github", "3": "name"}   # "3" (CPF) nem chega ao modelo

        plan = form_fill.map_fields(FIELDS, PROFILE, ask_llm=llm)
        filled = {f["i"]: v for f, v, _ in plan["fill"]}
        self.assertEqual(filled[0], "Felipe Grolla Freitas")
        self.assertEqual(filled[1], "felipe@example.com")
        self.assertEqual(filled[4], "Indaiatuba")
        self.assertEqual(filled[5], "Sao Paulo")             # opção do <select> sem acento
        self.assertEqual(filled[7], "https://github.com/Grolla05")
        self.assertNotIn(6, filled)                          # e-mail já usado: chave fora da lista do modelo
        self.assertEqual({f["i"] for f in plan["sensitive"]}, {2, 3})
        self.assertEqual({f["i"] for f in plan["unknown"]}, {6, 8})
        self.assertEqual(asked["labels"], ["Como conheceu o evento?", "Perfil profissional"])
        self.assertNotIn("email", asked["keys"])

    def test_llm_cannot_invent_values(self):
        plan = form_fill.map_fields([field(0, "Apelido", required=True)], PROFILE,
                                    ask_llm=lambda f, k: {"0": "Felipão"})
        self.assertEqual(plan["fill"], [])
        self.assertEqual([f["i"] for f in plan["unknown"]], [0])

    def test_time_field_never_gets_profile_text(self):
        # Caso real (httpbin, 25/11): o modelo mapeou "Preferred delivery time" (type=time) para a cidade
        fields = [field(0, "Customer name:"), field(1, "Preferred delivery time:", type="time"),
                  field(2, "Data do evento", type="date", required=True)]
        plan = form_fill.map_fields(fields, PROFILE, ask_llm=lambda f, k: {"1": "city", "2": "city"})
        self.assertEqual([(f["i"], v) for f, v, _ in plan["fill"]], [(0, "Felipe Grolla Freitas")])
        self.assertEqual([f["i"] for f in plan["unknown"]], [2])     # obrigatório: aparece em "não preenchi"
        self.assertEqual(form_fill.field_label(fields[0]), "Customer name")

    def test_filled_field_is_kept(self):
        plan = form_fill.map_fields([field(0, "Nome", filled=True)], PROFILE, ask_llm=None)
        self.assertEqual(plan, {"fill": [], "sensitive": [], "unknown": []})

    def test_sensitive_inputs(self):
        for f in (field(0, "", type="password"), field(1, "Número", autocomplete="cc-number"),
                  field(2, "", name="user_cpf"), field(3, "RG"), field(4, "", placeholder="Código de segurança")):
            self.assertTrue(headless.is_sensitive_input(f), f)
        self.assertFalse(headless.is_sensitive_input(field(5, "Nome completo")))


# ------------------------------------------------------------------ fluxo
class FakeSession:
    def __init__(self, url, fields=FIELDS, error=None):
        self.url, self.fields, self.error, self.title = url, fields, error, "Inscrição no evento"
        self.calls = []

    def start(self):
        return self

    def wait_ready(self, timeout):
        return self.error is None

    def call(self, cmd, *args, timeout=30):
        self.calls.append((cmd, args))
        if cmd == "fill":
            return {"ok": True, "filled": [f["i"] for f, _ in args[0]], "failed": []}
        if cmd == "submit":
            return {"ok": True, "title": "Inscrição recebida", "url": URL}
        return {"ok": True}


class TestFlow(unittest.TestCase):
    def setUp(self):
        state.pending_critical_action = None

    def tearDown(self):
        state.pending_critical_action = None

    def start(self, text=f"preenche esse formulário {URL}", **kw):
        holder = {}

        def factory(url):
            holder["session"] = FakeSession(url, **kw)
            return holder["session"]

        reply = form_fill.request(text, session_factory=factory, profile=PROFILE, map_llm=lambda f, k: {},
                                  active=lambda: "")
        return reply, holder.get("session")

    def test_fills_and_waits_for_yes(self):
        reply, session = self.start()
        self.assertIn("- Nome completo → Felipe Grolla Freitas", reply)
        self.assertIn("Senha (dado sensível)", reply)
        self.assertIn("CPF (dado sensível)", reply)
        self.assertIn("Envio? (**sim** envia", reply)
        cmds = [c for c, _ in session.calls]
        self.assertEqual(cmds, ["fill"])                      # nada enviado ainda
        values = [v for _, v in session.calls[0][1][0]]
        self.assertNotIn("123.456.789-09", values)
        action, status = pending.take()
        self.assertEqual((status, action["type"]), (pending.OK, "FORM_SUBMIT"))
        self.assertIn("Inscrição recebida", action["on_confirm"]())
        self.assertEqual(session.calls[-1], ("submit", (0,)))

    def test_decline_keeps_window(self):
        self.start()
        action, _ = pending.take()
        self.assertIn("janela segue aberta", action["on_decline"]())

    def test_adjust_field_from_user_words(self):
        _, session = self.start()
        action, _ = pending.take()
        reply = action["on_other"]("o telefone é 19 99999-0000")
        self.assertEqual(session.calls[-1][0], "fill")
        self.assertEqual(session.calls[-1][1][0][0][0]["i"], 8)
        self.assertEqual(session.calls[-1][1][0][0][1], "19 99999-0000")
        self.assertIn("- Telefone → 19 99999-0000", reply)
        self.assertNotIn("Telefone (não sei)", reply)
        self.assertEqual(pending.active()["type"], "FORM_SUBMIT")   # perguntou de novo

    def test_adjust_refuses_sensitive(self):
        _, session = self.start()
        action, _ = pending.take()
        n = len(session.calls)
        reply = action["on_other"]("o CPF é 123.456.789-09")
        self.assertIn("não preencho", reply)
        self.assertEqual(len(session.calls), n)
        action, _ = pending.take()
        self.assertIn("Não achei esse campo", action["on_other"]("abre o spotify com volume alto"))

    def test_guards(self):
        reply, _ = self.start(text="preenche esse formulário")
        self.assertIn("Qual formulário", reply)
        reply, _ = self.start(text="preenche http://localhost:5000/form")
        self.assertIn("não abro", reply)
        reply, _ = self.start(error="o site demorou demais para responder")
        self.assertIn("demorou demais", reply)
        reply, session = self.start(fields=[])
        self.assertIn("Não achei campos", reply)
        self.assertEqual(session.calls, [("close", ())])

    def test_busy_confirmation(self):
        pending.arm("OUTRA", "outra?", lambda: "x")
        reply, _ = self.start()
        self.assertEqual(reply, pending.BUSY_REPLY)

    def test_skill_passes_entity(self):
        from skills.productivity import form_fill as skill
        with patch.object(form_fill, "request", return_value="ok") as req:
            self.assertEqual(skill.execute(URL, "preenche a inscrição"), "ok")
        req.assert_called_once_with(f"preenche a inscrição {URL}")


# ------------------------------------------------------------------ thread do navegador
class FakeLoc:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    @property
    def first(self):
        return self

    def get_attribute(self, name):
        return None

    def fill(self, value):
        self.page.log.append(("fill", self.selector, value))

    def select_option(self, label=None):
        self.page.log.append(("select", self.selector, label))

    def click(self):
        self.page.log.append(("click", self.selector))
        self.page.url = URL + "/ok"


class FakeFormPage:
    def __init__(self):
        self.url, self.log, self.closed = "about:blank", [], False

    def goto(self, url, wait_until=None):
        self.url = url

    def wait_for_load_state(self, *a, **k):
        pass

    def wait_for_timeout(self, ms):
        pass

    def is_closed(self):
        return self.closed

    def title(self):
        return "Inscrição"

    def evaluate(self, script, arg):
        if script is headless._FIELDS_JS:
            return [field(0, "Nome completo"), field(1, "Senha", type="password")]
        return True     # _SUBMIT_JS achou o botão

    def locator(self, selector):
        return FakeLoc(self, selector)


class TestFormSession(unittest.TestCase):
    def test_session_fill_submit_close(self):
        page = FakeFormPage()

        @contextmanager
        def opener():
            yield page

        session = headless.FormSession(URL, opener=opener).start()
        self.assertTrue(session.wait_ready(5))
        self.assertTrue(headless.busy())
        self.assertEqual([f["label"] for f in session.fields], ["Nome completo", "Senha"])
        res = session.call("fill", [(session.fields[0], "Felipe"), (session.fields[1], "segredo")], timeout=5)
        self.assertEqual(res["filled"], [0])
        self.assertIn("sensível", res["failed"][0][1])
        self.assertNotIn("segredo", str(page.log))
        res = session.call("submit", 0, timeout=5)
        self.assertTrue(res["ok"])
        self.assertIn(("click", '[data-jarvis-submit="1"]'), page.log)
        self.assertTrue(session.call("close", timeout=5)["ok"])
        self.assertTrue(session.closed.wait(5))
        self.assertFalse(headless.busy())
        self.assertIn("fechada", session.call("fill", [], timeout=1)["error"])

    def test_user_closes_window(self):
        page = FakeFormPage()

        @contextmanager
        def opener():
            yield page

        session = headless.FormSession(URL, opener=opener).start()
        self.assertTrue(session.wait_ready(5))
        page.closed = True
        self.assertTrue(session.closed.wait(5))
        self.assertFalse(headless.busy())

    def test_unsafe_redirect(self):
        page = FakeFormPage()
        page.goto = lambda url, wait_until=None: setattr(page, "url", "http://192.168.0.1/")

        @contextmanager
        def opener():
            yield page

        session = headless.FormSession(URL, opener=opener).start()
        self.assertFalse(session.wait_ready(5))
        self.assertIn("não permitido", session.error)
        self.assertTrue(session.closed.wait(5))


if __name__ == "__main__":
    unittest.main()
