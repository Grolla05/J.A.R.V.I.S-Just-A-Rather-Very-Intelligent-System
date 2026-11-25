"""Web Watch — vigia páginas, preços e repositórios e avisa quando algo muda.

- Criar/listar/remover: `/vigiar` na TUI e a skill WEB_WATCH (texto → `create_from_text`)
- Estado na tabela `web_watches` (último valor, hash e hora da checagem)
- `collect(now)` é chamado pelo tick da TUI: checa só os itens vencidos
  (`WEBWATCH_INTERVAL_MIN`) e devolve os avisos `[{'text', 'urgent'}]`. Nunca levanta.

Avisos: página mudou / preço caiu / release ou commit novo. Preço que chega no
alvo pedido é `urgent` (passa pelo Não Perturbe como os lembretes pedidos).
"""
import json
import re
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from core import webwatch
from core.config import settings
from core.database import db
from core.logger import log
from core.webwatch import PAGE, PRICE, REPO

ICONS = {PAGE: "📄", PRICE: "💲", REPO: "📦"}
LABEL_MAX = 60

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
_REPO_TOKEN_RE = re.compile(r"(?<![\w./:-])([A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+)(?![\w/])")
_REPO_NAME_RE = re.compile(r"\b(?:repo|reposit[oó]rio)\s+(?:do\s+|da\s+|de\s+|o\s+)?([A-Za-z0-9_.-]+)", re.I)
_PRICE_WORDS_RE = re.compile(r"\b(pre[cç]os?|valor|barat\w*|abaixo|menos de|custa\w*|promo\w*)\b|R\$", re.I)
_TARGET_RE = re.compile(
    r"(?:abaixo de|menos de|menor que|baixar de|baixar para|cair para|cair de|at[eé]|alvo|chegar a|chegar em|por)\s*(?:R\$\s*)?(\d[\d.,]*)", re.I)


# ------------------------------------------------------------------ pedido
def parse_request(text, url_fallback=None):
    """Texto do pedido → {'kind', 'target', 'target_price'} ou None (sem alvo).
    `url_fallback()` (ex.: URL da aba aberta) entra quando o texto não traz endereço."""
    text = text or ""
    url = next((u.rstrip(".,;:!?)]}") for u in _URL_RE.findall(text)), None)
    repo = webwatch.github_repo(url) if url else None
    if not url:
        token = _REPO_TOKEN_RE.search(text)
        name = _REPO_NAME_RE.search(text)
        repo = token.group(1) if token else (name.group(1) if name else None)
    if repo:
        return {"kind": REPO, "target": repo, "target_price": None}
    if not url and url_fallback:
        try:
            url = url_fallback()
        except Exception as e:
            log.debug(f"[WEBWATCH] Sem URL da aba: {e}")
            url = None
        repo = webwatch.github_repo(url) if url else None
        if repo:
            return {"kind": REPO, "target": repo, "target_price": None}
    if not url:
        return None
    rest = text.replace(url, " ")
    target = _TARGET_RE.search(rest)
    target_price = webwatch.parse_number(target.group(1)) if target else None
    kind = PRICE if (target_price or _PRICE_WORDS_RE.search(rest)) else PAGE
    return {"kind": kind, "target": url, "target_price": target_price}


def short_label(url):
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    label = host + (parts.path.rstrip("/") or "")
    return label if len(label) <= LABEL_MAX else label[:LABEL_MAX - 1] + "…"


# ------------------------------------------------------------------ banco
def _iso(when):
    return when.replace(microsecond=0).isoformat()


def items():
    """Itens vigiados na ordem de criação: [{'id','kind','target','label','target_price',
    'last_value','last_hash','last_checked'}]."""
    try:
        with db.connection() as conn:
            rows = conn.execute("SELECT id, kind, target, label, target_price, last_value, last_hash, "
                                "last_checked FROM web_watches ORDER BY id").fetchall()
    except sqlite3.Error as e:
        log.error(f"[WEBWATCH] Falha ao ler: {e}")
        return []
    keys = ("id", "kind", "target", "label", "target_price", "last_value", "last_hash", "last_checked")
    return [dict(zip(keys, row)) for row in rows]


def add(kind, target, label, target_price, value, digest, now):
    """Grava o item já com a 1ª leitura. None se falhar ou se já existir."""
    try:
        with db.connection() as conn:
            return conn.execute(
                "INSERT INTO web_watches (kind, target, label, target_price, last_value, last_hash, last_checked) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (kind, target, label, target_price, value, digest, _iso(now))).lastrowid
    except sqlite3.IntegrityError:
        return None
    except sqlite3.Error as e:
        log.error(f"[WEBWATCH] Falha ao gravar: {e}")
        return None


def save_state(item_id, value, digest, now):
    try:
        with db.connection() as conn:
            conn.execute("UPDATE web_watches SET last_value = ?, last_hash = ?, last_checked = ? WHERE id = ?",
                         (value, digest, _iso(now), item_id))
    except sqlite3.Error as e:
        log.error(f"[WEBWATCH] Falha ao atualizar: {e}")


def touch(item_id, now):
    try:
        with db.connection() as conn:
            conn.execute("UPDATE web_watches SET last_checked = ? WHERE id = ?", (_iso(now), item_id))
    except sqlite3.Error as e:
        log.error(f"[WEBWATCH] Falha ao marcar checagem: {e}")


def remove(index):
    """Remove o n-ésimo item (número da lista). Devolve o item removido ou None."""
    current = items()
    if not 1 <= index <= len(current):
        return None
    item = current[index - 1]
    try:
        with db.connection() as conn:
            conn.execute("DELETE FROM web_watches WHERE id = ?", (item["id"],))
    except sqlite3.Error as e:
        log.error(f"[WEBWATCH] Falha ao remover: {e}")
        return None
    return item


# ------------------------------------------------------------------ checagem
def _default_checkers():
    return {
        PAGE: webwatch.check_page,
        PRICE: lambda url: webwatch.check_price(url, ask_llm=webwatch.ask_price_llm),
        REPO: webwatch.check_repo,
    }


def _repo_state(result):
    release = (result.get("release") or {}).get("tag")
    commit = (result.get("commit") or {}).get("sha")
    return json.dumps({"release": release, "commit": commit})


def _load_json(raw):
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def evaluate(item, result):
    """Compara a leitura nova com a guardada. → (aviso|None, urgent, value, digest).
    Puro: não grava nada."""
    kind, label = item["kind"], item["label"]
    if kind == PAGE:
        if result["hash"] == item.get("last_hash"):
            return None, False, item.get("last_value"), item.get("last_hash")
        added = webwatch.new_lines(item.get("last_value"), result["text"])
        detail = "".join(f"\n- {line[:160]}" for line in added) if added else ""
        text = f"A página **{label}** mudou, Senhor. {item['target']}{detail}"
        return text, False, result["text"], result["hash"]

    if kind == PRICE:
        new = result["price"]
        old = webwatch.parse_number(item.get("last_value"))
        alvo = item.get("target_price")
        value = repr(new)
        if old is None or new >= old:
            return None, False, value, None
        hit = bool(alvo and new <= alvo)
        text = (f"O preço em **{label}** caiu de {webwatch.format_brl(old)} para "
                f"{webwatch.format_brl(new)}, Senhor.")
        if hit:
            text += f" Chegou no seu alvo de {webwatch.format_brl(alvo)}."
        return text + f" {item['target']}", hit, value, None

    # REPO
    old = _load_json(item.get("last_value"))
    value = _repo_state(result)
    release, commit = result.get("release") or {}, result.get("commit") or {}
    if release.get("tag") and release["tag"] != old.get("release"):
        return (f"Release nova em **{result.get('repo', label)}**: {release.get('name') or release['tag']} "
                f"— {release.get('url', '')}", False, value, None)
    if commit.get("sha") and commit["sha"] != old.get("commit"):
        return (f"Commit novo em **{result.get('repo', label)}** (`{result.get('branch', '')}`): "
                f"[`{commit['sha'][:7]}`]({commit.get('url', '')}) {commit.get('title', '')}", False, value, None)
    return None, False, value, None


def _due(item, now, interval_min):
    if not item.get("last_checked"):
        return True
    try:
        last = datetime.fromisoformat(item["last_checked"])
    except ValueError:
        return True
    return now - last >= timedelta(minutes=interval_min)


def collect(now=None, checkers=None, interval_min=None):
    """Checa os itens vencidos e devolve os avisos: [{'text', 'urgent', 'kind'}]. Nunca levanta."""
    now = now or datetime.now()
    checkers = checkers or _default_checkers()
    interval_min = settings.WEBWATCH_INTERVAL_MIN if interval_min is None else interval_min
    out = []
    try:
        for item in items():
            if not _due(item, now, interval_min):
                continue
            check = checkers.get(item["kind"])
            result = check(item["target"]) if check else {"error": "tipo desconhecido"}
            if result.get("error"):
                log.debug(f"[WEBWATCH] {item['label']}: {result['error']}")
                touch(item["id"], now)
                continue
            text, urgent, value, digest = evaluate(item, result)
            save_state(item["id"], value, digest, now)
            if text:
                out.append({"text": text, "urgent": urgent, "kind": "webwatch"})
    except Exception as e:
        log.error(f"[WEBWATCH] Falha na checagem: {e}")
    return out


# ------------------------------------------------------------------ falas
def create_from_text(text, now=None, url_fallback=None, checkers=None):
    """`/vigiar <url|dono/repo> [preço abaixo de N]` e skill WEB_WATCH. Devolve a fala."""
    now = now or datetime.now()
    req = parse_request(text, url_fallback)
    if req is None:
        return ("O que vigiar, Senhor? Mande o link (`/vigiar https://… preço abaixo de 300`) "
                "ou o repositório (`/vigiar dono/repo`).")
    if len(items()) >= settings.WEBWATCH_MAX:
        return f"Já vigio {settings.WEBWATCH_MAX} itens, Senhor — o limite. `/vigiar rm <n>` libera espaço."
    checkers = checkers or _default_checkers()
    kind, target, alvo = req["kind"], req["target"], req["target_price"]
    result = checkers[kind](target)
    if result.get("error"):
        return f"Não consegui ler {target}, Senhor: {result['error']}."

    if kind == PAGE:
        label, value, digest = short_label(target), result["text"], result["hash"]
        reply = f"Vigiando **{label}**. Aviso quando o conteúdo mudar."
    elif kind == PRICE:
        label, value, digest = short_label(target), repr(result["price"]), None
        reply = f"Vigiando o preço em **{label}**: hoje {webwatch.format_brl(result['price'])}."
        reply += (f" Aviso com prioridade quando chegar a {webwatch.format_brl(alvo)}." if alvo
                  else " Aviso sempre que baixar.")
    else:
        target = result.get("repo") or target
        label, value, digest = target, _repo_state(result), None
        release = (result.get("release") or {}).get("tag")
        reply = (f"Vigiando **{target}**"
                 + (f" (release atual {release})" if release else "")
                 + ". Aviso em release ou commit novo.")
    if add(kind, target, label, alvo, value, digest, now) is None:
        return f"Já estou vigiando {label}, Senhor. `/vigiar` lista tudo."
    return reply


def _describe(item):
    icon = ICONS.get(item["kind"], "•")
    if item["kind"] == PRICE:
        price = webwatch.parse_number(item.get("last_value"))
        extra = webwatch.format_brl(price) if price else "sem leitura"
        if item.get("target_price"):
            extra += f" (alvo {webwatch.format_brl(item['target_price'])})"
    elif item["kind"] == REPO:
        state = _load_json(item.get("last_value"))
        extra = f"release {state['release']}" if state.get("release") else "commits"
    else:
        extra = "conteúdo"
    return f"{icon} **{item['label']}** — {extra}"


def list_text():
    current = items()
    if not current:
        return ("Nada sob vigia, Senhor. `/vigiar <link>` vigia uma página, `/vigiar <link> preço abaixo de 300` "
                "um preço e `/vigiar dono/repo` um repositório.")
    lines = [f"{i}. {_describe(item)}" for i, item in enumerate(current, 1)]
    return ("**Sob vigia**\n\n" + "\n".join(lines)
            + f"\n\nChecagem a cada {settings.WEBWATCH_INTERVAL_MIN} min com a TUI aberta · `/vigiar rm <n>` remove.")


def remove_text(index):
    item = remove(index)
    if not item:
        return f"Não há item {index} sob vigia, Senhor. `/vigiar` lista os números."
    return f"Parei de vigiar {item['label']}."
