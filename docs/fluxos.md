# Fluxos de um comando

Passo a passo de uma fala (modo Copilot) e de uma mensagem digitada (modo Chat). Regras da interface em [`tui.md`](tui.md); visão completa em [`arquitetura.md`](arquitetura.md); resumo do projeto em [`AGENTS.md`](../AGENTS.md).

## Fluxo de um comando de voz (modo Copilot)

```
1. listen.py           → captura áudio (Google STT), detecta wake word "Jarvis"   · orb: ouvindo
2. frontend/app.py     → _voice_loop mostra a fala no log (sessão atual, "voz · HH:MM") · orb: pensando
3. brain.py            → execute_command_stream(mode="copilot"): pending_critical_action? → intent → skill ou LLM
4. frontend/app.py     → _run_turn pinta o stream + selo da skill                  · orb: respondendo
5. speak.py            → edge-tts (ou pyttsx3) → áudio                              · orb volta a ouvindo
```

`execute_command()` (sem stream) segue existindo para o modo standalone `python -m services.brain`.

## Fluxo de uma mensagem no Chat (TUI)

```
1. PromptInput         → usuário digita + Enter (ou /comando)
2. JarvisApp.send      → monta bolhas e dispara o worker _stream (thread)
3. db.log_interaction  → salva a mensagem (com anexo, se houver /attach)
4. brain.py            → execute_command_stream(text, session_id, images, mode)
5. intent.py           → classify_intent(text, allowed_categories=("productivity", "web") no Chat)
6. chat.py             → ask_local_ai_stream() → Ollama stream (ou skill no Copilot)
7. MessageView         → call_from_thread(set_text) a cada 50 ms → Markdown em tempo real
```
