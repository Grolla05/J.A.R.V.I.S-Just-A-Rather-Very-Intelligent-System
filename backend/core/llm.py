import os
import threading
import time

from .config import settings
from .logger import log

os.environ["OLLAMA_HOST"] = settings.OLLAMA_HOST


class LLMError(Exception):
    """O Ollama falhou durante o stream. Quem consome mostra o erro, mas não o
    grava como resposta do assistente (voltaria ao modelo no histórico)."""


_clients = {}  # timeout -> ollama.Client (um por timeout, reaproveitado entre chamadas)
_clients_lock = threading.Lock()


def _get_client(timeout=None):
    """Client Ollama com host normalizado, reaproveitado por timeout (o Client
    guarda o pool de conexões HTTP). Centraliza query_ollama / stream / warm-up."""
    timeout = timeout or 120
    with _clients_lock:
        client = _clients.get(timeout)
        if client is None:
            from ollama import Client
            host = settings.OLLAMA_HOST
            if not host.startswith("http"):
                host = f"http://{host}"
            client = _clients[timeout] = Client(host=host, timeout=timeout)
        return client


# Fica True após o Ollama recusar num_gpu (VRAM insuficiente): a partir daí a opção
# some de TODAS as chamadas, evitando falha repetida e reload por opções divergentes.
_gpu_option_disabled = False


def _build_options(temperature):
    """Monta `options` do Ollama: temperature + num_ctx/num_gpu quando configurados."""
    options = {'temperature': temperature}
    if settings.OLLAMA_NUM_CTX:
        options['num_ctx'] = settings.OLLAMA_NUM_CTX
    if settings.OLLAMA_NUM_GPU is not None and not _gpu_option_disabled:
        options['num_gpu'] = settings.OLLAMA_NUM_GPU
    return options


def _disable_gpu_option(error):
    global _gpu_option_disabled
    _gpu_option_disabled = True
    log.warning(
        f"Ollama recusou num_gpu={settings.OLLAMA_NUM_GPU} ({error}). "
        "Opção desativada; seguindo com o padrão do Ollama. "
        "Reduza OLLAMA_NUM_CTX ou libere VRAM para tentar de novo."
    )


def _gpu_option_active():
    return settings.OLLAMA_NUM_GPU is not None and not _gpu_option_disabled


def _chat(client, temperature, **kwargs):
    """client.chat com fallback: se num_gpu estiver ativo e a chamada falhar,
    desativa a opção e repete uma vez sem ela."""
    try:
        return client.chat(options=_build_options(temperature), **kwargs)
    except Exception as e:
        if not _gpu_option_active():
            raise
        _disable_gpu_option(e)
        return client.chat(options=_build_options(temperature), **kwargs)


def query_ollama(messages, format=None, temperature=0.7, timeout=None, model=None, keep_alive=None):
    """Centraliza chamadas ao Ollama para tratamento de erro e config.

    timeout: segundos antes de desistir. None = 120s (default robusto).
    Classificação/extração devem passar um timeout curto (settings.TIMEOUT_API).
    keep_alive mantém o modelo residente na VRAM (settings.OLLAMA_KEEP_ALIVE).
    model/keep_alive: override explícito (ex: modelo de visão + keep_alive curto).
    """
    try:
        client = _get_client(timeout)
        response = _chat(
            client,
            temperature,
            model=model or settings.OLLAMA_MODEL,
            messages=messages,
            format=format,
            keep_alive=keep_alive or settings.OLLAMA_KEEP_ALIVE
        )
        return response['message']['content']
    except Exception as e:
        log.error(f"Erro na comunicação com Ollama: {e}")
        return None


def query_ollama_stream(messages, temperature=0.7, timeout=None, model=None, keep_alive=None):
    """Centraliza chamadas streaming ao Ollama.
    model/keep_alive: override explícito (ex: modelo de visão + keep_alive curto).
    Falha (antes ou no meio do stream) levanta `LLMError` — nunca vira texto."""
    try:
        client = _get_client(timeout)
        # O request só sai na 1ª iteração do stream: erro de VRAM aparece lá. Se nada
        # foi emitido ainda e num_gpu está ativo, desativa a opção e repete uma vez.
        for attempt in range(2):
            emitted = False
            try:
                response = client.chat(
                    model=model or settings.OLLAMA_MODEL,
                    messages=messages,
                    options=_build_options(temperature),
                    keep_alive=keep_alive or settings.OLLAMA_KEEP_ALIVE,
                    stream=True
                )
                for chunk in response:
                    emitted = True
                    yield chunk['message']['content']
                return
            except Exception as e:
                if attempt == 0 and not emitted and _gpu_option_active():
                    _disable_gpu_option(e)
                    continue
                raise
    except Exception as e:
        log.error(f"Erro na comunicação streaming com Ollama: {e}")
        raise LLMError(str(e) or e.__class__.__name__) from e


def warm_up_ollama():
    """Pré-carrega o modelo na VRAM no boot (esconde a lentidão da 1ª inferência).
    Combinado com keep_alive=-1, o modelo permanece residente. Engole exceções —
    se o Ollama ainda não subiu, o sistema segue normal e carrega sob demanda."""
    start = time.time()
    log.info(f"🔥 Aquecendo modelo '{settings.OLLAMA_MODEL}' na VRAM...")
    try:
        client = _get_client(timeout=120)
        _chat(
            client,
            0,
            model=settings.OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': 'ping'}],
            keep_alive=settings.OLLAMA_KEEP_ALIVE
        )
        log.info(f"✅ Modelo aquecido e residente ({time.time() - start:.1f}s)")
    except Exception as e:
        log.warning(f"⚠️ Falha no warm-up do Ollama (carregará sob demanda): {e}")
