"""Cofre de credenciais das integrações (refresh tokens OAuth).

Usa o Cofre de Credenciais do Windows via `keyring` (serviço "JARVIS"): o token
não fica em arquivo de texto nem no .env. Sem `keyring` (ou com backend que
falha), cai num JSON em `settings.DIR_DATABASE` — melhor que perder a sessão.

Valores são dicts serializados em JSON. Nada daqui vai para o log além do nome.
"""
import json
import threading

from core.config import settings
from core.logger import log

SERVICE = "JARVIS"
_FALLBACK_FILE = "integrations_secrets.json"
_lock = threading.Lock()


def _keyring():
    try:
        import keyring
        return keyring
    except Exception:
        return None


def _fallback_path():
    return settings.DIR_DATABASE / _FALLBACK_FILE


def _read_fallback():
    path = _fallback_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as e:
        log.warning(f"Cofre (arquivo) ilegível: {e}")
        return {}


def _write_fallback(data):
    path = _fallback_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def get(name):
    """Dict guardado em `name`, ou None."""
    kr = _keyring()
    if kr is not None:
        try:
            raw = kr.get_password(SERVICE, name)
            if raw:
                return json.loads(raw)
        except Exception as e:
            log.warning(f"Cofre do Windows indisponível para '{name}': {e}")
    with _lock:
        value = _read_fallback().get(name)
    return value if isinstance(value, dict) else None


def set(name, value):  # noqa: A001 — API do cofre (get/set/delete)
    """Grava `value` (dict). Retorna True se gravou em algum lugar."""
    raw = json.dumps(value)
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE, name, raw)
            return True
        except Exception as e:
            log.warning(f"Cofre do Windows recusou '{name}' ({e}); usando arquivo local.")
    try:
        with _lock:
            data = _read_fallback()
            data[name] = value
            _write_fallback(data)
        return True
    except OSError as e:
        log.error(f"Não consegui guardar a credencial '{name}': {e}")
        return False


def delete(name):
    """Apaga `name` dos dois lugares (ignora se não existir)."""
    kr = _keyring()
    if kr is not None:
        try:
            kr.delete_password(SERVICE, name)
        except Exception:
            pass
    try:
        with _lock:
            data = _read_fallback()
            if data.pop(name, None) is not None:
                _write_fallback(data)
    except OSError as e:
        log.warning(f"Não consegui apagar '{name}' do arquivo local: {e}")
