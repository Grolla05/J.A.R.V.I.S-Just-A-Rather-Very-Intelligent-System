"""Helpers puros da skill SPOTIFY_CONTROL.

O foco é o roteamento barato: `_parse_fast` precisa resolver transporte SEM
tocar no Ollama, e `_best_playlist_match` precisa errar pouco quando o STT
entende o nome da playlist pela metade. A rede é exercitada manualmente.
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
    "skills", "automation", "spotify_control.py"
)
_spec = importlib.util.spec_from_file_location("spotify_control", _SKILL_PATH)
spotify_control = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spotify_control)


class TestNormalize(unittest.TestCase):
    def test_baixa_caixa_e_apara_bordas(self):
        self.assertEqual(spotify_control._normalize("  PAUSA  "), "pausa")

    def test_remove_pontuacao_e_colapsa_espacos(self):
        self.assertEqual(
            spotify_control._normalize("Que música é essa??"),
            "que música é essa"
        )

    def test_nao_string_vira_vazio(self):
        for valor in (None, 42, []):
            with self.subTest(valor=valor):
                self.assertEqual(spotify_control._normalize(valor), "")


class TestParseFast(unittest.TestCase):
    """Estes comandos NÃO podem custar um roundtrip de inferência."""

    def test_reconhece_pausa(self):
        for frase in ("pausa", "pausar", "Pausa!", "para a música",
                      "pausa a musica", "jarvis, pausar música"):
            with self.subTest(frase=frase):
                self.assertEqual(spotify_control._parse_fast(frase), "PAUSE")

    def test_reconhece_proxima(self):
        for frase in ("próxima música", "proxima musica", "pula essa",
                      "passa a música", "próxima"):
            with self.subTest(frase=frase):
                self.assertEqual(spotify_control._parse_fast(frase), "NEXT")

    def test_reconhece_anterior(self):
        for frase in ("volta essa", "música anterior", "musica anterior",
                      "voltar música", "anterior"):
            with self.subTest(frase=frase):
                self.assertEqual(spotify_control._parse_fast(frase), "PREVIOUS")

    def test_reconhece_now_playing(self):
        for frase in ("que música é essa?", "que musica e essa",
                      "o que está tocando", "qual o nome dessa música"):
            with self.subTest(frase=frase):
                self.assertEqual(spotify_control._parse_fast(frase), "NOW_PLAYING")

    def test_reconhece_retomar(self):
        for frase in ("retoma", "continua a música", "volta a tocar", "despausa"):
            with self.subTest(frase=frase):
                self.assertEqual(spotify_control._parse_fast(frase), "RESUME")

    def test_pedido_de_busca_cai_para_o_llm(self):
        """Frase com nome de faixa/playlist tem que devolver None."""
        for frase in ("toque Comfortably Numb",
                      "coloca algo do Pink Floyd",
                      "toca minha playlist de foco",
                      "põe uma playlist de rock anos 80",
                      "adiciona Bohemian Rhapsody na fila"):
            with self.subTest(frase=frase):
                self.assertIsNone(spotify_control._parse_fast(frase))

    def test_comando_vazio_cai_para_o_llm(self):
        for valor in ("", "   ", None):
            with self.subTest(valor=valor):
                self.assertIsNone(spotify_control._parse_fast(valor))

    def test_nao_casa_no_meio_de_outra_palavra(self):
        """'pausa' dentro de 'pausadamente' não pode disparar PAUSE."""
        self.assertIsNone(spotify_control._parse_fast("toque algo pausadamente"))


class TestBestPlaylistMatch(unittest.TestCase):
    PLAYLISTS = [
        {"name": "Foco Profundo 2024", "uri": "spotify:playlist:A"},
        {"name": "Rock 80", "uri": "spotify:playlist:B"},
        {"name": "Lo-Fi", "uri": "spotify:playlist:C"},
    ]

    def test_nome_exato(self):
        achada = spotify_control._best_playlist_match("rock 80", self.PLAYLISTS)
        self.assertEqual(achada["uri"], "spotify:playlist:B")

    def test_substring_acha_a_playlist_completa(self):
        """'foco' precisa achar 'Foco Profundo 2024' — o difflib sozinho erra
        esse caso porque a diferença de comprimento derruba o score."""
        achada = spotify_control._best_playlist_match("foco", self.PLAYLISTS)
        self.assertEqual(achada["uri"], "spotify:playlist:A")

    def test_fuzzy_acima_do_cutoff(self):
        achada = spotify_control._best_playlist_match("lofi", self.PLAYLISTS)
        self.assertEqual(achada["uri"], "spotify:playlist:C")

    def test_abaixo_do_cutoff_nao_casa(self):
        self.assertIsNone(
            spotify_control._best_playlist_match("sertanejo universitário",
                                                 self.PLAYLISTS)
        )

    def test_lista_vazia_ou_nome_vazio(self):
        self.assertIsNone(spotify_control._best_playlist_match("foco", []))
        self.assertIsNone(spotify_control._best_playlist_match("", self.PLAYLISTS))
        self.assertIsNone(spotify_control._best_playlist_match(None, self.PLAYLISTS))

    def test_ignora_playlists_corrompidas(self):
        """A API devolve None no meio da lista quando a playlist foi apagada."""
        sujas = [None, {"name": None}, {"name": "Foco Profundo 2024",
                                        "uri": "spotify:playlist:A"}]
        achada = spotify_control._best_playlist_match("foco", sujas)
        self.assertEqual(achada["uri"], "spotify:playlist:A")


class TestArtistNames(unittest.TestCase):
    def test_um_artista(self):
        item = {"artists": [{"name": "Foo Fighters"}]}
        self.assertEqual(spotify_control._artist_names(item), "Foo Fighters")

    def test_dois_artistas(self):
        item = {"artists": [{"name": "Queen"}, {"name": "David Bowie"}]}
        self.assertEqual(spotify_control._artist_names(item), "Queen e David Bowie")

    def test_tres_artistas(self):
        item = {"artists": [{"name": "A"}, {"name": "B"}, {"name": "C"}]}
        self.assertEqual(spotify_control._artist_names(item), "A, B e C")

    def test_sem_artistas(self):
        for item in ({}, None, {"artists": []}, {"artists": [{}]}):
            with self.subTest(item=item):
                self.assertEqual(spotify_control._artist_names(item), "")


class TestFormatSearchResult(unittest.TestCase):
    def test_faixa_com_artista(self):
        item = {"name": "Everlong", "artists": [{"name": "Foo Fighters"}]}
        self.assertEqual(spotify_control._format_search_result(item),
                         "Everlong de Foo Fighters")

    def test_faixa_sem_artista(self):
        self.assertEqual(spotify_control._format_search_result({"name": "Everlong"}),
                         "Everlong")

    def test_item_vazio(self):
        self.assertEqual(spotify_control._format_search_result(None), "a faixa")


class TestFormatNowPlaying(unittest.TestCase):
    def test_nada_tocando(self):
        esperado = "Não há nada tocando no momento, senhor."
        for payload in (None, {}, {"item": None}, {"is_playing": True}):
            with self.subTest(payload=payload):
                self.assertEqual(spotify_control._format_now_playing(payload), esperado)

    def test_faixa_tocando(self):
        payload = {
            "is_playing": True,
            "item": {"type": "track", "name": "Everlong",
                     "artists": [{"name": "Foo Fighters"}]},
        }
        self.assertEqual(spotify_control._format_now_playing(payload),
                         "Está tocando Everlong de Foo Fighters.")

    def test_faixa_pausada(self):
        payload = {
            "is_playing": False,
            "item": {"type": "track", "name": "Everlong",
                     "artists": [{"name": "Foo Fighters"}]},
        }
        self.assertEqual(spotify_control._format_now_playing(payload),
                         "Está pausado em Everlong de Foo Fighters.")

    def test_podcast_nao_explode_por_falta_de_artists(self):
        payload = {
            "is_playing": True,
            "item": {"type": "episode", "name": "Episódio 42",
                     "show": {"name": "Flow"}},
        }
        self.assertEqual(spotify_control._format_now_playing(payload),
                         "Está tocando o episódio Episódio 42, do podcast Flow.")

    def test_podcast_sem_nome_do_show(self):
        payload = {"is_playing": True,
                   "item": {"type": "episode", "name": "Episódio 42"}}
        self.assertEqual(spotify_control._format_now_playing(payload),
                         "Está tocando o episódio Episódio 42.")


class TestContratoDaSkill(unittest.TestCase):
    def test_expoe_intent_e_execute(self):
        self.assertEqual(spotify_control.INTENT, "SPOTIFY_CONTROL")
        self.assertTrue(callable(spotify_control.execute))

    def test_prompt_text_tem_dois_pontos(self):
        """O bridge monta a descrição do card do frontend com
        PROMPT_TEXT.split(':')[-1] — sem ':' o card fica ilegível."""
        self.assertIn(":", spotify_control.PROMPT_TEXT)

    def test_execute_sem_client_id_nao_chama_a_api(self):
        original = spotify_control.settings.SPOTIFY_CLIENT_ID
        spotify_control.settings.SPOTIFY_CLIENT_ID = ""
        try:
            resposta = spotify_control.execute(None, "toque Everlong")
            self.assertIn("SPOTIFY_CLIENT_ID", resposta)
        finally:
            spotify_control.settings.SPOTIFY_CLIENT_ID = original


if __name__ == "__main__":
    unittest.main()
