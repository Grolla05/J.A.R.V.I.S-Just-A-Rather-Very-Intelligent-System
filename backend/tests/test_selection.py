"""core.selection + clipboard.translate_auto — copiar seleção e escolher o idioma alvo."""
import unittest

from tests._stubs import install

install()

from core import clipboard, selection  # noqa: E402


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class TestCopySelection(unittest.TestCase):
    def _copy(self, changes_after_copy=True, text="  texto selecionado  ", held=0):
        clock = _Clock()
        seq = {"n": 1}
        presses = {"left": held}
        sent = []

        def is_down(_vk):
            if presses["left"] > 0:
                presses["left"] -= 1
                return True
            return False

        def send():
            sent.append("ctrl+c")
            if changes_after_copy:
                seq["n"] += 1

        result = selection.copy_selection(send_copy=send, sequence=lambda: seq["n"], read=lambda: text,
                                          is_down=is_down, sleep=clock.sleep, clock=clock)
        return result, sent

    def test_returns_trimmed_text(self):
        result, sent = self._copy()
        self.assertEqual(result, "texto selecionado")
        self.assertEqual(sent, ["ctrl+c"])

    def test_nothing_selected(self):
        result, _ = self._copy(changes_after_copy=False)
        self.assertIsNone(result)

    def test_waits_for_modifiers(self):
        result, sent = self._copy(held=10)
        self.assertEqual(result, "texto selecionado")

    def test_caps_size(self):
        result, _ = self._copy(text="a" * 10_000)
        self.assertEqual(len(result), selection.MAX_CHARS)

    def test_modifiers_timeout(self):
        clock = _Clock()
        self.assertFalse(selection.wait_modifiers_released(lambda vk: True, timeout=0.1,
                                                           sleep=clock.sleep, clock=clock))


class TestTranslateAuto(unittest.TestCase):
    def test_target(self):
        self.assertEqual(clipboard.translation_target("Eu não sei se a reunião é amanhã ou na sexta."),
                         clipboard.TARGET_EN)
        self.assertEqual(clipboard.translation_target("The meeting is on Friday and it will be long."),
                         clipboard.TARGET_PT)
        self.assertEqual(clipboard.translation_target("Der Hund ist sehr gross"), clipboard.TARGET_PT)

    def test_uses_prompt_and_model(self):
        seen = {}

        def query(messages, temperature):
            seen["prompt"] = messages[0]["content"]
            return "  Olá mundo  "

        text, target = clipboard.translate_auto("Hello world, this is the text", query=query)
        self.assertEqual(text, "Olá mundo")
        self.assertEqual(target, clipboard.TARGET_PT)
        self.assertIn("português do Brasil", seen["prompt"])
        self.assertIn("Hello world", seen["prompt"])

    def test_model_offline(self):
        self.assertEqual(clipboard.translate_auto("Hello there my friend", query=lambda m, temperature: None)[0],
                         None)


if __name__ == "__main__":
    unittest.main()
