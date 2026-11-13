# `services/brain.py` — roteador

O `brain` recebe cada mensagem (digitada ou falada) e decide o destino: confirmar uma ação pendente, gravar memória, executar uma skill ou conversar com o LLM.

## Funções

| Função | Uso |
|---|---|
| `execute_command_stream(command, session_id, images=None, mode="chat", on_route=None)` | Pipeline da TUI (Chat e Copilot). Generator de texto |
| `execute_command(command, session_id)` | Pipeline do modo voz standalone. Devolve a resposta inteira; todas as skills liberadas |
| `confirm_pending_action(approved)` | Resolve `state.pending_critical_action`: chama `on_confirm()` da skill ou, sem ele, encerra `target` via `APP_CONTROL` |
| `start_brain()` | Laço de voz sem interface (`python -m services.brain`) |

## Decisão

```
1. Há ação crítica pendente?      → a mensagem é a resposta (sim/pode/ok… = aprovado)
2. classify_intent(...)           → {intent, entity, confidence}
      modo chat: exclude_categories = ("automation", "system")
3. intent == MEMORY_WRITE         → memory.extract_fact_to_memory(command)
4. skill ligada e permitida       → on_route(intent); skill.execute(entity, command)
      copilot: qualquer skill · chat: só skill_allowed_in_chat()
5. resto (CHAT, HARDWARE, MEMORY_READ, skill bloqueada)
      → get_vault_context(command) + live_context.build(command)
      → chat.ask_local_ai_stream(..., mode=mode)
```

`on_route` é como a TUI sabe que a resposta veio de uma skill e mostra o selo `[INTENT] executando… ✓/✗`.

## Pontos de atenção

- O `brain` registra `core.alerts.process_system_alert` como callback padrão do `SystemInfo`; a TUI sobrescreve com o seu handler.
- A verificação de categoria é dupla: o classificador nem recebe as skills bloqueadas no Chat, e o `brain` confere de novo antes de executar.
- O prompt do modo (`mode_chat.md`/`mode_copilot.md`) é escolhido pelo `chat.py` a partir de `mode`. Matemática sai em LaTeX dentro de bloco de código (o terminal não renderiza KaTeX).
