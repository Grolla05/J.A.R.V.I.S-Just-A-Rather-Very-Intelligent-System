"""Helpers puros do subsistema Spotify da skill WORK_MACRO.

Cobre só o que não depende da Windows API: validação de URI e leitura do
estado de reprodução pelo título da janela. O resto (EnumWindows, ShowWindow,
keybd_event) exige um Spotify real e é validado manualmente.
"""
import importlib.util
import os
import unittest

from tests._stubs import install

install()

# A skill é carregada pelo SkillManager via spec_from_file_location — o teste
# espelha esse mesmo mecanismo para não depender do pacote `skills`.
_SKILL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "automation", "work_macros.py"
)
_spec = importlib.util.spec_from_file_location("work_macros", _SKILL_PATH)
work_macros = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(work_macros)


class TestSanitizeSpotifyUri(unittest.TestCase):
    def test_uri_valida_passa_intacta(self):
        uri = "spotify:playlist:0XkPXLnaDEjO04Z3ZvrHIk"
        self.assertEqual(work_macros._sanitize_spotify_uri(uri), uri)

    def test_remove_sufixo_play_legado(self):
        self.assertEqual(
            work_macros._sanitize_spotify_uri("spotify:playlist:ABC123:play"),
            "spotify:playlist:ABC123"
        )

    def test_remove_espacos_em_volta(self):
        self.assertEqual(
            work_macros._sanitize_spotify_uri("  spotify:playlist:ABC123  "),
            "spotify:playlist:ABC123"
        )

    def test_aceita_album_e_track(self):
        for uri in ("spotify:album:ABC123", "spotify:track:ABC123"):
            with self.subTest(uri=uri):
                self.assertEqual(work_macros._sanitize_spotify_uri(uri), uri)

    def test_rejeita_injecao_de_shell(self):
        maliciosas = [
            "spotify:playlist:ABC & calc.exe",
            "spotify:playlist:ABC && shutdown /s",
            'spotify:playlist:ABC" | del C:\\',
        ]
        for uri in maliciosas:
            with self.subTest(uri=uri):
                self.assertEqual(work_macros._sanitize_spotify_uri(uri), "")

    def test_rejeita_esquema_estranho(self):
        for uri in ("http://evil.com", "spotify:artist:ABC", "playlist:ABC", ""):
            with self.subTest(uri=uri):
                self.assertEqual(work_macros._sanitize_spotify_uri(uri), "")

    def test_rejeita_nao_string(self):
        for valor in (None, 42, ["spotify:playlist:ABC"]):
            with self.subTest(valor=valor):
                self.assertEqual(work_macros._sanitize_spotify_uri(valor), "")


class TestIsPlayingTitle(unittest.TestCase):
    def test_titulos_ociosos_nao_sao_reproducao(self):
        ociosos = ["Spotify", "Spotify Premium", "Spotify Free",
                   "  spotify  ", "SPOTIFY PREMIUM", ""]
        for titulo in ociosos:
            with self.subTest(titulo=titulo):
                self.assertFalse(work_macros._is_playing_title(titulo))

    def test_titulo_de_faixa_indica_reproducao(self):
        tocando = ["Foo Fighters - Everlong",
                   "Legião Urbana - Tempo Perdido",
                   "AC/DC - Thunderstruck"]
        for titulo in tocando:
            with self.subTest(titulo=titulo):
                self.assertTrue(work_macros._is_playing_title(titulo))

    def test_nao_string_nao_e_reproducao(self):
        for valor in (None, 0, []):
            with self.subTest(valor=valor):
                self.assertFalse(work_macros._is_playing_title(valor))


class TestScenesConfig(unittest.TestCase):
    def test_playlists_das_cenas_sao_validas(self):
        for nome, cena in work_macros.SCENES.items():
            if "playlist" in cena:
                with self.subTest(cena=nome):
                    self.assertNotEqual(
                        work_macros._sanitize_spotify_uri(cena["playlist"]), "",
                        f"Playlist da cena '{nome}' é inválida."
                    )

    def test_spotify_nao_duplicado_na_lista_de_apps(self):
        """Cenas com playlist não devem abrir o Spotify duas vezes."""
        for nome, cena in work_macros.SCENES.items():
            if "playlist" in cena:
                with self.subTest(cena=nome):
                    apps = [a.lower() for a in cena["apps"]]
                    self.assertNotIn("spotify", apps)


if __name__ == "__main__":
    unittest.main()
