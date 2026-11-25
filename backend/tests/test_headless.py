"""Navegação headless — core/headless.py (validação dos passos, passos que enviam algo,
rotas vigiadas, execução com página falsa) e services/headless_tasks.py (plano,
confirmação, aviso). Nenhum teste abre o Edge nem chama o Ollama."""
import json
import re
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from tests._stubs import install

install()

import core.state as state  # noqa: E402
from core import headless, pending, webwatch  # noqa: E402
from services import headless_tasks  # noqa: E402

SITE = "https://www.kabum.com.br/busca/rtx-5060"


# ------------------------------------------------------------------ página falsa
class FakeLocator:
    def __init__(self, page, key, count=1, attrs=None):
        self.page, self.key, self._count, self.attrs = page, key, count, attrs or {}

    def count(self):
        return self._count

    @property
    def first(self):
        return self

    def click(self):
        self.page.log.append(("click", self.key))
        target = self.page.click_targets.get(self.key)
        if target:
            self.page.url = target

    def fill(self, value):
        self.page.log.append(("fill", self.key, value))

    def get_attribute(self, name):
        return self.attrs.get(name)


class FakePage:
    def __init__(self, fields=None, click_targets=None, html="<main><p>RTX 5060 por R$ 2.199,90</p></main>"):
        self.url = "about:blank"
        self.log = []
        self.fields = fields or {}               # rótulo -> atributos
        self.click_targets = click_targets or {}  # texto -> URL após o clique
        self.html = html
        self.keyboard = SimpleNamespace(press=lambda key: self.log.append(("press", key)))

    def goto(self, url, wait_until=None):
        self.log.append(("goto", url))
        self.url = url

    def wait_for_load_state(self, *a, **k):
        pass

    def wait_for_timeout(self, ms):
        self.log.append(("wait", ms))

    def get_by_role(self, role, name=None):
        if role in ("button", "link"):
            return FakeLocator(self, name, count=1 if name in self.click_targets or name == "Buscar" else 0)
        return FakeLocator(self, name, count=0)

    def get_by_text(self, text):
        return FakeLocator(self, text, count=0)

    def get_by_label(self, label):
        return FakeLocator(self, label, count=1 if label in self.fields else 0, attrs=self.fields.get(label))

    def get_by_placeholder(self, label):
        return FakeLocator(self, label, count=0)

    def content(self):
        return self.html

    def inner_text(self, selector, timeout=None):
        if selector == "main" and "<main>" not in self.html:
            raise TimeoutError("sem <main>")
        return re.sub(r"<[^>]+>", "\n", self.html)

    def title(self):
        return "KaBuM!"


def opener_for(page):
    @contextmanager
    def opener():
        yield page
    return opener


# ------------------------------------------------------------------ validação
class TestValidate(unittest.TestCase):
    def test_valid_plan_is_normalized(self):
        steps, error = headless.validate_steps([
            {"type": "goto", "url": SITE}, {"type": "fill", "label": " Busca ", "value": "rtx  5060"},
            {"type": "press", "key": "enter"}, {"type": "wait", "seconds": 30}, {"type": "extract"}])
        self.assertIsNone(error)
        self.assertEqual(steps[1], {"type": "fill", "label": "Busca", "value": "rtx 5060"})
        self.assertEqual(steps[2]["key"], "Enter")
        self.assertEqual(steps[3]["seconds"], headless.MAX_WAIT_S)

    def test_rejections(self):
        bad = {
            "vazio": [],
            "tipo desconhecido": [{"type": "goto", "url": SITE}, {"type": "eval", "js": "alert(1)"}],
            "passos demais": [{"type": "goto", "url": SITE}] + [{"type": "extract"}] * headless.MAX_STEPS,
            "1º não é goto": [{"type": "click", "text": "Ok"}],
            "localhost": [{"type": "goto", "url": "http://localhost:8080"}],
            "rede local": [{"type": "goto", "url": "http://192.168.0.1/admin"}],
            "arquivo": [{"type": "goto", "url": "file:///C:/Windows/win.ini"}],
            "senha": [{"type": "goto", "url": SITE}, {"type": "fill", "label": "Senha", "value": "x"}],
            "cpf": [{"type": "goto", "url": SITE}, {"type": "fill", "label": "CPF", "value": "1"}],
            "cartão": [{"type": "goto", "url": SITE}, {"type": "fill", "label": "Número do cartão", "value": "1"}],
            "valor cpf": [{"type": "goto", "url": SITE}, {"type": "fill", "label": "Busca", "value": "123.456.789-09"}],
            "valor cartão": [{"type": "goto", "url": SITE},
                             {"type": "fill", "label": "Busca", "value": "4111 1111 1111 1111"}],
            "tecla": [{"type": "goto", "url": SITE}, {"type": "press", "key": "Control+W"}],
        }
        for name, raw in bad.items():
            steps, error = headless.validate_steps(raw)
            self.assertIsNone(steps, name)
            self.assertTrue(error, name)
        self.assertEqual(headless.validate_steps("não é lista"), (None, "nenhum passo"))


class TestRisky(unittest.TestCase):
    def steps(self, *raw):
        steps, error = headless.validate_steps([{"type": "goto", "url": SITE}, *raw])
        self.assertIsNone(error)
        return steps

    def test_send_clicks_are_risky(self):
        steps = self.steps({"type": "click", "text": "Comprar agora"}, {"type": "click", "text": "Próxima página"},
                           {"type": "click", "text": "Buscar"}, {"type": "click", "text": "Enviar mensagem"},
                           {"type": "click", "text": "Confirmar e OK"})
        self.assertEqual(headless.risky_steps(steps), [1, 4, 5])

    def test_enter_after_search_is_safe(self):
        steps = self.steps({"type": "fill", "label": "Pesquisar", "value": "rtx"}, {"type": "press", "key": "Enter"})
        self.assertEqual(headless.risky_steps(steps), [])
        steps = self.steps({"type": "fill", "label": "Nome", "value": "Felipe"}, {"type": "press", "key": "Enter"})
        self.assertEqual(headless.risky_steps(steps), [2])
        self.assertEqual(headless.risky_steps(self.steps({"type": "press", "key": "Enter"})), [])


class TestGuard(unittest.TestCase):
    def route(self, url, nav=False, main=True):
        frame = SimpleNamespace(parent_frame=None if main else object())
        req = SimpleNamespace(url=url, frame=frame, is_navigation_request=lambda: nav)
        calls = []
        route = SimpleNamespace(request=req, continue_=lambda: calls.append("ok"), abort=lambda: calls.append("abort"))
        headless._guard(route)
        return calls[0]

    def test_guard(self):
        self.assertEqual(self.route(SITE, nav=True), "ok")
        self.assertEqual(self.route("http://localhost:3000/", nav=True), "abort")
        self.assertEqual(self.route("https://site.com/?token=abc", nav=True), "abort")
        self.assertEqual(self.route("https://cdn.site.com/a.js?token=abc"), "ok")   # recurso: só o host importa
        self.assertEqual(self.route("http://192.168.0.1/x.png"), "abort")
        self.assertEqual(self.route("http://10.0.0.5/frame", nav=True, main=False), "abort")
        self.assertEqual(self.route("data:image/png;base64,AAAA"), "ok")


# ------------------------------------------------------------------ execução
class TestRunTask(unittest.TestCase):
    def test_runs_steps_and_extracts(self):
        page = FakePage(fields={"Busca": {"type": "search"}})
        steps, _ = headless.validate_steps([{"type": "goto", "url": SITE},
                                            {"type": "fill", "label": "Busca", "value": "rtx 5060"},
                                            {"type": "press", "key": "Enter"}, {"type": "wait", "seconds": 1}])
        res = headless.run_task(steps, opener=opener_for(page))
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["done"], 4)
        self.assertIn("R$ 2.199,90", res["text"])
        self.assertEqual(page.log, [("goto", SITE), ("fill", "Busca", "rtx 5060"), ("press", "Enter"), ("wait", 1000)])
        self.assertFalse(headless.busy())

    def test_password_field_is_refused(self):
        page = FakePage(fields={"Usuário": {"type": "password"}})
        steps, _ = headless.validate_steps([{"type": "goto", "url": SITE},
                                            {"type": "fill", "label": "Usuário", "value": "x"}])
        res = headless.run_task(steps, opener=opener_for(page))
        self.assertFalse(res["ok"])
        self.assertIn("sensível", res["error"])
        self.assertEqual(res["done"], 1)
        self.assertNotIn(("fill", "Usuário", "x"), page.log)

    def test_redirect_to_unsafe_stops(self):
        page = FakePage(click_targets={"Ver oferta": "http://192.168.0.10/"})
        steps, _ = headless.validate_steps([{"type": "goto", "url": SITE}, {"type": "click", "text": "Ver oferta"},
                                            {"type": "extract"}])
        res = headless.run_task(steps, opener=opener_for(page))
        self.assertFalse(res["ok"])
        self.assertIn("não permitido", res["error"])

    def test_missing_element(self):
        steps, _ = headless.validate_steps([{"type": "goto", "url": SITE}, {"type": "click", "text": "Nada"}])
        res = headless.run_task(steps, opener=opener_for(FakePage()))
        self.assertEqual(res["error"], "não achei “Nada” na página")

    def test_one_task_at_a_time(self):
        steps, _ = headless.validate_steps([{"type": "goto", "url": SITE}])
        with headless._lock:
            res = headless.run_task(steps, opener=lambda: 1 / 0)
        self.assertFalse(res["ok"])
        self.assertIn("já há uma tarefa", res["error"])

    def test_visible_text_joins_currency(self):
        raw = "Placa RTX 5060\n\n  R$  \n4.199,99\nNo PIX\n$\n12.50"
        self.assertEqual(headless._visible_text(raw, 1000), "Placa RTX 5060\nR$ 4.199,99\nNo PIX\n$ 12.50")

    def test_render_html(self):
        def never():
            raise AssertionError("não devia abrir o navegador")
        self.assertEqual(headless.render_html("http://127.0.0.1/", opener=never), "")
        page = FakePage(html="<html>R$ 99,90</html>")
        self.assertEqual(headless.render_html(SITE, opener=opener_for(page)), "<html>R$ 99,90</html>")
        self.assertIn("2.199,90", headless.fetch_rendered(SITE, opener=opener_for(FakePage())))

    def test_webwatch_tries_rendered_before_llm(self):
        calls = []
        res = webwatch.check_price(SITE, fetch=lambda u: ("<html>sem preço</html>", None),
                                   rendered=lambda u: '<meta property="product:price:amount" content="1899.90">',
                                   ask_llm=lambda t: calls.append(t))
        self.assertEqual(res, {"price": 1899.90})
        self.assertEqual(calls, [])


# ------------------------------------------------------------------ serviço
class TestService(unittest.TestCase):
    def setUp(self):
        state.pending_critical_action = None
        self.announced = []
        self._announce = state.announce
        state.announce = self.announced.append

    def tearDown(self):
        state.pending_critical_action = None
        state.announce = self._announce

    def plan_llm(self, *raw, goal="preço da RTX 5060"):
        return lambda text: {"objetivo": goal, "passos": [{"type": "goto", "url": SITE}, *raw]}

    def test_plan_fallback_to_link(self):
        goal, steps, error = headless_tasks.plan(f"resume {SITE}.", ask_llm=lambda t: None)
        self.assertEqual(steps, [{"type": "goto", "url": SITE}, {"type": "extract"}])
        goal, steps, error = headless_tasks.plan("vê o preço", ask_llm=lambda t: {"passos": [{"type": "eval"}]})
        self.assertIsNone(steps)
        self.assertIn("desconhecido", error)

    def test_safe_task_runs_in_background(self):
        seen = {}

        def runner(steps):
            seen["steps"] = steps
            return {"ok": True, "url": SITE, "title": "KaBuM!", "text": "RTX 5060 por R$ 2.199,90", "done": 2}

        reply = headless_tasks.request("entra na kabum e vê o preço da rtx 5060",
                                       plan_llm=self.plan_llm({"type": "extract"}), runner=runner,
                                       answer_llm=lambda goal, res: "Está **R$ 2.199,90**, Senhor.",
                                       background=lambda fn: fn())
        self.assertIn("Executando em segundo plano: abrir www.kabum.com.br → copiar o texto da página", reply)
        self.assertEqual(len(seen["steps"]), 2)
        self.assertIn("R$ 2.199,90", self.announced[0])
        self.assertIn(f"Página: {SITE}", self.announced[0])
        self.assertIsNone(state.pending_critical_action)

    def test_risky_task_waits_for_confirmation(self):
        ran = []
        reply = headless_tasks.request("compra a rtx", plan_llm=self.plan_llm({"type": "click", "text": "Comprar"}),
                                       runner=lambda steps: ran.append(steps) or {"ok": True, "text": "ok", "url": SITE},
                                       answer_llm=lambda g, r: "feito", background=lambda fn: fn())
        self.assertIn("⚠️ **envia algo**", reply)
        self.assertIn("(**sim** / **não**)", reply)
        self.assertEqual(ran, [])
        action, status = pending.take()
        self.assertEqual(status, pending.OK)
        self.assertEqual(action["type"], "HEADLESS_TASK")
        self.assertIn("Executando", action["on_confirm"]())
        self.assertEqual(len(ran), 1)
        self.assertEqual(action["on_decline"](), "Nada enviado, Senhor.")

    def test_busy_confirmation(self):
        pending.arm("OUTRA", "outra?", lambda: "x")
        reply = headless_tasks.request("compra", plan_llm=self.plan_llm({"type": "click", "text": "Comprar"}),
                                       runner=lambda s: {}, background=lambda fn: fn())
        self.assertEqual(reply, pending.BUSY_REPLY)

    def test_report(self):
        self.assertIn("parou no passo 2", headless_tasks.report("x", {"ok": False, "done": 1, "error": "timeout"}))
        self.assertIn("não tinha texto legível", headless_tasks.report("x", {"ok": True, "text": " ", "url": SITE}))
        self.assertIn("Não consegui resumir", headless_tasks.report("x", {"ok": True, "text": "a", "url": SITE},
                                                                    ask_llm=lambda g, r: None))

    def test_unavailable(self):
        with patch.object(headless, "available", return_value=(False, "o Microsoft Edge não foi encontrado")):
            self.assertIn("Edge não foi encontrado", headless_tasks.request("entra no site x"))

    def test_skill_passes_phrase(self):
        from skills.web import headless_task
        with patch.object(headless_tasks, "request", return_value="ok") as req:
            self.assertEqual(headless_task.execute("kabum", "entra no site da kabum"), "ok")
        req.assert_called_once_with("entra no site da kabum")

    def test_plan_prompt_has_request(self):
        from core.prompts import load_prompt
        self.assertIn("vê o preço", load_prompt("headless_plan.md", request="vê o preço"))
        self.assertTrue(json.loads('{"type": "extract"}'))


if __name__ == "__main__":
    unittest.main()
