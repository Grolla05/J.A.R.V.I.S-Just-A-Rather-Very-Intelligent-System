# `main.py` — boot da TUI

`backend/main.py` é o ponto de entrada do JARVIS. Ele prepara o ambiente, garante o Ollama no ar e entrega o controle à TUI (`frontend.app.JarvisApp`). Não existe mais janela PyWebView nem laço de voz próprio: a voz vive dentro da TUI (modo Copilot).

## Passo a passo (`start_jarvis`)

1. **`settings.perform_sanity_check()`** — cria as pastas graváveis (`settings.DIR_*`) e valida o `.env`.
2. **Crash log** — `faulthandler` grava o stack de todas as threads em `logs/crash.log` quando um crash nativo (PortAudio, CUDA) derruba o processo sem passar pelo logger.
3. **Perfil do Windows Terminal** — `core/wt_profile.ensure_profile()` grava o fragmento "JARVIS" (logo na aba).
4. **Ollama** — `core/ollama_server.ensure_ollama_running()` sobe `ollama serve` se o servidor local estiver fora (`OLLAMA_AUTOSTART`) e espera até `OLLAMA_START_TIMEOUT`. Nunca derruba o boot.
5. **`sys.path`** — põe a raiz do repositório no caminho para importar o pacote `frontend`.
6. **TUI** — `JarvisApp(boot_fn=run_boot, start_mode=..., quiet_boot=..., update_fn=..., install_fn=...).run()`:
   - `boot_fn` (`core/boot.run_boot`) roda as checagens na tela de boot; warm-up do modelo e scan de hardware vão para threads daemon.
   - `update_fn`/`install_fn` (`core/updater`) mostram a tela de atualização e pedem a instalação ao agente.
7. **Saída** — `os._exit(0)` derruba threads presas em I/O bloqueante (microfone, monitor).

## Argumentos

| Argumento | Efeito |
|---|---|
| (nenhum) | Abre no Chat, com tela de boot |
| `--copilot` | Aberto pelo agente (`Win+J`/bandeja): já no Copilot (voz), sem tela de boot |
| `--update-preview [versão]` | Dev: mostra a tela "ATUALIZAÇÃO DISPONÍVEL!!" sem rede e sem instalar |

## Outros pontos de entrada

| Comando | O quê |
|---|---|
| `python agent.py` | Agente residente (bandeja, `Win+J`, `Ctrl+Alt+T`, atualização). Instalado, sobe no logon com `--logon` |
| `python -m services.brain` | Modo voz standalone, sem interface (`start_brain`) |

## Regras

- Nenhum import pesado (deep learning, áudio) no topo do `main.py`: cada serviço carrega sob demanda.
- Toda thread nova é `daemon=True`, para o `os._exit(0)` encerrá-la.
- Nada escreve em `sys.stdout` depois que a TUI sobe — use `log` ou `state.announce`.
