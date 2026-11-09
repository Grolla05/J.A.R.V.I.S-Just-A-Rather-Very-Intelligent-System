"""Testes da skill WORK_MACRO que não dependem da Windows API.

Validação de URI e leitura do título do Spotify moraram aqui até irem para
`core/spotify.py` — hoje são cobertas por `test_spotify_client.py`. Aqui fica
o que é da skill: a configuração das cenas e a escolha do caminho da trilha
sonora (Web API quando autorizado, app local como rede de segurança).
"""
import importlib.util
import os
import unittest
from unittest import mock

from tests._stubs import install

install()

from core.spotify import _sanitize_spotify_uri  # noqa: E402

# A skill é carregada pelo SkillManager via spec_from_file_location — o teste
# espelha esse mesmo mecanismo para não depender do pacote `skills`.
_SKILL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "automation", "work_macros.py"
)
_spec = importlib.util.spec_from_file_location("work_macros", _SKILL_PATH)
work_macros = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(work_macros)

_URI = "spotify:playlist:0XkPXLnaDEjO04Z3ZvrHIk"


class TestScenesConfig(unittest.TestCase):
    def test_playlists_das_cenas_sao_validas(self):
        for nome, cena in work_macros.SCENES.items():
            if "playlist" in cena:
                with self.subTest(cena=nome):
                    self.assertNotEqual(
                        _sanitize_spotify_uri(cena["playlist"]), "",
                        f"Playlist da cena '{nome}' é inválida."
                    )

    def test_spotify_nao_duplicado_na_lista_de_apps(self):
        """Cenas com playlist não devem abrir o Spotify duas vezes."""
        for nome, cena in work_macros.SCENES.items():
            if "playlist" in cena:
                with self.subTest(cena=nome):
                    apps = [a.lower() for a in cena["apps"]]
                    self.assertNotIn("spotify", apps)


class TestStartPlaylist(unittest.TestCase):
    def _patch(self, authorized, play_ok=True):
        client = mock.Mock()
        client.is_authorized.return_value = authorized
        client.play.return_value = play_ok
        start_uri = mock.Mock(return_value=True)
        ensure = mock.Mock(return_value="dev-1")
        patches = [
            mock.patch.object(work_macros, "spotify", client),
            mock.patch.object(work_macros, "start_uri", start_uri),
            mock.patch.object(work_macros, "ensure_device_ready", ensure),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return client, start_uri, ensure

    def test_autorizado_usa_web_api(self):
        client, start_uri, ensure = self._patch(authorized=True)
        self.assertTrue(work_macros._start_playlist(_URI))
        ensure.assert_called_once()
        client.play.assert_called_once_with(context_uri=_URI, device_id="dev-1")
        start_uri.assert_not_called()

    def test_web_api_falhou_cai_no_app_local(self):
        client, start_uri, _ = self._patch(authorized=True, play_ok=False)
        self.assertTrue(work_macros._start_playlist(_URI))
        client.play.assert_called_once()
        start_uri.assert_called_once_with(_URI)

    def test_sem_autorizacao_vai_direto_ao_app_local(self):
        client, start_uri, ensure = self._patch(authorized=False)
        self.assertTrue(work_macros._start_playlist(_URI))
        ensure.assert_not_called()
        client.play.assert_not_called()
        start_uri.assert_called_once_with(_URI)


if __name__ == "__main__":
    unittest.main()
