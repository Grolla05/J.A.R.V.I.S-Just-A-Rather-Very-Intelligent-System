"""Modo instalado (JARVIS_DATA_DIR) e defaults do core.config.

O config lê o ambiente no import, então cada cenário roda num processo Python
novo (subprocess) e devolve os caminhos em JSON.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

_PROBE = (
    "import json; from core.config import settings as s; print(json.dumps({"
    "'data': str(s.DIR_DATA), 'env': str(s.ENV_PATH), 'logs': str(s.DIR_LOGS),"
    "'db': str(s.DB_PATH), 'uploads': str(s.DIR_UPLOADS), 'sounds': str(s.DIR_SOUNDS),"
    "'token': str(s.SPOTIFY_TOKEN_PATH), 'installed': s.IS_INSTALLED,"
    "'rate': s.SPEECH_RATE, 'mic': s.MIC_INDEX, 'host': s.OLLAMA_HOST,"
    "'model': s.OLLAMA_MODEL, 'version': s.VERSION}))"
)

_ENV_KEYS = ("JARVIS_DATA_DIR", "SPEECH_RATE", "MIC_INDEX", "OLLAMA_HOST", "OLLAMA_MODEL")


def _probe(extra_env):
    env = {k: v for k, v in os.environ.items() if k not in _ENV_KEYS}
    env.update(extra_env)
    out = subprocess.run(
        [sys.executable, "-c", _PROBE], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=60, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


class InstalledModeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name) / "JARVIS"
        # .env mínimo, como o instalador copia (sem SPEECH_RATE/MIC_INDEX)
        self.data.mkdir()
        (self.data / ".env").write_text("OLLAMA_MODEL=qwen2.5:7b\n", encoding="utf-8")
        self.cfg = _probe({"JARVIS_DATA_DIR": str(self.data)})

    def tearDown(self):
        self._tmp.cleanup()

    def test_dados_gravaveis_vao_para_a_pasta_de_dados(self):
        for key in ("logs", "db", "uploads", "sounds", "token"):
            self.assertTrue(Path(self.cfg[key]).is_relative_to(self.data), key)
        self.assertTrue(self.cfg["installed"])

    def test_env_lido_da_pasta_de_dados(self):
        self.assertEqual(Path(self.cfg["env"]), self.data / ".env")
        self.assertEqual(self.cfg["model"], "qwen2.5:7b")

    def test_pastas_criadas_no_import(self):
        for sub in ("logs", "database", "uploads"):
            self.assertTrue((self.data / sub).is_dir(), sub)


class DevModeTest(unittest.TestCase):
    def test_sem_variavel_dados_ficam_no_backend(self):
        cfg = _probe({})
        self.assertFalse(cfg["installed"])
        self.assertEqual(Path(cfg["data"]), BACKEND)
        self.assertEqual(Path(cfg["db"]).parent, BACKEND / "database")


class DefaultsTest(unittest.TestCase):
    def test_defaults_sem_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            # pasta de dados vazia = nenhum .env para carregar
            cfg = _probe({"JARVIS_DATA_DIR": tmp})
        self.assertEqual(cfg["rate"], 180)
        self.assertEqual(cfg["mic"], 0)
        self.assertEqual(cfg["host"], "http://localhost:11434")
        self.assertEqual(cfg["model"], "llama3.2")
        self.assertTrue(cfg["version"])


if __name__ == "__main__":
    unittest.main()
