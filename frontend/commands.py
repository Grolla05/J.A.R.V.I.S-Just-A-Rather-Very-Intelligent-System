"""Parser dos /comandos da TUI (puro, sem dependência de Textual)."""
from dataclasses import dataclass

# nome -> (uso, descrição). Ordem = ordem do /help.
COMMANDS = {
    "help":     ("/help", "lista os comandos"),
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
    "clear":    ("/clear", "limpa a tela (não apaga o histórico)"),
    "quit":     ("/quit", "encerra o J.A.R.V.I.S (Ctrl+Q)"),
}

ALIASES = {"q": "quit", "exit": "quit", "h": "help", "?": "help", "s": "sessions", "n": "new"}


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
        return Command("help")
    name, _, arg = body.partition(" ")
    name = ALIASES.get(name.lower(), name.lower())
    return Command(name, arg.strip(), name in COMMANDS)


def unescape(text):
    """'//texto' → '/texto' (mensagem que começa com barra)."""
    return text[1:] if text.startswith("//") else text


def help_markdown():
    lines = ["| comando | ação |", "|---|---|"]
    lines += [f"| `{usage}` | {desc} |" for usage, desc in COMMANDS.values()]
    return "\n".join(lines)
