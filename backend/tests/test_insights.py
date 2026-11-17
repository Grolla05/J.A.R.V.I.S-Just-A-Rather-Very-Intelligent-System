"""services.insights + ObsidianClient.append_note + skill INSIGHT_SAVE (sem Obsidian nem Ollama)."""
import importlib.util
import json
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.obsidian  # noqa: E402,F401

obsidian_mod = sys.modules["core.obsidian"]
from services import insights  # noqa: E402

NOW = datetime(2026, 11, 16, 14, 30)
IDEA = "Tive uma ideia: um painel na cozinha que mostra a agenda da família e a lista de compras."


class FakeDb:
    def __init__(self):
        self.data = {}

    def get_config(self, key):
        return json.loads(json.dumps(self.data[key])) if key in self.data else None

    def save_config(self, key, value):
        self.data[key] = json.loads(json.dumps(value))


class FakeVault:
    """Cliente do Obsidian de mentira: `online=False` simula o plugin fora do ar."""

    def __init__(self, online=True):
        self.online = online
        self.notes = {}

    def append_note(self, path, text, header=""):
        if not self.online:
            return False
        self.notes[path] = self.notes.get(path, header) + text if path in self.notes else header + text
        return True


class InsightsCase(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self._patch = patch.object(insights, "db", self.db)
        self._patch.start()
        self.vault = FakeVault()

    def tearDown(self):
        self._patch.stop()

    def _save(self, title="Painel da cozinha", summary="Um painel com agenda e compras.", now=NOW):
        return insights.save(title, summary, "sessão de teste", now=now, client=self.vault)


class TestWorthChecking(unittest.TestCase):
    def test_cases(self):
        cases = {
            IDEA: True,
            "oi jarvis": False,
            "qual é a capital da França mesmo?": False,                       # curta
            "/web como fazer um painel de cozinha com raspberry pi zero": False,   # comando
            "olha esse código aqui que eu fiz ontem ```def f(): pass``` certo?": False,
            "": False,
        }
        for text, expected in cases.items():
            with self.subTest(text=text[:30]):
                self.assertEqual(insights.worth_checking(text), expected)


class TestExtract(unittest.TestCase):
    def _run(self, raw):
        with patch.object(insights, "query_ollama", return_value=raw) as llm:
            return insights.extract(IDEA, "Boa ideia, Senhor."), llm

    def test_insight_found(self):
        found, llm = self._run(json.dumps({"insight": True, "title": " Painel  da cozinha ", "summary": "Um painel."}))
        self.assertEqual(found, {"title": "Painel da cozinha", "summary": "Um painel."})
        prompt = llm.call_args[0][0][0]["content"]
        self.assertIn("painel na cozinha", prompt)
        self.assertIn("Boa ideia, Senhor.", prompt)
        self.assertEqual(llm.call_args.kwargs["format"], "json")

    def test_label_prefix_is_removed_from_title(self):
        """Visto no teste real com gemma2:2b: 'INSIGHT: Modo Viagem para JARVIS'."""
        for raw_title in ("INSIGHT: Modo viagem", "Ideia - Modo viagem", "Título: Modo viagem"):
            found, _ = self._run(json.dumps({"insight": True, "title": raw_title, "summary": "x"}))
            self.assertEqual(found["title"], "Modo viagem")

    def test_not_an_insight_or_bad_output(self):
        for raw in (json.dumps({"insight": False, "title": "x", "summary": "y"}),
                    json.dumps({"insight": "true", "title": "x", "summary": "y"}),   # só o booleano vale
                    json.dumps({"insight": True, "title": "", "summary": "y"}),
                    "não é json", None, "[]"):
            with self.subTest(raw=raw):
                self.assertIsNone(self._run(raw)[0])

    def test_llm_error_is_none(self):
        with patch.object(insights, "query_ollama", side_effect=RuntimeError("ollama fora")):
            self.assertIsNone(insights.extract(IDEA))


class TestSave(InsightsCase):
    def test_creates_monthly_note_in_brainstorms_with_header(self):
        self.assertEqual(self._save(), insights.SAVED)
        path = "🧠 Brainstorms/J.A.R.V.I.S — Insights 2026-11.md"
        self.assertEqual(list(self.vault.notes), [path])
        note = self.vault.notes[path]
        self.assertTrue(note.startswith("---\ntipo: brainstorm\ncriado: 2026-11-16"))
        self.assertIn("# Insights — novembro de 2026", note)
        self.assertIn("## 16/11 14:30 — Painel da cozinha", note)
        self.assertIn("> origem: sessão de teste", note)

    def test_second_insight_is_appended_without_repeating_header(self):
        self._save()
        self.assertEqual(self._save("Outra", "Um robô que rega as plantas."), insights.SAVED)
        note = next(iter(self.vault.notes.values()))
        self.assertEqual(note.count("tipo: brainstorm"), 1)
        self.assertLess(note.index("Painel da cozinha"), note.index("Outra"))

    def test_duplicate_within_window_and_allowed_after(self):
        self._save()
        self.assertEqual(self._save("Título diferente", "um painel com AGENDA e compras"), insights.DUPLICATE)
        later = datetime(2026, 11, 30, 9, 0)
        self.assertEqual(self._save(now=later), insights.SAVED)

    def test_new_month_goes_to_new_note(self):
        self._save()
        self._save("Dezembro", "Planejar as férias com antecedência.", now=datetime(2026, 12, 1, 8, 0))
        self.assertEqual(len(self.vault.notes), 2)
        self.assertIn("🧠 Brainstorms/J.A.R.V.I.S — Insights 2026-12.md", self.vault.notes)

    def test_offline_is_queued_then_flushed_in_order(self):
        self.vault.online = False
        self.assertEqual(self._save("Primeira", "Ideia número um."), insights.QUEUED)
        self.assertEqual(self._save("Segunda", "Ideia número dois."), insights.QUEUED)
        self.assertEqual(self.vault.notes, {})
        self.assertEqual(len(self.db.data[insights.PENDING_KEY]), 2)
        self.vault.online = True
        self.assertEqual(self._save("Terceira", "Ideia número três."), insights.SAVED)
        note = next(iter(self.vault.notes.values()))
        self.assertLess(note.index("Primeira"), note.index("Segunda"))
        self.assertLess(note.index("Segunda"), note.index("Terceira"))
        self.assertEqual(note.count("tipo: brainstorm"), 1)
        self.assertEqual(self.db.data[insights.PENDING_KEY], [])

    def test_flush_stops_at_first_failure(self):
        self.vault.online = False
        self._save("Primeira", "Ideia número um.")
        self.assertEqual(insights.flush_pending(self.vault), 0)
        self.assertEqual(len(self.db.data[insights.PENDING_KEY]), 1)
        self.vault.online = True
        self.assertEqual(insights.flush_pending(self.vault), 1)
        self.assertEqual(insights.flush_pending(self.vault), 0)

    def test_empty_is_rejected(self):
        with self.assertRaises(ValueError):
            insights.save("  ", "algo", client=self.vault)

    def test_save_text_uses_first_sentence_as_title(self):
        reply = insights.save_text("Painel da cozinha. Mostra agenda e compras para a família.",
                                   now=NOW, client=self.vault)
        self.assertIn("Brainstorms", reply)
        self.assertIn("— Painel da cozinha.", next(iter(self.vault.notes.values())))
        self.assertIn("já está registrada", insights.save_text(
            "Painel da cozinha. Mostra agenda e compras para a família.", now=NOW, client=self.vault))
        self.vault.online = False
        self.assertIn("Guardei a ideia", insights.save_text("Outra coisa bem diferente disso.", now=NOW,
                                                            client=self.vault))
        self.assertIn("Qual é a ideia", insights.save_text("  "))


class TestCapture(InsightsCase):
    def _capture(self, text=IDEA, found=None):
        found = {"title": "Painel da cozinha", "summary": "Um painel com agenda."} if found is None else found
        with patch.object(insights, "extract", return_value=found or None) as extract:
            return insights.capture(text, "resposta", "sessão", now=NOW, client=self.vault), extract

    def test_saves_and_returns_title(self):
        title, _ = self._capture()
        self.assertEqual(title, "Painel da cozinha")
        self.assertEqual(len(self.vault.notes), 1)

    def test_short_message_never_reaches_the_model(self):
        title, extract = self._capture(text="oi jarvis")
        self.assertIsNone(title)
        extract.assert_not_called()

    def test_no_insight_or_duplicate_returns_none(self):
        self.assertIsNone(self._capture(found={})[0])
        self._capture()
        self.assertIsNone(self._capture()[0])

    def test_queued_still_reports_title(self):
        self.vault.online = False
        self.assertEqual(self._capture()[0], "Painel da cozinha")


class TestAppendNote(unittest.TestCase):
    def setUp(self):
        self.client = obsidian_mod.ObsidianClient.__new__(obsidian_mod.ObsidianClient)

    def _append(self, exists):
        with patch.object(self.client, "note_exists", return_value=exists), \
             patch.object(self.client, "_req", return_value=MagicMock()) as req:
            ok = self.client.append_note("🧠 Brainstorms/Nota.md", "\ntexto\n", header="# Cabeçalho\n")
        return ok, req

    def test_new_note_gets_header(self):
        ok, req = self._append(False)
        self.assertTrue(ok)
        self.assertEqual(req.call_args[0][0], "POST")  # append: nunca PUT (sobrescreveria)
        self.assertEqual(req.call_args.kwargs["data"].decode("utf-8"), "# Cabeçalho\n\ntexto\n")
        self.assertIn("%F0%9F%A7%A0%20Brainstorms%2FNota.md", req.call_args[0][1])

    def test_existing_note_only_gets_the_text(self):
        ok, req = self._append(True)
        self.assertTrue(ok)
        self.assertEqual(req.call_args.kwargs["data"].decode("utf-8"), "\ntexto\n")

    def test_unknown_state_writes_nothing(self):
        ok, req = self._append(None)
        self.assertFalse(ok)
        req.assert_not_called()

    def test_write_failure_is_false(self):
        with patch.object(self.client, "note_exists", return_value=True), \
             patch.object(self.client, "_req", return_value=None):
            self.assertFalse(self.client.append_note("a.md", "x"))


class TestSkill(unittest.TestCase):
    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "skills", "productivity", "insight_note.py")
        spec = importlib.util.spec_from_file_location("insight_note", path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_strip_request(self):
        cases = {
            "anota essa ideia: um app que resume reuniões": "um app que resume reuniões",
            "Jarvis, registra esse insight de que testes pequenos rodam mais": "testes pequenos rodam mais",
            "tive uma ideia, anota aí: vender o curso em módulos": "vender o curso em módulos",
            "anota um painel para a cozinha": "um painel para a cozinha",
            "guarda esse brainstorm sobre o canal de vídeos curtos": "o canal de vídeos curtos",
            "anota essa ideia": "",
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(self.mod.strip_request(command), expected)

    def test_execute_uses_model_title_and_keeps_user_words(self):
        """Visto no teste real: sem isso o título virava 'Estive pensando: o JARVIS podia…'."""
        idea = "um modo viagem que junta cartão de embarque, clima e trajeto num aviso"
        with patch.object(insights, "extract", return_value={"title": "Modo viagem", "summary": "resumo do modelo"}), \
             patch.object(insights, "save", return_value=insights.SAVED) as save:
            reply = self.mod.execute(None, f"anota essa ideia: {idea}")
        self.assertIn("Modo viagem", reply)
        self.assertEqual(save.call_args[0][:2], ("Modo viagem", idea[0].upper() + idea[1:]))

    def test_execute_saves_or_asks(self):
        with patch.object(insights, "extract", return_value=None), \
             patch.object(insights, "save_text", return_value="ok") as save:
            self.assertEqual(self.mod.execute(None, "anota essa ideia: um app que resume reuniões"), "ok")
            self.assertEqual(save.call_args[0][0], "Um app que resume reuniões")
            self.assertIn("Qual é a ideia", self.mod.execute(None, "anota essa ideia"))
            self.assertEqual(self.mod.execute("painel para a cozinha", "anota essa ideia"), "ok")
        self.assertEqual(save.call_count, 2)
        self.assertEqual(self.mod.INTENT, "INSIGHT_SAVE")


if __name__ == "__main__":
    unittest.main()
