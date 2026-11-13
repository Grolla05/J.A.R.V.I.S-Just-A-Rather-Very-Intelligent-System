"""services/chat.py — prompts vêm de backend/prompts/*.md, nunca de string Python."""
import pathlib
import unittest
from unittest.mock import patch

from tests._stubs import install

install()

from core.prompts import PROMPTS_DIR, load_prompt  # noqa: E402
from services import chat  # noqa: E402

CHAT_SRC = pathlib.Path(chat.__file__).read_text(encoding="utf-8")
NEW_PROMPTS = ("mode_voice.md", "memory_read.md", "hardware_context.md", "live_data.md", "vault_memory.md")


def _messages(**kwargs):
    with patch.object(chat, "get_session_history_for_ai", return_value=[{"role": "user", "content": "antes"}]), \
         patch.object(chat.state, "sys_monitor") as mon:
        mon.get_realtime_context.return_value = "CPU 5%"
        mon.get_detailed_hardware_context.return_value = "GPU RTX 4070"
        return chat.build_messages("pergunta", **kwargs)


class TestPromptFiles(unittest.TestCase):
    def test_prompt_files_exist(self):
        for name in NEW_PROMPTS:
            self.assertTrue((pathlib.Path(PROMPTS_DIR) / name).is_file(), name)

    def test_no_prompt_text_left_in_python(self):
        for text in ("INSTRUÇÃO CRÍTICA", "MODO ATUAL", "USE ISSO", "LIVE DATA", "MEMÓRIA PESSOAL", "REGRAS DE ÁUDIO"):
            self.assertNotIn(text, CHAT_SRC)

    def test_memory_prompt_has_no_hardcoded_name(self):
        self.assertNotIn("Felipe", load_prompt("memory_read.md"))


class TestBuildMessages(unittest.TestCase):
    def test_order_and_content(self):
        msgs = _messages(mode="chat", intent_type="CHAT", vault_context="nota", vault_filename="Sobre mim.md",
                         live_context="[AGENDA] 09:00")
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["system", "system", "system", "system", "user", "user"])
        self.assertIn(load_prompt("mode_chat.md").strip(), msgs[0]["content"])
        self.assertEqual(msgs[1]["content"], load_prompt("live_data.md", live_data="CPU 5%").strip())
        self.assertEqual(msgs[2]["content"], load_prompt("vault_memory.md", note="Sobre mim.md", content="nota").strip())
        self.assertEqual(msgs[3]["content"], "[AGENDA] 09:00")
        self.assertEqual(msgs[-1], {"role": "user", "content": "pergunta"})

    def test_modes_pick_their_prompt(self):
        self.assertIn(load_prompt("mode_voice.md").strip(), _messages(mode="voice")[0]["content"])
        self.assertIn(load_prompt("mode_copilot.md").strip(), _messages(mode="copilot")[0]["content"])

    def test_hardware_and_memory_read_instructions(self):
        hw = _messages(intent_type="HARDWARE")[0]["content"]
        self.assertIn(load_prompt("hardware_context.md", hardware="GPU RTX 4070").strip(), hw)
        mem = _messages(intent_type="MEMORY_READ")[0]["content"]
        self.assertIn(load_prompt("memory_read.md").strip(), mem)
        self.assertNotIn(load_prompt("memory_read.md").strip(), _messages(intent_type="CHAT")[0]["content"])

    def test_no_vault_or_live_context_means_no_extra_system(self):
        msgs = _messages()
        self.assertEqual([m["role"] for m in msgs], ["system", "system", "user", "user"])

    def test_vault_content_with_dollar_is_kept(self):
        msgs = _messages(vault_context="custa $10 e $nome", vault_filename="a.md")
        self.assertIn("custa $10 e $nome", msgs[2]["content"])


class TestEntryPoints(unittest.TestCase):
    def test_voice_reply_is_cleaned_and_uses_voice_prompt(self):
        seen = {}

        def fake_query(messages, temperature):
            seen["messages"] = messages
            return "**Olá** # Senhor"

        with patch.object(chat, "query_ollama", fake_query), \
             patch.object(chat, "get_session_history_for_ai", return_value=[]), \
             patch.object(chat.state, "sys_monitor"):
            self.assertEqual(chat.ask_local_ai("oi"), "Olá  Senhor")
        self.assertIn(load_prompt("mode_voice.md").strip(), seen["messages"][0]["content"])

    def test_stream_uses_mode_and_temperature(self):
        seen = {}

        def fake_stream(messages, temperature):
            seen.update(messages=messages, temperature=temperature)
            yield "a"

        with patch.object(chat, "query_ollama_stream", fake_stream), \
             patch.object(chat, "get_session_history_for_ai", return_value=[]), \
             patch.object(chat.state, "sys_monitor"):
            self.assertEqual(list(chat.ask_local_ai_stream("oi", mode="copilot")), ["a"])
        self.assertIn(load_prompt("mode_copilot.md").strip(), seen["messages"][0]["content"])
        self.assertEqual(seen["temperature"], 0.7)


if __name__ == "__main__":
    unittest.main()
