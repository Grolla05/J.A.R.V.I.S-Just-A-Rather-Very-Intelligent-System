from .SystemInfo import SystemInfo

sys_monitor = SystemInfo()
pending_critical_action = None

# Voz (wake word + TTS) é opcional na TUI e começa desligada.
# speak() vira no-op e o microfone nem é aberto enquanto for False.
voice_enabled = False

# Callback opcional (str) -> None que a interface registra para exibir
# falas/alertas do JARVIS em texto (ex: TUI). None = só log.
announce = None
