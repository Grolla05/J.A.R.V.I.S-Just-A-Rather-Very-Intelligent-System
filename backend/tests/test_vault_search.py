"""Busca no vault: POST no plugin, palavras do assunto (não do pedido), ranking por
caminho/nota principal e aviso ao modelo quando a nota pedida não existe.

Caso real: "JARVIS acesse meu obsidian e leia a nota sobre o meu projeto OHMFLOW..."
buscava 'acesse obsidian leia nota' (com GET, que sempre voltava vazio) e o modelo
inventava o projeto."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import sys  # noqa: E402

from core.prompts import load_prompt  # noqa: E402

obsidian_mod = sys.modules["core.obsidian"]
client = obsidian_mod.obsidian

ASK = "JARVIS acesse meu obsidian e leia a nota sobre o meu projeto OHMFLOW e me diga do que que ele se trata"
OHM = "🚀 Projetos/OhmFlow"
RESULTS = [  # ordem e scores reais do plugin (negativos; perto de zero = melhor)
    {"filename": "🚀 Projetos/System Boost/System Boost - CHANGES.md", "score": -1.52},
    {"filename": "🚀 Projetos/System Boost/System Boost.md", "score": -6.47},
    {"filename": f"{OHM}/OhmFlow - 02 Arquitetura.md", "score": -31.5},
    {"filename": f"{OHM}/OhmFlow - 14 Módulo Resistor e Código de Cores.md", "score": -45.88},
]


class TestSearchEndpoint(unittest.TestCase):
    def test_simple_search_uses_post(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = [{"filename": "a.md", "score": -2.0}, {"filename": "b.md", "score": -1.0}]
        with patch.object(obsidian_mod.requests, "request", return_value=resp) as req:
            items = client.search_scored("ohmflow")
        self.assertEqual(req.call_args.args[0], "POST")
        self.assertIn("/search/simple/?query=ohmflow", req.call_args.args[1])
        self.assertEqual(req.call_args.kwargs["timeout"], obsidian_mod.SEARCH_TIMEOUT_S)
        self.assertEqual([i["filename"] for i in items], ["b.md", "a.md"])

    def test_legacy_search_uses_post(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = []
        with patch.object(obsidian_mod.requests, "request", return_value=resp) as req:
            client.search("ohmflow")
        self.assertEqual(req.call_args.args[0], "POST")


class TestKeywords(unittest.TestCase):
    def test_request_words_do_not_take_the_slots(self):
        self.assertEqual(obsidian_mod.search_keywords(ASK), ["ohmflow"])

    def test_proper_noun_comes_first(self):
        kws = obsidian_mod.search_keywords("explique a arquitetura do banco de dados do System Boost")
        self.assertEqual(kws[:2], ["system", "boost"])
        self.assertIn("arquitetura", kws)

    def test_at_most_four(self):
        self.assertEqual(len(obsidian_mod.search_keywords("alfa beta gama delta épsilon zeta")), 4)


class TestRanking(unittest.TestCase):
    def test_path_with_keyword_beats_plugin_score(self):
        best = obsidian_mod._rank(RESULTS, ["ohmflow"])[0]
        self.assertTrue(best["filename"].startswith(OHM))

    def test_main_note_wins_inside_the_folder(self):
        results = RESULTS + [{"filename": f"{OHM}/OhmFlow.md", "score": -80.0}]
        self.assertEqual(obsidian_mod._rank(results, ["ohmflow"])[0]["filename"], f"{OHM}/OhmFlow.md")


class TestVaultContextOhmflow(unittest.TestCase):
    def setUp(self):
        obsidian_mod._search_warned = False

    def test_project_question_reads_the_project_main_note(self):
        notes = {f"{OHM}/OhmFlow.md": "# OhmFlow\nControle de estoque de resistores em C99."}
        with patch.object(client, "search_scored", return_value=RESULTS) as search, \
             patch.object(client, "get_file", side_effect=lambda p, quiet=False: notes.get(p)):
            name, content = obsidian_mod.get_vault_context(ASK)
        self.assertEqual(search.call_args.args[0], "ohmflow")
        self.assertEqual(name, f"{OHM}/OhmFlow.md")
        self.assertIn("resistores", content)

    def test_empty_multi_word_search_retries_main_keyword(self):
        notes = {f"{OHM}/OhmFlow.md": "# OhmFlow\nResumo.",
                 f"{OHM}/OhmFlow - 02 Arquitetura.md": "# Arquitetura do OhmFlow\nMódulos C99."}
        with patch.object(client, "search_scored", side_effect=[[], RESULTS]) as search, \
             patch.object(client, "get_file", side_effect=lambda p, quiet=False: notes.get(p)):
            name, _ = obsidian_mod.get_vault_context("me fala da arquitetura do OhmFlow")
        self.assertEqual([c.args[0] for c in search.call_args_list], ["ohmflow arquitetura", "ohmflow"])
        self.assertEqual(name, f"{OHM}/OhmFlow - 02 Arquitetura.md")  # nota do tema, não o resumo

    def test_falls_back_to_best_note_without_main_note(self):
        with patch.object(client, "search_scored", return_value=RESULTS), \
             patch.object(client, "get_file", side_effect=lambda p, quiet=False:
                          "OhmFlow: arquitetura em módulos" if "02 Arquitetura" in p else None):
            name, _ = obsidian_mod.get_vault_context(ASK)
        self.assertEqual(name, f"{OHM}/OhmFlow - 02 Arquitetura.md")


class TestAsksVault(unittest.TestCase):
    def test_explicit_vault_requests(self):
        for text in (ASK, "o que diz minha nota de cálculo?", "abre o vault", "resuma meus projetos"):
            with self.subTest(text=text):
                self.assertTrue(obsidian_mod.asks_vault(text))

    def test_ordinary_questions(self):
        for text in ("qual a capital da França?", "notaram a mudança?", "me conta uma piada"):
            with self.subTest(text=text):
                self.assertFalse(obsidian_mod.asks_vault(text))


class TestVaultNotFoundPrompt(unittest.TestCase):
    def _messages(self, **kwargs):
        from services import chat
        with patch.object(chat, "get_session_history_for_ai", return_value=[]), \
             patch.object(chat.state, "sys_monitor"):
            return chat.build_messages("pergunta", **kwargs)

    def test_missing_note_adds_warning(self):
        contents = [m["content"] for m in self._messages(vault_missing=True)]
        self.assertIn(load_prompt("vault_not_found.md").strip(), contents)

    def test_found_note_wins_over_missing_flag(self):
        contents = [m["content"] for m in self._messages(vault_context="nota", vault_filename="x.md",
                                                         vault_missing=True)]
        self.assertNotIn(load_prompt("vault_not_found.md").strip(), contents)

    def test_no_warning_by_default(self):
        contents = [m["content"] for m in self._messages()]
        self.assertNotIn(load_prompt("vault_not_found.md").strip(), contents)

    def test_grounded_answers_use_low_temperature(self):
        from services import chat
        seen = {}

        def fake_stream(messages, temperature):
            seen["temperature"] = temperature
            yield "a"

        with patch.object(chat, "query_ollama_stream", fake_stream), \
             patch.object(chat, "get_session_history_for_ai", return_value=[]), \
             patch.object(chat.state, "sys_monitor"):
            list(chat.ask_local_ai_stream("oi", vault_missing=True))
        self.assertEqual(seen["temperature"], 0.1)


class TestBrainPassesMissingFlag(unittest.TestCase):
    def test_stream_flags_missing_vault_note(self):
        from services import brain
        captured = {}

        def fake_stream(*a, **k):
            captured.update(k)
            return iter(["ok"])

        with patch.object(brain, "_check_pending_action", return_value=None), \
             patch.object(brain, "classify_intent", return_value={"intent": "CHAT", "entity": None}), \
             patch.object(brain, "get_vault_context", return_value=("", "")), \
             patch.object(brain.live_context, "build", return_value=""), \
             patch.object(brain, "ask_local_ai_stream", side_effect=fake_stream):
            list(brain.execute_command_stream(ASK))
        self.assertTrue(captured["vault_missing"])


if __name__ == "__main__":
    unittest.main()
