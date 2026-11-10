"""Parser dos /comandos da TUI (puro, sem dependência de Textual)."""
import re
from dataclasses import dataclass
from pathlib import Path

# nome -> (uso, descrição). Ordem = ordem da paleta (Ctrl+K).
COMMANDS = {
    "menu":     ("/menu", "paleta de comandos, skills e foco (Ctrl+K)"),
    "new":      ("/new", "nova sessão (Ctrl+N)"),
    "sessions": ("/sessions", "trocar de sessão (Ctrl+O)"),
    "rename":   ("/rename <título>", "renomeia a sessão atual"),
    "pin":      ("/pin", "fixa/desafixa a sessão atual"),
    "regen":    ("/regen", "regenera a última resposta (Ctrl+R)"),
    "edit":     ("/edit", "edita a última mensagem e reenvia (↑ com input vazio)"),
    "attach":   ("/attach <caminho>", "imagem → modelo de visão; áudio → transcreve no input"),
    "detach":   ("/detach", "remove o anexo pendente"),
    "mode":     ("/mode [chat|copilot]", "troca o modo (Shift+Tab)"),
    "voice":    ("/voice", "liga/desliga wake word + voz (Ctrl+T)"),
    "skills":   ("/skills [on|off <skill|categoria>]", "cartuchos das skills (ou alterna direto)"),
    "status":   ("/status", "dashboard do sistema: CPU, RAM, GPU, rede e processos"),
    "log":      ("/log", "log de atividade com filtros e o último turno do Copilot"),
    "vault":    ("/vault [termo]", "memória no Obsidian: árvore, busca e nota no chat"),
    "web":      ("/web <pergunta>", "pesquisa na internet e resume com fontes"),
    "gh":       ("/gh [prs|issues|commit|ci] [dono/repo]", "GitHub: PRs, issues, último commit e CI"),
    "briefing": ("/briefing", "briefing do dia: clima, agenda, trânsito, máquina e GitHub"),
    "rota":     ("/rota [<local> <endereço>]", "cadastra um local fixo (casa, trabalho, faculdade…); sem argumento lista"),
    "clip":     ("/clip [explicar|traduzir|resumir|hist]", "age sobre o que você copiou (monitor no /config)"),
    "focus":    ("/focus [min|stop|skip|status]", "pomodoro 25/5 (liga o Não Perturbe no foco)"),
    "dnd":      ("/dnd [on|off|min]", "Não Perturbe: silencia notificações do Windows e alertas"),
    "silent":   ("/silent [on|off]", "Modo Apresentação: mic fechado, voz muda e alertas guardados"),
    "config":   ("/config", "ajustes de voz, microfone e rotinas (menu estilo RPG)"),
    "clear":    ("/clear", "limpa a tela (não apaga o histórico)"),
    "quit":     ("/quit", "encerra o J.A.R.V.I.S (Esc)"),
}

# /help saiu (a paleta Ctrl+K lista tudo); quem digitar por hábito cai na paleta.
ALIASES = {"q": "quit", "exit": "quit", "help": "menu", "h": "menu", "?": "menu", "s": "sessions", "n": "new"}


@dataclass(frozen=True)
class Command:
    name: str
    arg: str = ""
    known: bool = True


def parse(text):
    """Retorna Command se `text` começa com '/', senão None (é mensagem).
    '//texto' escapa e vira mensagem literal '/texto'."""
    if not text or not text.startswith("/") or text.startswith("//"):
        return None
    body = text[1:].strip()
    if not body:
        return Command("menu")
    name, _, arg = body.partition(" ")
    name = ALIASES.get(name.lower(), name.lower())
    return Command(name, arg.strip(), name in COMMANDS)


_FOCUS_WORDS = {"stop": "stop", "parar": "stop", "para": "stop", "off": "stop",
                "skip": "skip", "pular": "skip", "pula": "skip",
                "status": "status", "?": "status"}
_DND_WORDS = {"on": "dnd_on", "liga": "dnd_on", "off": "dnd_off", "desliga": "dnd_off"}


def parse_focus_arg(arg):
    """/focus <arg> -> (ação, minutos) ou None se inválido.
    ''->start · '50'->start 50 · stop|skip|status."""
    arg = (arg or "").strip().lower()
    if not arg:
        return "start", None
    if arg.isdigit() and int(arg) > 0:
        return "start", int(arg)
    action = _FOCUS_WORDS.get(arg)
    return (action, None) if action else None


def parse_dnd_arg(arg):
    """/dnd <arg> -> (ação, minutos) ou None. ''->alterna · on|off · '30'->liga por 30 min."""
    arg = (arg or "").strip().lower()
    if not arg:
        return "dnd_toggle", None
    if arg.isdigit() and int(arg) > 0:
        return "dnd_on", int(arg)
    action = _DND_WORDS.get(arg)
    return (action, None) if action else None


_SILENT_WORDS = {"on": "on", "liga": "on", "off": "off", "desliga": "off"}


def parse_silent_arg(arg):
    """/silent <arg> -> 'toggle' | 'on' | 'off' | None se inválido."""
    arg = (arg or "").strip().lower()
    return "toggle" if not arg else _SILENT_WORDS.get(arg)


def parse_rota_arg(arg):
    """/rota <arg> -> ('list', None, '') · ('set', local, endereço) · None se faltar o endereço.
    O local é uma palavra (casa, trabalho, faculdade, escola…); o resto é o endereço."""
    arg = (arg or "").strip()
    if not arg:
        return "list", None, ""
    word, _, rest = arg.partition(" ")
    rest = rest.strip()
    if not rest:
        return None
    return "set", word.lower(), rest


def unescape(text):
    """'//texto' → '/texto' (mensagem que começa com barra)."""
    return text[1:] if text.startswith("//") else text


# ------------------------------------------------------- arrastar arquivo
# O Windows Terminal, ao soltar um arquivo, cola o caminho (entre aspas se tiver
# espaço; vários arquivos separados por espaço). Extensões espelham os MIME
# aceitos em core/config.py (ALLOWED_IMAGE_MIME / ALLOWED_AUDIO_MIME).
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".oga"}
_PATH_TOKEN = re.compile(r'"([^"]+)"|\'([^\']+)\'|(\S+)')


def is_image_path(path):
    return Path(path).suffix.lower() in IMAGE_EXTS


def dropped_paths(text):
    """Caminhos de arquivos soltos no terminal, ou [] se o texto não for só isso.

    Só aceita quando **todo** pedaço é um arquivo existente de imagem/áudio —
    assim texto comum colado (mesmo com um caminho no meio) segue para o input.
    """
    if not text or not text.strip():
        return []
    whole = Path(text.strip().strip('"').strip("'")).expanduser()
    if whole.suffix.lower() in IMAGE_EXTS | AUDIO_EXTS and whole.is_file():
        return [str(whole)]  # um caminho com espaço que chegou sem aspas
    paths = []
    for match in _PATH_TOKEN.finditer(text.strip()):
        token = next(g for g in match.groups() if g)
        path = Path(token).expanduser()
        if path.suffix.lower() not in IMAGE_EXTS | AUDIO_EXTS or not path.is_file():
            return []
        paths.append(str(path))
    return paths


# ------------------------------------------------------------ paleta (Ctrl+K)
# Comandos que não fazem sentido sem argumento: a paleta só preenche o input.
NEEDS_ARG = {"rename", "attach", "web"}
# Fora da paleta: ela mesma e os que já têm entrada própria (modo/foco).
_PALETTE_SKIP = {"menu", "mode", "focus", "dnd"}

_FOCUS_ENTRIES = (
    ("Iniciar Pomodoro", "25 min de foco com Não Perturbe", "start"),
    ("Encerrar foco", "para o Pomodoro e o Não Perturbe", "stop"),
    ("Pular fase", "vai para a próxima fase do Pomodoro", "skip"),
    ("Quanto falta?", "tempo restante do foco", "status"),
    ("Não Perturbe", "liga/desliga: silencia notificações e alertas", "dnd_toggle"),
)


@dataclass(frozen=True)
class PaletteEntry:
    group: str   # COMANDOS | MODO | FOCO | SKILLS
    label: str
    desc: str
    kind: str    # command | prefill | mode | focus | skill
    value: object


def palette_entries(skills=(), mode="chat"):
    """Itens da paleta. `skills` = services.skill_settings.list_skills().
    No Copilot não há input: somem os comandos que só preenchem o prompt."""
    entries = []
    for name, (usage, desc) in COMMANDS.items():
        if name in _PALETTE_SKIP:
            continue
        if name in NEEDS_ARG:
            if mode == "copilot":
                continue
            entries.append(PaletteEntry("COMANDOS", usage, desc, "prefill", f"/{name} "))
        else:
            entries.append(PaletteEntry("COMANDOS", f"/{name}", desc, "command", name))
    other = "copilot" if mode == "chat" else "chat"
    entries.append(PaletteEntry("MODO", f"Ir para o {other.capitalize()}",
                                "Copilot: só voz, com skills" if other == "copilot" else "Chat: conversa por texto",
                                "mode", other))
    entries += [PaletteEntry("FOCO", label, desc, "focus", action) for label, desc, action in _FOCUS_ENTRIES]
    for cat in skills or ():
        for skill in cat.get("skills", ()):
            on = bool(skill.get("enabled"))
            entries.append(PaletteEntry("SKILLS", skill["id"],
                                        f"{cat.get('id', '?')} · {'ON → desligar' if on else 'OFF → ligar'}",
                                        "skill", (skill["id"], not on)))
    return entries


def fuzzy_score(query, text):
    """Pontuação da busca (None = não casa). Prefixo > início de palavra >
    subsequência; quanto mais junto e mais cedo, melhor."""
    query, text = query.lower().strip(), text.lower()
    if not query:
        return 0
    if text.startswith(query):
        return 1000 - len(text)
    words = text.replace("/", " ").replace("_", " ").replace("·", " ").split()
    if any(w.startswith(query) for w in words):
        return 800 - len(text)
    pos, gaps, last = 0, 0, -1
    for ch in query:
        pos = text.find(ch, pos)
        if pos < 0:
            return None
        if last >= 0:
            gaps += pos - last - 1
        last, pos = pos, pos + 1
    return 500 - gaps * 5 - len(text)


def filter_entries(entries, query):
    """Entradas que casam com `query`, da melhor para a pior (ordem original sem query)."""
    if not (query or "").strip():
        return list(entries)
    scored = []
    for i, entry in enumerate(entries):
        score = fuzzy_score(query, entry.label)
        desc_score = fuzzy_score(query, entry.desc)
        if desc_score is not None:
            desc_score -= 300  # descrição vale menos que o nome
        best = max((s for s in (score, desc_score) if s is not None), default=None)
        if best is not None:
            scored.append((-best, i, entry))
    return [entry for _s, _i, entry in sorted(scored)]
