from .SystemInfo import SystemInfo

sys_monitor = SystemInfo()
pending_critical_action = None

# Voz (wake word + TTS) é opcional na TUI e começa desligada.
# speak() vira no-op e o microfone nem é aberto enquanto for False.
voice_enabled = False

# Não Perturbe (services/focus.py): com ele ligado, alertas proativos não falam
# nem notificam — vão para o backlog e são resumidos quando o foco termina.
dnd_active = False
dnd_backlog = []
# Silêncio automático do filtro de notificações: "SILENT" (apresentação) | "REUNIÃO" | "TELA CHEIA" | None
auto_quiet = None
# Modo Apresentação ligado na mão (/silent, skill PRESENTATION_MODE) — services/presentation.py
presentation_active = False

# Callback opcional (str) -> None que a interface registra para exibir
# falas/alertas do JARVIS em texto (ex: TUI). None = só log.
announce = None
