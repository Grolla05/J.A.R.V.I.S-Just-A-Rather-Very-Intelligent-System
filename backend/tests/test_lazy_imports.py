"""TUI — importar o cérebro não pode abrir microfone nem motores de áudio."""
import sys
import unittest
from unittest.mock import MagicMock

from tests._stubs import install

install()

# Dependências de áudio substituídas por mocks: se alguém as instanciar no
# import, o mock registra a chamada e o teste falha.
_sr = MagicMock()
_pyttsx3 = MagicMock()
_pygame = MagicMock()
sys.modules.setdefault("speech_recognition", _sr)
sys.modules.setdefault("pyttsx3", _pyttsx3)
sys.modules.setdefault("pygame", _pygame)
sys.modules.setdefault("edge_tts", MagicMock())


class TestLazySenses(unittest.TestCase):
    def test_listen_does_not_open_mic_on_import(self):
        sys.modules.pop("services.listen", None)
        import services.listen as listen
        self.assertIsNone(listen.jarvis_ear)
        listen.ear_pause()   # sem ouvido criado: no-op, não abre o mic
        listen.ear_resume()
        self.assertIsNone(listen.jarvis_ear)
        sys.modules["speech_recognition"].Microphone.assert_not_called()

    def test_speak_is_silent_when_voice_disabled(self):
        sys.modules.pop("services.speak", None)
        import core.state as state
        import services.speak as speak
        shown = []
        state.voice_enabled = False
        state.announce = shown.append
        try:
            speak.speak("olá")
        finally:
            state.announce = None
        self.assertEqual(shown, ["olá"])
        self.assertIsNone(speak._engine_offline)
        self.assertFalse(speak._mixer_ready)


if __name__ == "__main__":
    unittest.main()
