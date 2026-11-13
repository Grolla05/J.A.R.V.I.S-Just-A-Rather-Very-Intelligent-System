# `services/speak.py` — voz do JARVIS (TTS)

Transforma texto em fala. A voz é **opcional**: começa desligada e liga com `/voice`, `Ctrl+T` ou entrando no Copilot. Nada de áudio é carregado no import — `pygame` e `pyttsx3` só inicializam na primeira fala.

## `speak(text, play_callback=None, show=True, force=False)`

1. `show=True` → `state.announce(text)` mostra a fala na TUI (quem já exibe a resposta passa `show=False`).
2. Sai sem falar se o **Modo Apresentação** estiver ativo (mesmo com `force`) ou se a voz estiver desligada e `force=False`. `force=True` é usado pelo briefing, que é sempre falado.
3. Com a `speech_lock` (nunca remover: impede alerta e resposta falando ao mesmo tempo):
   - **Online:** `edge-tts` gera o MP3 com a voz, velocidade e volume do `/config` (padrão `pt-BR-AntonioNeural`), tocado pelo `pygame`. `play_callback` dispara quando o áudio começa.
   - **Offline:** se o online falhar, `pyttsx3` (rate `SPEECH_RATE`).

## Limpeza do texto (`_treat_text`)

Antes do TTS: remove Markdown e símbolos (fica só letra, número, espaço e pontuação básica) e expande gírias via `SLANG_MAP` (`vc` → você, `tmj` → tamo junto…).

## Integração com o ouvido

Quem fala com a voz ligada pausa o microfone (`listen.ear_pause()`/`ear_resume()`), para o JARVIS não ouvir a própria resposta. A TUI faz isso em `_speak_always` e no `_voice_loop`.

## Regras

- Importe `speak` dentro da função que usa (import tardio), nunca no topo de outro módulo.
- Arquivos temporários de áudio usam nome único em `settings.DIR_SOUNDS`.
