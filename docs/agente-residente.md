# Agente residente (`backend/agent.py`)

Processo em segundo plano que segura os atalhos globais e a atualização automática. Resumo do projeto em [`AGENTS.md`](../AGENTS.md); interface em [`tui.md`](tui.md); visão ponta a ponta em [`arquitetura.md`](arquitetura.md).

## Regras

- Processo separado (pythonw, sem janela, bandeja via `pystray`) que segura `GLOBAL_HOTKEY` e sobe no logon (valor `JARVIS` em `HKCU\…\Run`, ligado pelo instalador, `/config` → SISTEMA ou bandeja). Fechar a TUI não o fecha
- Fala com a TUI só por `core/presence.py` (arquivo `tui.json` + eventos nomeados) — nada de socket/HTTP. A TUI chama `register_tui` no `on_mount` (com serviços) e `unregister_tui` ao sair
- Leve de propósito: registra um pacote `core` vazio em `sys.modules` para não rodar o `core/__init__` (banco, skills). Módulos usados por ele (`config`, `logger`, `hotkey`, `presence`, `autostart`, `launcher`, `window_utils`, `updater`) não podem importar o pacote `core` inteiro

## Atualização automática (`core/updater.py`)

- `check_available()` (Release de `UPDATE_REPO` **mais novo** que `settings.VERSION`; nunca levanta; cache `updates/available.json` por `CACHE_TTL_S`) roda na abertura da TUI (`JarvisApp(update_fn=, install_fn=, snooze_fn=)`, depois do boot) e no agente com `--logon` (que então abre a TUI)
- Com versão nova a TUI mostra `UpdateScreen` (`frontend/screens/update.py`, orb parada); **Enter** chama `request_install()` (Esc chama `snooze()`: adia aquela versão por 24 h em `updates/snooze.json`, inclusive no logon; teclas nos primeiros 0,5 s são ignoradas) → evento `presence.INSTALL_UPDATE` (agente → `install_latest`: espera a TUI fechar, baixa, confere o SHA-256 do `digest` e roda o setup `/VERYSILENT /SKIPOLLAMA /UPDATE`) ou, sem agente, sobe um com `--install-update`; a TUI fecha com o CRT
- O agente se fecha e o `[Run]` com `Check: EhAtualizacao` o reabre. O setup fecha `python`/`pythonw` do runtime e apaga `{app}\app` e `{app}\runtime` antes de copiar: a versão nova substitui a antiga
- Dev (sem `JARVIS_DATA_DIR`) nunca atualiza; `main.py --update-preview X` mostra a tela sem instalar. Toggle em `/config` → SISTEMA (registro `HKCU\Software\JARVIS\AutoUpdate`, padrão `AUTO_UPDATE`)
