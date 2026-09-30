"""num_ctx / num_gpu opcionais em core.llm: default não muda nada; configurados vão em
`options`; se o Ollama recusar num_gpu (VRAM), a opção é desativada e a chamada repete."""
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.llm as llm


def _ok(text="ok"):
    return {"message": {"content": text}}


def _failing_stream():
    raise RuntimeError("model requires more system memory")
    yield  # pragma: no cover


def _stream(*parts):
    return iter([{"message": {"content": p}} for p in parts])


class TestLlmOptions(unittest.TestCase):
    def setUp(self):
        llm._gpu_option_disabled = False

    def tearDown(self):
        llm._gpu_option_disabled = False

    def test_default_options_only_temperature(self):
        with patch.object(llm.settings, "OLLAMA_NUM_CTX", None), \
             patch.object(llm.settings, "OLLAMA_NUM_GPU", None):
            self.assertEqual(llm._build_options(0.3), {"temperature": 0.3})

    def test_configured_options_are_passed(self):
        with patch.object(llm.settings, "OLLAMA_NUM_CTX", 4096), \
             patch.object(llm.settings, "OLLAMA_NUM_GPU", 99):
            self.assertEqual(
                llm._build_options(0),
                {"temperature": 0, "num_ctx": 4096, "num_gpu": 99},
            )

    def test_num_gpu_zero_is_respected(self):
        # 0 = tudo na CPU; não pode ser tratado como "não configurado"
        with patch.object(llm.settings, "OLLAMA_NUM_CTX", None), \
             patch.object(llm.settings, "OLLAMA_NUM_GPU", 0):
            self.assertEqual(llm._build_options(0)["num_gpu"], 0)

    def test_query_falls_back_without_num_gpu(self):
        client = MagicMock()
        client.chat.side_effect = [RuntimeError("out of memory"), _ok("resposta")]
        with patch.object(llm.settings, "OLLAMA_NUM_CTX", 4096), \
             patch.object(llm.settings, "OLLAMA_NUM_GPU", 99), \
             patch.object(llm, "_get_client", return_value=client):
            out = llm.query_ollama([{"role": "user", "content": "oi"}])
        self.assertEqual(out, "resposta")
        self.assertEqual(client.chat.call_count, 2)
        first = client.chat.call_args_list[0].kwargs["options"]
        second = client.chat.call_args_list[1].kwargs["options"]
        self.assertIn("num_gpu", first)
        self.assertNotIn("num_gpu", second)
        self.assertEqual(second["num_ctx"], 4096)  # só num_gpu cai
        self.assertTrue(llm._gpu_option_disabled)

    def test_option_stays_disabled_for_later_calls(self):
        llm._gpu_option_disabled = True
        with patch.object(llm.settings, "OLLAMA_NUM_GPU", 99), \
             patch.object(llm.settings, "OLLAMA_NUM_CTX", None):
            self.assertNotIn("num_gpu", llm._build_options(0))

    def test_no_retry_when_num_gpu_not_configured(self):
        client = MagicMock()
        client.chat.side_effect = RuntimeError("offline")
        with patch.object(llm.settings, "OLLAMA_NUM_GPU", None), \
             patch.object(llm, "_get_client", return_value=client):
            out = llm.query_ollama([{"role": "user", "content": "oi"}])
        self.assertIsNone(out)
        self.assertEqual(client.chat.call_count, 1)

    def test_stream_falls_back_before_first_chunk(self):
        client = MagicMock()
        client.chat.side_effect = [_failing_stream(), _stream("a", "b")]
        with patch.object(llm.settings, "OLLAMA_NUM_GPU", 99), \
             patch.object(llm.settings, "OLLAMA_NUM_CTX", None), \
             patch.object(llm, "_get_client", return_value=client):
            out = list(llm.query_ollama_stream([{"role": "user", "content": "oi"}]))
        self.assertEqual(out, ["a", "b"])
        self.assertEqual(client.chat.call_count, 2)
        self.assertNotIn("num_gpu", client.chat.call_args_list[1].kwargs["options"])

    def test_stream_does_not_retry_after_output(self):
        def broken_after_one():
            yield {"message": {"content": "parcial"}}
            raise RuntimeError("caiu no meio")

        client = MagicMock()
        client.chat.side_effect = [broken_after_one()]
        with patch.object(llm.settings, "OLLAMA_NUM_GPU", 99), \
             patch.object(llm.settings, "OLLAMA_NUM_CTX", None), \
             patch.object(llm, "_get_client", return_value=client):
            out = list(llm.query_ollama_stream([{"role": "user", "content": "oi"}]))
        self.assertEqual(out, ["parcial", "Erro de processamento neural."])
        self.assertEqual(client.chat.call_count, 1)


if __name__ == "__main__":
    unittest.main()
