"""Camada de infraestrutura do Spotify (core/spotify.py).

Cobre só o que é determinístico: geração do par PKCE, validade de token,
whitelist de URI, escolha de dispositivo e a FORMA dos requests à Web API.
O que depende da Windows API (EnumWindows, ShowWindow, keybd_event) e o
consentimento no navegador exigem um Spotify real e são validados manualmente.
"""
import base64
import hashlib
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

import core.spotify as sp


class TestBuildPkcePair(unittest.TestCase):
    def test_verifier_respeita_o_tamanho_da_rfc_7636(self):
        for _ in range(20):
            verifier, _ = sp._build_pkce_pair()
            self.assertGreaterEqual(len(verifier), 43)
            self.assertLessEqual(len(verifier), 128)

    def test_verifier_usa_apenas_caracteres_permitidos(self):
        permitidos = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
        )
        verifier, _ = sp._build_pkce_pair()
        self.assertTrue(set(verifier).issubset(permitidos))

    def test_challenge_e_base64url_sem_padding(self):
        _, challenge = sp._build_pkce_pair()
        self.assertNotIn("=", challenge)
        self.assertNotIn("+", challenge)
        self.assertNotIn("/", challenge)

    def test_challenge_e_o_sha256_do_verifier(self):
        verifier, challenge = sp._build_pkce_pair()
        esperado = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        self.assertEqual(challenge, esperado)

    def test_cada_chamada_gera_um_verifier_novo(self):
        pares = {sp._build_pkce_pair()[0] for _ in range(10)}
        self.assertEqual(len(pares), 10)


class TestTokenIsExpired(unittest.TestCase):
    def test_token_com_folga_e_valido(self):
        # Vence daqui a 10 min, margem de 60s -> ainda vale.
        self.assertFalse(sp._token_is_expired(1_000_600, now=1_000_000))

    def test_token_dentro_da_margem_ja_conta_como_vencido(self):
        # Vence em 30s: sai válido mas chega expirado.
        self.assertTrue(sp._token_is_expired(1_000_030, now=1_000_000))

    def test_limite_exato_da_margem_e_vencido(self):
        self.assertTrue(sp._token_is_expired(1_000_060, now=1_000_000))

    def test_um_segundo_alem_da_margem_e_valido(self):
        self.assertFalse(sp._token_is_expired(1_000_061, now=1_000_000))

    def test_ausencia_de_expires_at_e_vencido(self):
        for valor in (None, "", "1000000", [], {}):
            with self.subTest(valor=valor):
                self.assertTrue(sp._token_is_expired(valor, now=1_000_000))


class TestSanitizeSpotifyUri(unittest.TestCase):
    def test_uri_valida_passa_intacta(self):
        uri = "spotify:playlist:0XkPXLnaDEjO04Z3ZvrHIk"
        self.assertEqual(sp._sanitize_spotify_uri(uri), uri)

    def test_remove_sufixo_play_legado(self):
        self.assertEqual(
            sp._sanitize_spotify_uri("spotify:playlist:ABC123:play"),
            "spotify:playlist:ABC123"
        )

    def test_remove_espacos_em_volta(self):
        self.assertEqual(
            sp._sanitize_spotify_uri("  spotify:playlist:ABC123  "),
            "spotify:playlist:ABC123"
        )

    def test_aceita_album_e_track(self):
        for uri in ("spotify:album:ABC123", "spotify:track:ABC123"):
            with self.subTest(uri=uri):
                self.assertEqual(sp._sanitize_spotify_uri(uri), uri)

    def test_rejeita_injecao_de_shell(self):
        maliciosas = [
            "spotify:playlist:ABC & calc.exe",
            "spotify:playlist:ABC && shutdown /s",
            'spotify:playlist:ABC" | del C:\\',
        ]
        for uri in maliciosas:
            with self.subTest(uri=uri):
                self.assertEqual(sp._sanitize_spotify_uri(uri), "")

    def test_rejeita_esquema_estranho(self):
        for uri in ("http://evil.com", "spotify:artist:ABC", "playlist:ABC", ""):
            with self.subTest(uri=uri):
                self.assertEqual(sp._sanitize_spotify_uri(uri), "")

    def test_rejeita_nao_string(self):
        for valor in (None, 42, ["spotify:playlist:ABC"]):
            with self.subTest(valor=valor):
                self.assertEqual(sp._sanitize_spotify_uri(valor), "")


class TestIsPlayingTitle(unittest.TestCase):
    def test_titulos_ociosos_nao_sao_reproducao(self):
        ociosos = ["Spotify", "Spotify Premium", "Spotify Free",
                   "  spotify  ", "SPOTIFY PREMIUM", ""]
        for titulo in ociosos:
            with self.subTest(titulo=titulo):
                self.assertFalse(sp._is_playing_title(titulo))

    def test_titulo_de_faixa_indica_reproducao(self):
        tocando = ["Foo Fighters - Everlong",
                   "Legião Urbana - Tempo Perdido",
                   "AC/DC - Thunderstruck"]
        for titulo in tocando:
            with self.subTest(titulo=titulo):
                self.assertTrue(sp._is_playing_title(titulo))

    def test_nao_string_nao_e_reproducao(self):
        for valor in (None, 0, []):
            with self.subTest(valor=valor):
                self.assertFalse(sp._is_playing_title(valor))


class TestPickDevice(unittest.TestCase):
    PC = {"id": "pc", "name": "JARVIS-PC", "type": "Computer", "is_active": False}
    CELULAR = {"id": "cel", "name": "Galaxy", "type": "Smartphone", "is_active": False}
    TV = {"id": "tv", "name": "Sala", "type": "TV", "is_active": True}

    def test_lista_vazia_nao_tem_dispositivo(self):
        for valor in ([], None):
            with self.subTest(valor=valor):
                self.assertIsNone(sp._pick_device(valor))

    def test_dispositivo_ativo_tem_prioridade_absoluta(self):
        escolhido = sp._pick_device([self.PC, self.TV], hostname="JARVIS-PC")
        self.assertEqual(escolhido["id"], "tv")

    def test_casa_pelo_nome_do_host_quando_ninguem_esta_ativo(self):
        escolhido = sp._pick_device([self.CELULAR, self.PC], hostname="jarvis-pc")
        self.assertEqual(escolhido["id"], "pc")

    def test_cai_para_qualquer_computador_sem_casar_o_host(self):
        escolhido = sp._pick_device([self.CELULAR, self.PC], hostname="OUTRA-MAQUINA")
        self.assertEqual(escolhido["id"], "pc")

    def test_cai_para_o_primeiro_quando_nao_ha_computador(self):
        escolhido = sp._pick_device([self.CELULAR], hostname="JARVIS-PC")
        self.assertEqual(escolhido["id"], "cel")


class TestJsonHelper(unittest.TestCase):
    """204 e corpo vazio são respostas NORMAIS nos endpoints de player."""

    def test_resposta_ausente_vira_none(self):
        self.assertIsNone(sp.SpotifyClient._json(None))

    def test_204_vira_none(self):
        r = MagicMock(status_code=204, content=b"")
        self.assertIsNone(sp.SpotifyClient._json(r))

    def test_corpo_vazio_vira_none(self):
        r = MagicMock(status_code=200, content=b"")
        self.assertIsNone(sp.SpotifyClient._json(r))

    def test_corpo_invalido_vira_none_em_vez_de_explodir(self):
        r = MagicMock(status_code=200, content=b"<html>")
        r.json.side_effect = ValueError("not json")
        self.assertIsNone(sp.SpotifyClient._json(r))

    def test_corpo_valido_e_desserializado(self):
        r = MagicMock(status_code=200, content=b'{"a": 1}')
        r.json.return_value = {"a": 1}
        self.assertEqual(sp.SpotifyClient._json(r), {"a": 1})


class TestFormaDosRequests(unittest.TestCase):
    """Garante que cada ação bate no verbo, na rota e no corpo certos."""

    def setUp(self):
        self.client = sp.SpotifyClient()
        self.patcher = patch.object(sp.SpotifyClient, "_req")
        self.req = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.req.return_value = MagicMock(status_code=204, content=b"")

    def test_play_com_faixas_manda_uris(self):
        self.client.play(uris=["spotify:track:ABC"])
        metodo, rota = self.req.call_args[0]
        self.assertEqual(metodo, "PUT")
        self.assertEqual(rota, "/me/player/play")
        self.assertEqual(self.req.call_args[1]["json"], {"uris": ["spotify:track:ABC"]})

    def test_play_com_contexto_manda_context_uri(self):
        self.client.play(context_uri="spotify:playlist:ABC")
        self.assertEqual(self.req.call_args[1]["json"],
                         {"context_uri": "spotify:playlist:ABC"})

    def test_play_sem_corpo_apenas_retoma(self):
        self.client.play()
        self.assertEqual(self.req.call_args[0], ("PUT", "/me/player/play"))
        self.assertNotIn("json", self.req.call_args[1])

    def test_device_id_vai_na_query_string(self):
        self.client.play(uris=["spotify:track:ABC"], device_id="pc 1")
        _, rota = self.req.call_args[0]
        self.assertEqual(rota, "/me/player/play?device_id=pc%201")

    def test_transporte_usa_os_verbos_http_corretos(self):
        casos = [
            (self.client.pause, ("PUT", "/me/player/pause")),
            (self.client.next_track, ("POST", "/me/player/next")),
            (self.client.previous_track, ("POST", "/me/player/previous")),
        ]
        for metodo, esperado in casos:
            with self.subTest(acao=esperado[1]):
                metodo()
                self.assertEqual(self.req.call_args[0], esperado)

    def test_fila_recusa_uri_invalida_sem_chamar_a_api(self):
        self.assertFalse(self.client.queue("spotify:playlist:ABC & calc.exe"))
        self.req.assert_not_called()

    def test_fila_envia_a_uri_escapada(self):
        self.client.queue("spotify:track:ABC123")
        metodo, rota = self.req.call_args[0]
        self.assertEqual(metodo, "POST")
        self.assertEqual(rota, "/me/player/queue?uri=spotify%3Atrack%3AABC123")

    def test_transfer_playback_manda_lista_de_ids(self):
        self.client.transfer_playback("pc", play=False)
        self.assertEqual(self.req.call_args[0], ("PUT", "/me/player"))
        self.assertEqual(self.req.call_args[1]["json"],
                         {"device_ids": ["pc"], "play": False})

    def test_busca_pluraliza_a_chave_e_filtra_itens_nulos(self):
        self.req.return_value = MagicMock(status_code=200, content=b"{}")
        self.req.return_value.json.return_value = {
            "tracks": {"items": [{"uri": "spotify:track:A"}, None]}
        }
        resultado = self.client.search("everlong", kind="track")
        self.assertEqual(resultado, [{"uri": "spotify:track:A"}])
        self.assertIn("/search?", self.req.call_args[0][1])
        self.assertIn("type=track", self.req.call_args[0][1])

    def test_busca_vazia_nao_chama_a_api(self):
        for valor in ("", None):
            with self.subTest(valor=valor):
                self.assertEqual(self.client.search(valor), [])
        self.req.assert_not_called()

    def test_busca_sem_resultado_devolve_lista_vazia(self):
        self.req.return_value = None
        self.assertEqual(self.client.search("nada"), [])


if __name__ == "__main__":
    unittest.main()
