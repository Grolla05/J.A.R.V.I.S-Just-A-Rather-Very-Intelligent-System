"""Skill de controle do Spotify via Web API.

Roteamento em dois estágios, por custo:

1. `_parse_fast()` — tabela de verbos. Resolve pausar/próxima/anterior/retomar/
   o-que-está-tocando em microssegundos, SEM tocar no Ollama. "pausa" não pode
   custar um roundtrip de inferência.
2. `_ask_ollama_spotify_expert()` — só quando sobra uma query de busca, que é
   quando de fato precisamos de um LLM para separar verbo de nome de faixa.
"""
import difflib
import json

from core import log
from core.config import settings
from core.llm import query_ollama
from core.prompts import load_prompt
from core.spotify import (
    ensure_device_ready,
    spotify,
    start_authorization,
    start_uri,
)

# --- CONFIGURAÇÃO DA SKILL ---
INTENT = "SPOTIFY_CONTROL"
PROMPT_TEXT = load_prompt("skills/spotify_control.md")

# --- CÉREBRO ESPECÍFICO DA SKILL (CURADOR MUSICAL) ---
SPOTIFY_DECISION_PROMPT = load_prompt("skills/spotify_decision.md")

# Cutoff do fuzzy match de playlist. Mesmo valor de app_control.find_best_match:
# abaixo disso o difflib começa a casar playlists completamente erradas.
PLAYLIST_MATCH_CUTOFF = 0.6

# Verbos que dispensam o LLM. A ordem importa: a primeira entrada que casar
# vence, então frases mais específicas vêm antes das genéricas.
FAST_VERBS = (
    ("NOW_PLAYING", (
        "que musica e essa", "que música é essa", "qual musica e essa",
        "qual música é essa", "que musica esta tocando", "que música está tocando",
        "o que esta tocando", "o que está tocando", "qual o nome dessa musica",
        "qual o nome dessa música", "que faixa e essa", "que faixa é essa",
    )),
    ("PREVIOUS", (
        "musica anterior", "música anterior", "faixa anterior", "volta a musica",
        "volta a música", "voltar musica", "voltar música", "volta essa",
        "musica passada", "música passada", "anterior",
    )),
    ("NEXT", (
        "proxima musica", "próxima música", "proxima faixa", "próxima faixa",
        "pula essa", "pular musica", "pular música", "pula a musica",
        "pula a música", "passa a musica", "passa a música", "proxima", "próxima",
    )),
    ("PAUSE", (
        "pausa a musica", "pausa a música", "pausar musica", "pausar música",
        "para a musica", "para a música", "parar musica", "parar música",
        "pausa", "pausar", "pause", "silencia a musica", "silencia a música",
    )),
    ("RESUME", (
        "retoma a musica", "retoma a música", "retomar musica", "retomar música",
        "continua a musica", "continua a música", "continuar musica",
        "continuar música", "volta a tocar", "retoma", "retomar", "despausa",
    )),
)


# ============================================================================
# HELPERS PUROS (testáveis sem rede)
# ============================================================================
def _normalize(text):
    """Minúsculas, sem pontuação de borda e com espaços colapsados."""
    if not isinstance(text, str):
        return ""
    limpo = text.lower().strip()
    for char in "?!.,;:":
        limpo = limpo.replace(char, " ")
    return " ".join(limpo.split())


def _parse_fast(command):
    """Resolve comandos de transporte sem LLM. None = precisa do cérebro."""
    texto = _normalize(command)
    if not texto:
        return None

    for action, gatilhos in FAST_VERBS:
        for gatilho in gatilhos:
            if gatilho == texto or f" {gatilho} " in f" {texto} ":
                return action
    return None


def _best_playlist_match(name, playlists):
    """Casa o nome falado com uma playlist do usuário.

    Mesmo mecanismo de `app_control.find_best_match`: difflib com cutoff 0.6,
    para não tocar a playlist errada quando o STT entende mal.
    """
    alvo = _normalize(name)
    if not alvo or not playlists:
        return None

    por_nome = {}
    for playlist in playlists:
        chave = _normalize((playlist or {}).get("name"))
        if chave:
            por_nome.setdefault(chave, playlist)

    if alvo in por_nome:
        return por_nome[alvo]

    # Substring: "foco" acha "Foco Profundo 2024" — o difflib erra esse caso,
    # porque a diferença de comprimento derruba o score abaixo do cutoff.
    contidos = [k for k in por_nome if alvo in k]
    if contidos:
        return por_nome[min(contidos, key=len)]

    matches = difflib.get_close_matches(alvo, list(por_nome.keys()), n=1,
                                        cutoff=PLAYLIST_MATCH_CUTOFF)
    return por_nome[matches[0]] if matches else None


def _artist_names(item):
    """Extrai 'Artista A e Artista B' de um objeto de faixa."""
    artistas = [a.get("name") for a in (item or {}).get("artists") or [] if a.get("name")]
    if not artistas:
        return ""
    if len(artistas) == 1:
        return artistas[0]
    return f"{', '.join(artistas[:-1])} e {artistas[-1]}"


def _format_search_result(item):
    """Descreve uma faixa em texto puro — o retorno vai direto para o TTS."""
    if not item:
        return "a faixa"
    nome = item.get("name") or "faixa desconhecida"
    artistas = _artist_names(item)
    return f"{nome} de {artistas}" if artistas else nome


def _format_now_playing(payload):
    """Traduz /me/player/currently-playing numa frase falável."""
    if not payload:
        return "Não há nada tocando no momento, senhor."

    item = payload.get("item")
    if not item:
        return "Não há nada tocando no momento, senhor."

    # Podcasts vêm como 'episode' e não têm o campo 'artists'.
    if item.get("type") == "episode":
        nome = item.get("name") or "um episódio"
        show = ((item.get("show") or {}).get("name")) or ""
        base = f"Está tocando o episódio {nome}"
        return f"{base}, do podcast {show}." if show else f"{base}."

    descricao = _format_search_result(item)
    prefixo = "Está tocando" if payload.get("is_playing") else "Está pausado em"
    return f"{prefixo} {descricao}."


def _ask_ollama_spotify_expert(command):
    """Sub-agente: traduz a frase do usuário em {action, query}."""
    resposta = query_ollama(
        [{"role": "system", "content": SPOTIFY_DECISION_PROMPT},
         {"role": "user", "content": command}],
        format="json",
        temperature=0.1,
        timeout=settings.TIMEOUT_API
    )
    if not resposta:
        return None
    try:
        decisao = json.loads(resposta)
        return decisao if isinstance(decisao, dict) else None
    except (ValueError, TypeError) as e:
        log.error(f"❌ [SPOTIFY] Resposta do curador não é JSON válido: {e}")
        return None


# ============================================================================
# AÇÕES
# ============================================================================
def _play_track(query):
    resultados = spotify.search(query, kind="track", limit=1)
    if not resultados:
        return f"Não encontrei nada parecido com {query} no Spotify, senhor."

    faixa = resultados[0]
    device_id = ensure_device_ready()
    if spotify.play(uris=[faixa["uri"]], device_id=device_id):
        return f"Tocando {_format_search_result(faixa)}."

    # A Web API falhou (sem Premium, sem device utilizável). O app local resolve.
    if start_uri(faixa["uri"]):
        return f"Tocando {_format_search_result(faixa)}."
    return "Encontrei a faixa, mas não consegui iniciar a reprodução, senhor."


def _play_playlist(query):
    playlist = _best_playlist_match(query, spotify.my_playlists())

    if not playlist:
        # Não é uma playlist do usuário — procura no catálogo público.
        publicas = spotify.search(query, kind="playlist", limit=1)
        playlist = publicas[0] if publicas else None

    if not playlist:
        return f"Não localizei nenhuma playlist chamada {query}, senhor."

    nome = playlist.get("name") or query
    device_id = ensure_device_ready()
    if spotify.play(context_uri=playlist["uri"], device_id=device_id):
        return f"Iniciando a playlist {nome}."

    if start_uri(playlist["uri"]):
        return f"Iniciando a playlist {nome}."
    return f"Encontrei a playlist {nome}, mas a reprodução não iniciou."


def _queue(query):
    resultados = spotify.search(query, kind="track", limit=1)
    if not resultados:
        return f"Não encontrei {query} para adicionar à fila, senhor."

    faixa = resultados[0]
    ensure_device_ready()
    if spotify.queue(faixa["uri"]):
        return f"{_format_search_result(faixa)} entrou na fila."
    return "Não consegui adicionar à fila, senhor."


def _resume():
    ensure_device_ready()
    return "Retomando." if spotify.play() else "Não há nada para retomar, senhor."


def _transport(action):
    """Executa as ações que não dependem de busca."""
    if action == "PAUSE":
        return "Pausado." if spotify.pause() else "Não há reprodução ativa, senhor."
    if action == "NEXT":
        return "Próxima." if spotify.next_track() else "Não consegui pular a faixa, senhor."
    if action == "PREVIOUS":
        return "Voltando." if spotify.previous_track() else "Não consegui voltar a faixa, senhor."
    if action == "NOW_PLAYING":
        return _format_now_playing(spotify.now_playing())
    if action == "RESUME":
        return _resume()
    return None


# ============================================================================
# CONTRATO DA SKILL
# ============================================================================
def execute(entity, command=""):
    texto = command or entity or ""

    if not spotify.is_configured():
        return ("Senhor, falta cadastrar o SPOTIFY_CLIENT_ID no arquivo .env "
                "antes que eu possa comandar a sua música.")

    if not spotify.is_authorized():
        start_authorization()
        return ("Abri o navegador, senhor. Autorize meu acesso ao Spotify e "
                "repita o comando.")

    try:
        # Estágio 1: verbos de transporte, sem custo de inferência.
        action = _parse_fast(texto)
        query = None

        # Estágio 2: só quem sobrou precisa do curador musical.
        if action is None:
            decisao = _ask_ollama_spotify_expert(texto)
            if not decisao:
                return "Falha na triangulação de dados. Não consigo processar isso agora."
            action = decisao.get("action")
            query = decisao.get("query")

        log.info(f"🎵 [SPOTIFY] Ação: {action} | Query: {query!r}")

        if action in ("PAUSE", "NEXT", "PREVIOUS", "NOW_PLAYING", "RESUME"):
            return _transport(action)

        if action == "PLAY_TRACK":
            return _play_track(query) if query else _resume()
        if action == "PLAY_PLAYLIST":
            return _play_playlist(query) if query else _resume()
        if action == "QUEUE":
            return _queue(query) if query else "O que devo adicionar à fila, senhor?"

        return "Esse comando musical ainda não consta nos meus protocolos, senhor."

    except Exception as e:
        log.error(f"Erro na Skill do Spotify: {e}")
        return "Detectada instabilidade no subsistema de música."
