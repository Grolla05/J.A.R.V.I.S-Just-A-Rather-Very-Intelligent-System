# `backend/services/` — roteamento, conversa, voz e rotinas

Os serviços ficam entre a interface e o `core/`. Recebem texto (digitado ou falado), decidem o que fazer e devolvem texto em stream.

## Pipeline

```
texto (TUI ou voz)
  └─ brain.execute_command_stream(texto, session_id, images, mode, on_route)
       ├─ ação crítica pendente?  → confirm_pending_action (sim/não)
       ├─ intent.classify_intent  → Ollama em JSON {intent, entity, confidence}
       │     Chat: exclude_categories=("automation", "system")
       ├─ MEMORY_WRITE            → memory.extract_fact_to_memory → Obsidian
       ├─ skill ligada/permitida  → on_route(intent) → skill.execute(entity, texto)
       └─ CHAT / HARDWARE / MEMORY_READ
             → chat.ask_local_ai_stream(histórico + vault + live_context + telemetria)
```

`execute_command` (sem stream) é a versão do modo voz standalone (`python -m services.brain`), sempre com todas as skills.

## Módulos

| Módulo | Papel |
|---|---|
| `brain.py` | Roteador. Modos `chat` (só skills fora de `automation`/`system`) e `copilot` (todas). `confirm_pending_action(approved)` executa `pending['on_confirm']` ou encerra o processo-alvo |
| `intent.py` | `classify_intent(texto, skip_skills, exclude_categories)` com cache TTL (30 s, 64 entradas). Intents fixos: `HARDWARE`, `MEMORY_READ`, `MEMORY_WRITE`, `CHAT`, mais os `INTENT` das skills ligadas. `is_skill_enabled`, `skill_allowed_in_chat` |
| `chat.py` | Monta as mensagens: system prompt + regras do modo (`mode_chat.md`/`mode_copilot.md` ou voz) + `LIVE DATA` (telemetria) + nota do vault + `live_context` + últimas 8 mensagens da sessão. `HARDWARE` injeta as specs; imagens vão para o modelo de visão |
| `live_context.py` | Pergunta sobre agenda ("o que tenho amanhã?") → eventos reais do Google Agenda no prompt, com instrução de não inventar |
| `memory.py` | Extrai chave/valor de "lembre que…" e grava em `🚀 Projetos/J.A.R.V.I.S/Memória/{chave}.md` |
| `sessions.py` | Sessões e histórico (listar, renomear, fixar, apagar, editar a partir de uma mensagem). `to_local()` converte o UTC do SQLite |
| `skill_settings.py` | Lista skills e liga/desliga skill ou categoria (`disabled_skills`, `disabled_categories` na tabela `config`) |
| `user_prefs.py` | Preferências do `/config`: voz, velocidade, volume, sensibilidade do mic, janela de atenção, briefing automático, manchetes, monitor de clipboard, aviso de saída, silêncio em reunião/tela cheia, apresentação automática |
| `integrations.py` | Cards de `/config` → INTEGRAÇÕES. Estados `on`/`wait`/`off`/`setup`; `connect`/`disconnect` devolvem texto e nunca levantam |
| `listen.py` | Ouvido lazy (`get_ear()`): mic só abre com a voz ligada; wake word (`WAKE_WORDS`) por palavra inteira; Google STT; janela de atenção; `ear_pause`/`ear_resume`; nível do mic para a `VoiceBar` |
| `speak.py` | TTS: edge-tts (voz da pref, padrão `pt-BR-AntonioNeural`) com fallback pyttsx3; `speech_lock`; limpa Markdown e símbolos e expande gírias (`SLANG_MAP`); no-op com a voz desligada ou em apresentação |
| `focus.py` | `FocusManager`: Pomodoro (25/5, longa 15 a cada 4) e Não Perturbe (toasts do Windows off + backlog de alertas com resumo no fim) |
| `presentation.py` | Modo Apresentação manual (`/silent`, skill) ou automático (PowerPoint, Canva, Google Slides, PDF em tela cheia) |
| `notify_filter.py` | Prioridade do alerta (`critical`/`high`/`normal`) × contexto (apresentação, DND, reunião, tela cheia) → falar, guardar ou descartar; selo da linha de status |

## Regras

- `listen` e `speak` nunca são importados no topo de outros módulos (import dentro da função).
- A `speech_lock` do `speak.py` não pode ser removida.
- Ações do `FocusManager` devolvem texto; só troca de fase e fim de prazo anunciam sozinhas.
- Dado pessoal que o Chat precisa responder entra como contexto (`live_context`), nunca deixado para o LLM adivinhar.
