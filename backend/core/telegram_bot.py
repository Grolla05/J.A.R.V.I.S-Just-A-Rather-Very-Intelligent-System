"""Telegram Bot API por long polling (só `requests`, sem lib nova).

O PC busca as mensagens (`getUpdates?timeout=30`) — nenhuma porta aberta, nenhum
webhook. Só chats privados. O token nunca vai para o log.
"""
import time

from core.logger import log

API = "https://api.telegram.org/bot{token}/{method}"
POLL_TIMEOUT = 30
BACKOFF_MAX_S = 60


def parse_update(update):
    """(chat_id, user_id, texto) de uma mensagem privada de texto; None para o resto."""
    msg = update.get("message") or {}
    chat, sender, text = msg.get("chat") or {}, msg.get("from") or {}, msg.get("text")
    if chat.get("type") != "private" or not text or sender.get("is_bot"):
        return None
    return chat.get("id"), str(sender.get("id")), text


class TelegramBridge:
    def __init__(self, token, handler, http=None, sleep=time.sleep):
        self.token, self.handler, self.sleep = token, handler, sleep
        self._http = http
        self.offset = 0
        self.failed = False   # última rodada deu erro de rede/API (o run espera antes de tentar)

    @property
    def http(self):
        if self._http is None:
            import requests
            self._http = requests
        return self._http

    def _url(self, method):
        return API.format(token=self.token, method=method)

    def _safe(self, error):
        return str(error).replace(self.token, "***") if self.token else str(error)

    def send(self, chat_id, text):
        try:
            self.http.post(self._url("sendMessage"), json={"chat_id": chat_id, "text": text}, timeout=15)
        except Exception as e:
            log.warning(f"[TELEGRAM] Envio falhou: {self._safe(e)}")

    def typing(self, chat_id):
        try:
            self.http.post(self._url("sendChatAction"), json={"chat_id": chat_id, "action": "typing"}, timeout=10)
        except Exception:
            pass

    def poll_once(self):
        """Uma rodada de getUpdates. Devolve quantas mensagens foram tratadas."""
        self.failed = True
        try:
            r = self.http.get(self._url("getUpdates"), params={"timeout": POLL_TIMEOUT, "offset": self.offset},
                              timeout=POLL_TIMEOUT + 10)
            data = r.json()
        except Exception as e:
            log.warning(f"[TELEGRAM] Polling falhou: {self._safe(e)}")
            return 0
        if not data.get("ok"):
            log.warning(f"[TELEGRAM] API recusou: {self._safe(data.get('description', ''))}")
            return 0
        self.failed = False
        handled = 0
        for update in data.get("result") or []:
            self.offset = max(self.offset, int(update.get("update_id", 0)) + 1)
            parsed = parse_update(update)
            if not parsed:
                continue
            chat_id, user_id, text = parsed
            self.typing(chat_id)
            try:
                replies = self.handler("telegram", user_id, text)
            except Exception as e:
                log.error(f"[TELEGRAM] Tratamento falhou: {e}")
                replies = ["Algo deu errado do meu lado, Senhor."]
            for part in replies or []:
                self.send(chat_id, part)
            handled += 1
        return handled

    def run(self, stop_event):
        log.info("[TELEGRAM] Ponte no ar (long polling).")
        backoff = 0
        while not stop_event.is_set():
            self.poll_once()   # bloqueia até POLL_TIMEOUT esperando mensagem
            backoff = min(max(backoff * 2, 2), BACKOFF_MAX_S) if self.failed else 0
            if backoff and stop_event.wait(backoff):
                break
