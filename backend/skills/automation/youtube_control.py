# ⚠️ ACESSO SENSÍVEL: foca a janela do navegador, troca para a aba do YouTube e manda
# teclas do player (pyautogui); lê títulos de abas pela UI Automation. Ver SECURITY.md.
"""Skill YOUTUBE_CONTROL — "toca lo-fi no YouTube", "pausa o vídeo", "tela cheia".

- Tocar: `core.youtube.find_video` (busca do DuckDuckGo) → abre o 1º vídeo direto;
  sem vídeo, a página de resultados.
- Player: teclas oficiais do YouTube (k, j/l, f, t, i, c, m, Shift+N/P, >/<, 0–9)
  na aba do YouTube — achada pelo título, trocando de aba se preciso. Em ações
  rápidas (pausar, pular 10 s, legenda…) o foco volta para onde o usuário estava.
- Roteamento como o do Spotify: regex primeiro, LLM só para a frase que sobrar.
"""
import json
import re
import unicodedata

from core import browser, log, youtube
from core.config import settings
from core.prompts import load_prompt

INTENT = "YOUTUBE_CONTROL"
PROMPT_TEXT = load_prompt("skills/youtube_control.md")
# Pré-filtro do classificador (sem acento; `*` = prefixo). Ver skills/README.md
# Verbos do player entram também: "avança 30 segundos" não cita o vídeo, e sem
# candidato o classificador recebe todas as skills (estoura o contexto do Ollama).
KEYWORDS = ("youtube", "video", "videos", "legenda*", "tela cheia", "velocidade", "cinema", "miniplayer",
            "avanc*", "adiant*", "retroced*", "segundos")

DECISION_PROMPT = load_prompt("skills/youtube_decision.md")

# Ação → (teclas, resposta). Teclas oficiais do player do YouTube.
KEYS = {
    "TOGGLE": (("k",), "Feito."),
    "PAUSE": (("k",), "Vídeo pausado."),
    "RESUME": (("k",), "Retomando o vídeo."),
    "FULLSCREEN": (("f",), "Tela cheia alternada."),
    "THEATER": (("t",), "Modo cinema alternado."),
    "MINIPLAYER": (("i",), "Miniplayer alternado."),
    "CAPTIONS": (("c",), "Legendas alternadas."),
    "MUTE": (("m",), "Som do vídeo alternado."),
    "NEXT": (("shift", "n"), "Próximo vídeo."),
    "PREVIOUS": (("shift", "p"), "Vídeo anterior."),
    "RESTART": (("0",), "Do começo."),
    "SPEED_UP": ((">",), "Mais rápido."),
    "SPEED_DOWN": (("<",), "Mais devagar."),
    "VOLUME_UP": (("up",), "Volume do vídeo aumentado."),
    "VOLUME_DOWN": (("down",), "Volume do vídeo reduzido."),
}
PLAYER_ACTIONS = set(KEYS) | {"FORWARD", "BACK", "SEEK_PERCENT", "SPEED_SET"}
ACTIONS = PLAYER_ACTIONS | {"PLAY", "SEARCH", "OPEN_HOME", "NOW_PLAYING"}
# Ações rápidas: depois das teclas o foco volta para a janela anterior
RESTORE_FOCUS = {"TOGGLE", "PAUSE", "RESUME", "CAPTIONS", "MUTE", "NEXT", "PREVIOUS", "RESTART", "SPEED_UP",
                 "SPEED_DOWN", "VOLUME_UP", "VOLUME_DOWN", "FORWARD", "BACK", "SEEK_PERCENT", "SPEED_SET"}
VOLUME_STEPS = 4         # 5% por toque de ↑/↓
SPEED_MIN, SPEED_MAX, SPEED_STEP = 0.25, 2.0, 0.25
MAX_SEEK_PRESSES = 60    # 10 min de "l"

NO_YOUTUBE = "Não há YouTube aberto em nenhum navegador, Senhor. Peça para eu tocar algo."
NO_FOCUS = "O navegador não aceitou o foco, Senhor. Clique nele uma vez e repita."

_VIDEO_WORDS = {"o video", "video", "esse video", "este video", "ele", "isso", "o youtube", "youtube", ""}
_UNITS = r"(segundos?|seg|s|minutos?|min)"

# (ação, regex) — a 1ª que casar vence. Grupo "q" = busca; "n"/"u" = quantidade/unidade.
PATTERNS = (
    ("SEARCH", re.compile(r"\b(?:pesquis\w*|busc\w*|procur\w*)\s+(?:por\s+)?(?P<q>.+?)\s+(?:no|do|pelo) youtube$")),
    ("SEARCH", re.compile(r"\b(?:no|pelo) youtube\s+(?:pesquis\w*|busc\w*|procur\w*)\s+(?:por\s+)?(?P<q>.+)$")),
    ("PLAY", re.compile(r"\b(?:toc\w*|toque|coloc\w*|bot\w*|poe|ponha|abr\w*|assist\w*|mostr\w*|reproduz\w*)\s+"
                        r"(?P<q>.+?)\s+(?:no|do|pelo|via) youtube$")),
    ("PLAY", re.compile(r"\b(?:toc\w*|toque|coloc\w*|poe|ponha|assist\w*|mostr\w*|reproduz\w*)\s+(?:o |um |uma )?"
                        r"videos?\s+(?:de |do |da |dos |das |sobre |com )(?P<q>.+)$")),
    ("OPEN_HOME", re.compile(r"\babr\w* (?:o )?youtube$")),
    ("NOW_PLAYING", re.compile(r"\b(?:que|qual) (?:e o )?video (?:e esse|e este|esta (?:passando|tocando))\b|"
                               r"\bo que (?:esta|ta) (?:passando|tocando) no youtube\b|\bnome (?:desse|deste) video\b")),
    ("NEXT", re.compile(r"\bproximo video\b|\bpula (?:esse|este|o) video\b")),
    ("PREVIOUS", re.compile(r"\bvideo anterior\b")),
    ("FULLSCREEN", re.compile(r"\btela cheia\b")),
    ("THEATER", re.compile(r"\bmodo (?:cinema|teatro)\b")),
    ("MINIPLAYER", re.compile(r"\bmini ?player\b")),
    ("CAPTIONS", re.compile(r"\blegenda")),
    ("SPEED_SET", re.compile(r"\bvelocidade (?:de |para |pra |em )?(?P<n>\d+(?:[.,]\d+)?|normal)\b")),
    ("SPEED_UP", re.compile(r"\b(?:acelera\w*|mais rapido|aumenta\w* a velocidade)\b")),
    ("SPEED_DOWN", re.compile(r"\b(?:mais devagar|mais lento|desacelera\w*|diminu\w* a velocidade)\b")),
    ("RESTART", re.compile(r"\b(?:do (?:comeco|inicio)|reinici\w* (?:o )?video|volta\w* (?:pro|para o) (?:comeco|inicio))\b")),
    ("SEEK_PERCENT", re.compile(r"\b(?:metade|meio) do video\b|\b(?P<n>\d{1,2}) ?(?:%|por ?cento)")),
    ("FORWARD", re.compile(r"\b(?:avanc\w*|adiant\w*|pul\w*)\s+(?:mais\s+)?(?P<n>\d+)\s*" + _UNITS + r"\b")),
    ("BACK", re.compile(r"\b(?:volt\w*|retroced\w*|recu\w*)\s+(?:mais\s+)?(?P<n>\d+)\s*" + _UNITS + r"\b")),
    ("FORWARD", re.compile(r"\b(?:avanc\w*|adiant\w*) (?:um pouco|o video)\b")),
    ("BACK", re.compile(r"\b(?:volt\w*|retroced\w*) (?:um pouco|o video)\b")),
    ("MUTE", re.compile(r"\b(?:muta\w*|desmuta\w*|mudo|silencia\w*|tira o som|volta o som)\b")),
    ("VOLUME_UP", re.compile(r"\b(?:aument\w*|sob\w*) o volume\b")),
    ("VOLUME_DOWN", re.compile(r"\b(?:diminu\w*|abaix\w*|baix\w*) o volume\b")),
    ("PAUSE", re.compile(r"\b(?:paus\w*|pause|para o video|parar o video)\b")),
    ("RESUME", re.compile(r"\b(?:continu\w*|retom\w*|despaus\w*|da (?:o )?play|dar play|solta o video|play)\b|"
                          r"\b(?:toc\w*|toque) (?:o |esse |este )?video$")),
)


# ------------------------------------------------------------ lógica pura
def normalize(text):
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[?!;:]", " ", text)
    text = re.sub(r"(?<!\d)[.,](?!\d)", " ", text)  # mantém "1.5" / "1,5"
    text = re.sub(r"^\s*jarvis\b", " ", text)
    return " ".join(text.split())


def clean_query(q):
    q = re.sub(r"^(?:o |a |os |as |um |uma )", "", (q or "").strip())
    q = re.sub(r"^videos? (?:de |do |da |sobre )?", "", q)
    return q.strip()


def seconds(n, unit):
    n = int(n)
    return n * 60 if unit.startswith("min") else n


def parse(command):
    """(ação, valor) por regex; None se precisa do LLM. Valor: busca, segundos,
    dígito do % ou velocidade, conforme a ação."""
    text = normalize(command)
    if not text:
        return None
    for action, rx in PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        g = m.groupdict()
        if action in ("PLAY", "SEARCH"):
            q = clean_query(g.get("q"))
            if q in _VIDEO_WORDS:
                return ("RESUME", None) if action == "PLAY" else ("OPEN_HOME", None)
            return action, q
        if action in ("FORWARD", "BACK"):
            return action, seconds(g["n"], m.group(m.lastindex)) if g.get("n") else 10
        if action == "SEEK_PERCENT":
            return action, min(9, int(g["n"]) // 10) if g.get("n") else 5
        if action == "SPEED_SET":
            raw = g["n"]
            return action, 1.0 if raw == "normal" else float(raw.replace(",", "."))
        return action, None
    return None


def seek_keys(secs):
    """Segundos → (tecla, toques): múltiplos de 10 usam j/l; senão ←/→ (5 s)."""
    secs = abs(int(secs or 10))
    if secs % 10 == 0:
        return "l", min(secs // 10, MAX_SEEK_PRESSES)
    return "right", min(max(1, round(secs / 5)), MAX_SEEK_PRESSES * 2)


def speed_presses(target):
    """Velocidade-alvo → toques de '>' partindo do mínimo (0,25×), já que o
    YouTube não informa a velocidade atual: desce tudo e sobe o necessário."""
    target = min(SPEED_MAX, max(SPEED_MIN, float(target)))
    return round((target - SPEED_MIN) / SPEED_STEP)


def _ask_llm(command):
    from core.llm import query_ollama
    raw = query_ollama([{"role": "system", "content": DECISION_PROMPT}, {"role": "user", "content": command}],
                       format="json", temperature=0.1, timeout=settings.TIMEOUT_LLM)
    try:
        data = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("action") not in ACTIONS:
        return None
    action, value = data["action"], data.get("value")
    if action in ("PLAY", "SEARCH"):
        q = clean_query(str(value or ""))
        return (action, q) if q else ("RESUME", None)
    if action in ("FORWARD", "BACK"):
        try:
            return action, int(value or 10)
        except (TypeError, ValueError):
            return action, 10
    return action, None


# ------------------------------------------------------------ navegador
def locate():
    """(janela, aba | None) do YouTube: janela cuja aba ativa já é o YouTube
    (aba None) ou janela + aba de fundo; (None, None) se não houver."""
    wins = browser.find_browser_windows()
    for win in wins:
        if youtube.is_youtube_title(win.get("title")):
            return win, None
    for win in wins:
        tabs = [t for t in browser.list_tabs(win) if youtube.is_youtube_title(t["title"])]
        if tabs:
            return win, next((t for t in tabs if t["selected"]), tabs[0])
    return None, None


def _now_playing():
    win, tab = locate()
    if not win:
        return NO_YOUTUBE
    title = youtube.clean_title(tab["title"] if tab else win["title"])
    return f"No YouTube: **{title}**." if title else "O YouTube está aberto, mas sem vídeo, Senhor."


def _player(action, value):
    win, tab = locate()
    if not win:
        return NO_YOUTUBE
    previous = browser.foreground()
    if tab and not tab["selected"] and not browser.select_tab(win, tab["index"]):
        return NO_FOCUS
    if action in KEYS:
        keys, reply = KEYS[action]
        presses = VOLUME_STEPS if action in ("VOLUME_UP", "VOLUME_DOWN") else 1
        ok = browser.send_hotkey(win, *keys, presses=presses)
    elif action in ("FORWARD", "BACK"):
        key, presses = seek_keys(value)
        if action == "BACK":
            key = {"l": "j", "right": "left"}[key]
        ok = browser.send_hotkey(win, key, presses=presses)
        verb = "Avancei" if action == "FORWARD" else "Voltei"
        reply = f"{verb} {abs(int(value or 10))} segundos."
    elif action == "SEEK_PERCENT":
        ok = browser.send_hotkey(win, str(value))
        reply = f"Pulei para {int(value) * 10}% do vídeo."
    else:  # SPEED_SET
        ok = (browser.send_hotkey(win, "<", presses=round((SPEED_MAX - SPEED_MIN) / SPEED_STEP))
              and browser.send_hotkey(win, ">", presses=speed_presses(value)))
        reply = f"Velocidade em {min(SPEED_MAX, max(SPEED_MIN, float(value))):g}×."
    if not ok:
        return NO_FOCUS
    if action in RESTORE_FOCUS and previous and previous != win["hwnd"]:
        browser.restore_focus(previous)
    return reply


def run(action, value):
    if action == "PLAY":
        url, title = youtube.find_video(value)
        if not browser.open_url(url):
            return "O navegador recusou abrir o YouTube, Senhor."
        if title:
            return f"Tocando **{title}** no YouTube."
        return f"Não achei um vídeo exato; abri os resultados de '{value}'."
    if action == "SEARCH":
        ok = browser.open_url(youtube.results_url(value))
        return f"Resultados de '{value}' no YouTube." if ok else "O navegador recusou abrir o YouTube, Senhor."
    if action == "OPEN_HOME":
        return "YouTube aberto." if browser.open_url(youtube.HOME_URL) else "O navegador recusou abrir o YouTube, Senhor."
    if action == "NOW_PLAYING":
        return _now_playing()
    if action in PLAYER_ACTIONS:
        return _player(action, value)
    return "Esse comando de YouTube não consta nos meus protocolos, Senhor."


def execute(entity, command=""):
    text = command or entity or ""
    decision = parse(text) or _ask_llm(text)
    if not decision:
        return "Não entendi o que fazer no YouTube, Senhor."
    action, value = decision
    log.info(f"▶️ [YOUTUBE] {action} | valor={value!r}")
    try:
        return run(action, value)
    except Exception as e:
        log.error(f"[YOUTUBE] Falha: {e}")
        return "O YouTube não colaborou dessa vez, Senhor."
